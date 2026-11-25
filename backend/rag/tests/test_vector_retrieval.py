"""Tests for PostgreSQL/pgvector similarity retrieval, top-K, active/READY filtering, and relevance thresholding."""
from __future__ import annotations

import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from rag.models import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentChunk
from rag.services import document_upload_service, retrieval_service
from rag.tests.helpers import make_user, patched_Subsystems
from rag.workers.ingestion_worker import process_document


class VectorRetrievalTestCase(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.user = make_user("retrieval_user", role="LQ", is_superuser=True)
        self.kb = KnowledgeBase.objects.create(owner=self.user, name="Hardware KB")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_top_k_active_ready_filtering_and_relevance_threshold(self):
        with override_settings(RAG_LOCAL_STORAGE_DIR=self.temp_dir.name, RAG_QUEUE_BACKEND="local"):
            with patched_Subsystems():
                doc = document_upload_service.upload_document(
                    self.kb,
                    self.user,
                    SimpleUploadedFile(
                        "company_profile.md",
                        (
                            "# Showroom\n\nOur showroom is located at 14 Gandhi Road, Coimbatore 641001.\n\n"
                            "# Business Hours\n\nWe are open Monday to Saturday from 9:00 AM to 7:00 PM.\n"
                        ).encode("utf-8"),
                        content_type="text/markdown",
                    ),
                )
                # Before ingestion (status=UPLOADED, is_active=False), retrieval returns no_results
                pre = retrieval_service.retrieve(
                    self.kb, query_text="Where is your showroom located?", user=self.user, top_k=3
                )
                self.assertEqual(pre.status, "no_results")

                process_document(doc.pk)

                # Relevant query passes threshold and returns matching chunk
                hit = retrieval_service.retrieve(
                    self.kb, query_text="Where is your showroom located?", user=self.user, top_k=3, threshold=0.30
                )
                self.assertEqual(hit.status, "ok")
                self.assertGreaterEqual(len(hit.chunks), 1)
                self.assertIn("Gandhi Road", hit.chunks[0].text)

                # Unrelated general-knowledge query falls below threshold -> low_relevance
                miss = retrieval_service.retrieve(
                    self.kb,
                    query_text="Who is the prime minister of India?",
                    user=self.user,
                    top_k=3,
                    threshold=0.30,
                )
                self.assertEqual(miss.status, "low_relevance")
                self.assertEqual(len(miss.chunks), 0)

                # Chunks from a different embedding model are excluded at the SQL level
                KnowledgeDocumentChunk.objects.filter(document=doc).update(embedding_model="old-model-v1")
                stale = retrieval_service.retrieve(
                    self.kb, query_text="Where is your showroom located?", user=self.user, top_k=3
                )
                self.assertEqual(stale.status, "no_results")
