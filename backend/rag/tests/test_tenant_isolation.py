"""Tests for strict tenant, user, company, and WhatsAppSession isolation across APIs and vector retrieval."""
from __future__ import annotations

import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from companies.models import Company
from rag.exceptions import AuthorizationError
from rag.models import KnowledgeBase, KnowledgeBaseSessionAssignment
from rag.services import document_upload_service, rag_pipeline_service, retrieval_service, vector_store_service
from rag.tests.helpers import make_user, patched_Subsystems
from rag.workers.ingestion_worker import process_document
from whatsapp.models import WhatsAppSession


class TenantIsolationTestCase(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.company_a = Company.objects.create(name="Alpha Corp", code="ALPHA", slug="alpha-corp")
        self.company_b = Company.objects.create(name="Beta Corp", code="BETA", slug="beta-corp")

        self.superadmin = make_user("ingester_superadmin", role="MANAGER", is_superuser=True)
        self.user_a = make_user("alice_alpha", role="MANAGER", company=self.company_a)
        self.user_b = make_user("bob_beta", role="MANAGER", company=self.company_b)

        self.session_a = WhatsAppSession.objects.create(
            owner=self.user_a, session_name="wa_alice", status=WhatsAppSession.Status.READY, is_active=True
        )
        self.session_b = WhatsAppSession.objects.create(
            owner=self.user_b, session_name="wa_bob", status=WhatsAppSession.Status.READY, is_active=True
        )

        self.kb_a = KnowledgeBase.objects.create(
            owner=self.user_a, company=self.company_a, name="Alpha KB"
        )
        self.kb_b = KnowledgeBase.objects.create(
            owner=self.user_b, company=self.company_b, name="Beta Secret KB"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_zero_cross_tenant_chunk_leakage_and_api_isolation(self):
        with override_settings(RAG_LOCAL_STORAGE_DIR=self.temp_dir.name, RAG_QUEUE_BACKEND="local"):
            with patched_Subsystems():
                doc_a = document_upload_service.upload_document(
                    self.kb_a,
                    self.superadmin,
                    SimpleUploadedFile(
                        "alpha.txt",
                        b"Our showroom is at 14 Gandhi Road, Coimbatore 641001.",
                        content_type="text/plain",
                    ),
                )
                doc_b = document_upload_service.upload_document(
                    self.kb_b,
                    self.superadmin,
                    SimpleUploadedFile(
                        "beta_secret.txt",
                        b"secret_company_b Quantum Turbine price is 99999 USD.",
                        content_type="text/plain",
                    ),
                )
                process_document(doc_a.pk)
                process_document(doc_b.pk)

                # 1. SQL base_queryset for kb_a never returns chunks from kb_b
                a_chunk_kb_ids = set(
                    vector_store_service.base_queryset(self.kb_a).values_list("knowledge_base_id", flat=True)
                )
                self.assertEqual(a_chunk_kb_ids, {self.kb_a.id})

                # 2. User A cannot retrieve from KB B
                with self.assertRaises(AuthorizationError):
                    retrieval_service.retrieve(
                        self.kb_b, query_text="Quantum Turbine price", user=self.user_a
                    )

                # 3. Session A cannot be assigned to KB B via API, nor access KB B's documents
                client = APIClient()
                client.force_authenticate(user=self.user_a)

                resp_kb_list = client.get("/api/rag/knowledge-bases/")
                self.assertEqual(resp_kb_list.status_code, 200)
                returned_ids = {item["id"] for item in resp_kb_list.data["results"]}
                self.assertIn(str(self.kb_a.id), returned_ids)
                self.assertNotIn(str(self.kb_b.id), returned_ids)

                # Cross-tenant document access returns 404 (and delete is 403 for non-superadmin)
                self.assertEqual(client.get(f"/api/rag/documents/{doc_b.id}/").status_code, 404)
                self.assertEqual(client.delete(f"/api/rag/documents/{doc_b.id}/").status_code, 403)
                self.assertEqual(client.delete(f"/api/rag/documents/{doc_a.id}/").status_code, 403)

                # Cross-tenant session assignment rejected
                assign_resp = client.post(
                    "/api/rag/session-assignments/",
                    {"session": self.session_a.pk, "knowledge_base": str(self.kb_b.id), "is_active": True},
                    format="json",
                )
                self.assertEqual(assign_resp.status_code, 400)

                # Even if a database row were forged linking session_a to kb_b, pipeline refuses with tenant_mismatch
                KnowledgeBaseSessionAssignment.objects.create(
                    session=self.session_a, knowledge_base=self.kb_b, is_active=True
                )
                forged = rag_pipeline_service.answer_for_session(
                    self.session_a, "What is the Quantum Turbine price?"
                )
                self.assertEqual(forged.status, "REFUSED")
                self.assertEqual(forged.refusal_reason, "tenant_mismatch")
                self.assertNotIn("99999", forged.reply_text)
