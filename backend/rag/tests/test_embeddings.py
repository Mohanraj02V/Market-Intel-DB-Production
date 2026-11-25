"""Tests for Amazon Bedrock Titan V2 embedding generation, retry/backoff, and dimension validation."""
from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from rag.exceptions import EmbeddingConfigError, EmbeddingError
from rag.services import embedding_service
from rag.tests.helpers import FakeBedrockClient, patched_Subsystems


class EmbeddingServiceTestCase(SimpleTestCase):
    def test_embeds_query_and_batches_with_expected_dimensions(self):
        client = FakeBedrockClient(dim=1024)
        with patched_Subsystems(bedrock_client=client):
            qvec = embedding_service.embed_query("What are your business hours?")
            self.assertEqual(len(qvec), 1024)
            batch = embedding_service.embed_texts(["First chunk", "Second chunk", "Third chunk"])
            self.assertEqual(len(batch), 3)
            self.assertTrue(all(len(v) == 1024 for v in batch))

    @patch("time.sleep", return_value=None)
    def test_retries_transient_throttling_and_succeeds(self, _mock_sleep):
        client = FakeBedrockClient(dim=1024, fail_times=2, error_code="ThrottlingException")
        with patched_Subsystems(bedrock_client=client):
            vec = embedding_service.embed_query("Steel Bolt M10 price")
            self.assertEqual(len(vec), 1024)
            self.assertEqual(client.calls, 3)

    @patch("time.sleep", return_value=None)
    def test_raises_embedding_error_without_model_substitution_when_bedrock_fails(self, _mock_sleep):
        client = FakeBedrockClient(dim=1024, fail_times=10, error_code="AccessDeniedException")
        with patched_Subsystems(bedrock_client=client):
            with self.assertRaises(EmbeddingError):
                embedding_service.embed_query("Any question")

    def test_detects_mismatched_dimension_or_conflicting_model_env(self):
        with override_settings(RAG_EMBEDDING_DIMENSIONS=512):
            with self.assertRaises(EmbeddingConfigError):
                embedding_service.validate_configuration()

        with override_settings(
            BEDROCK_EMBEDDING_MODEL_ID="amazon.titan-embed-text-v2:0",
            RAG_EMBEDDING_MODEL="cohere.embed-english-v3",
        ):
            with self.assertRaises(ImproperlyConfigured):
                embedding_service.validate_configuration()
