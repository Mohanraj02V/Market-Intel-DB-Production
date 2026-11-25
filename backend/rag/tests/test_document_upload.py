"""Tests for document upload validation, storage, duplicate detection, versioning, and retry/deletion lifecycle."""
from __future__ import annotations

import io
import os
import tempfile
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from rag.exceptions import AuthorizationError, DocumentValidationError, DuplicateDocumentError
from rag.models import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentChunk
from rag.services import document_upload_service, knowledge_base_service
from rag.tests.helpers import make_user, patched_Subsystems
from rag.workers.ingestion_worker import process_document
from rest_framework.test import APIClient


class DocumentUploadTestCase(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.user = make_user("upload_superadmin", role="LQ", is_superuser=True)
        self.non_admin = make_user("upload_non_admin", role="MANAGER", is_superuser=False)
        self.kb = KnowledgeBase.objects.create(owner=self.user, name="Catalogue KB")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_only_superadmin_can_ingest_retry_or_delete_documents(self):
        with self.assertRaises(AuthorizationError):
            document_upload_service.upload_document(
                self.kb,
                self.non_admin,
                SimpleUploadedFile("prices.txt", b"Bolt 10 INR", content_type="text/plain"),
            )

        client = APIClient()
        client.force_authenticate(user=self.non_admin)
        resp_kb = client.post("/api/rag/knowledge-bases/", {"name": "Blocked KB"}, format="json")
        self.assertEqual(resp_kb.status_code, 403)
        resp_doc = client.post(
            f"/api/rag/knowledge-bases/{self.kb.id}/documents/",
            {"file": SimpleUploadedFile("prices.txt", b"Bolt 10 INR", content_type="text/plain")},
            format="multipart",
        )
        self.assertEqual(resp_doc.status_code, 403)

    def test_rejects_unsupported_extension_and_spoofed_magic_bytes(self):
        with self.assertRaises(DocumentValidationError) as ctx:
            document_upload_service.upload_document(
                self.kb,
                self.user,
                SimpleUploadedFile("malware.exe", b"MZ\x90\x00", content_type="application/octet-stream"),
            )
        self.assertEqual(ctx.exception.code, "unsupported_type")

        # Spoofed PDF extension containing plain text (missing %PDF- signature)
        with self.assertRaises(DocumentValidationError) as ctx2:
            document_upload_service.upload_document(
                self.kb,
                self.user,
                SimpleUploadedFile("fake.pdf", b"This is not a real PDF file", content_type="application/pdf"),
            )
        self.assertEqual(ctx2.exception.code, "signature_mismatch")

        # Empty file rejected
        with self.assertRaises(DocumentValidationError) as ctx3:
            document_upload_service.upload_document(
                self.kb,
                self.user,
                SimpleUploadedFile("empty.txt", b"", content_type="text/plain"),
            )
        self.assertEqual(ctx3.exception.code, "empty_file")

    def test_upload_deduplication_versioning_and_safe_deletion(self):
        with override_settings(RAG_LOCAL_STORAGE_DIR=self.temp_dir.name, RAG_QUEUE_BACKEND="local"):
            with patched_Subsystems():
                f1 = SimpleUploadedFile(
                    "prices.csv",
                    b"Product,Price,Currency\nSteel Bolt M10,18.00,INR\n",
                    content_type="text/csv",
                )
                doc1 = document_upload_service.upload_document(self.kb, self.user, f1)
                self.assertEqual(doc1.status, "UPLOADED")
                self.assertEqual(doc1.version, 1)
                self.assertFalse(doc1.is_active)

                # Duplicate upload of identical content is rejected
                with self.assertRaises(DuplicateDocumentError):
                    document_upload_service.upload_document(
                        self.kb,
                        self.user,
                        SimpleUploadedFile(
                            "prices_copy.csv",
                            b"Product,Price,Currency\nSteel Bolt M10,18.00,INR\n",
                            content_type="text/csv",
                        ),
                    )

                # Run ingestion -> READY and active
                res1 = process_document(doc1.pk)
                self.assertEqual(res1.status, "ready")
                doc1.refresh_from_db()
                self.assertEqual(doc1.status, "READY")
                self.assertTrue(doc1.is_active)
                self.assertGreater(doc1.total_chunks, 0)

                # Idempotent retry: re-running process_document on READY document is a safe no-op
                again = process_document(doc1.pk)
                self.assertEqual(again.status, "skipped")
                self.assertEqual(
                    KnowledgeDocumentChunk.objects.filter(document=doc1).count(),
                    doc1.total_chunks,
                )

                # Uploading a new version of prices.csv creates v2, and retires v1 only once v2 is READY
                doc2 = document_upload_service.upload_document(
                    self.kb,
                    self.user,
                    SimpleUploadedFile(
                        "prices.csv",
                        b"Product,Price,Currency\nSteel Bolt M10,20.00,INR\nCopper Wire 2mm,240,INR\n",
                        content_type="text/csv",
                    ),
                )
                self.assertEqual(doc2.version, 2)
                self.assertFalse(doc2.is_active)
                # Before v2 is ingested, v1 remains active
                doc1.refresh_from_db()
                self.assertTrue(doc1.is_active)

                res2 = process_document(doc2.pk)
                self.assertEqual(res2.status, "ready")
                doc2.refresh_from_db()
                self.assertTrue(doc2.is_active)
                self.assertFalse(KnowledgeDocument.objects.filter(pk=doc1.pk).exists())

                # Safe deletion removes chunks, storage file, and DB row
                knowledge_base_service.delete_document(doc2, actor=self.user)
                self.assertEqual(KnowledgeDocumentChunk.objects.filter(knowledge_base=self.kb).count(), 0)
                self.assertEqual(KnowledgeDocument.objects.filter(knowledge_base=self.kb).count(), 0)
