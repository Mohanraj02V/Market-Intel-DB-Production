"""Tests for end-to-end WhatsApp AI + Strict RAG integration, legacy preservation, and non-fallback guarantees."""
from __future__ import annotations

import json
import re
import tempfile
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from rag.constants import DEFAULT_REFUSAL_MESSAGE
from rag.models import KnowledgeBase, KnowledgeBaseSessionAssignment, SessionRAGConfig
from rag.services import document_upload_service
from rag.tests.helpers import make_user, patched_Subsystems
from rag.workers.ingestion_worker import process_document
from whatsapp.models import WhatsAppConfiguration, WhatsAppConversation, WhatsAppMessage, WhatsAppSession
from whatsapp_ai.gemini_service import process_ai_auto_reply
from whatsapp_ai.models import WhatsAppAIReplyLog


class WhatsAppRAGIntegrationTestCase(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        WhatsAppConfiguration.objects.get_or_create(
            pk=1, defaults={"outbound_enabled": True, "safety_stop_active": False}
        )
        self.superadmin = make_user("wa_rag_superadmin", role="MANAGER", is_superuser=True)
        self.user = make_user("wa_rag_owner", role="LQ")
        self.session = WhatsAppSession.objects.create(
            owner=self.user,
            session_name="wa_rag_sess",
            phone_number="+919003619221",
            status=WhatsAppSession.Status.READY,
            is_active=True,
        )
        self.conversation = WhatsAppConversation.objects.create(
            session=self.session,
            chat_id="919876543210@c.us",
            phone_number="+919876543210",
            whatsapp_name="Customer Ravi",
        )
        self.kb = KnowledgeBase.objects.create(owner=self.user, name="Store KB")
        from whatsapp_ai.models import WhatsAppAIAutoReplyConfig
        WhatsAppAIAutoReplyConfig.objects.create(session=self.session, enabled=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_inbound(self, text: str, idx: int = 1) -> WhatsAppMessage:
        now = timezone.now()
        return WhatsAppMessage.objects.create(
            idempotency_key=f"in-{idx}-{now.timestamp()}",
            conversation=self.conversation,
            waha_message_id=f"waha-in-{idx}",
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            body_preview=text[:200],
            full_body=text,
            body_hash=WhatsAppMessage.compute_body_hash(text),
            message_type="chat",
            waha_timestamp=now,
            sent_at=now,
        )

    @patch("whatsapp.client.get_waha_client")
    @patch("whatsapp_ai.gemini_service.generate_gemini_whatsapp_reply")
    def test_legacy_session_without_strict_rag_uses_existing_gemini_path(
        self, mock_legacy_gemini, mock_get_waha
    ):
        mock_legacy_gemini.return_value = ("Legacy helpful reply", "gemini-2.5-flash")
        fake_waha = MagicMock()
        fake_waha.send_text.return_value = {"id": "waha-out-legacy"}
        mock_get_waha.return_value = fake_waha

        msg = self._create_inbound("Hello, can you help me?", idx=1)
        with override_settings(WHATSAPP_AI_AUTO_REPLY_ENABLED=True):
            res = process_ai_auto_reply(msg.pk)

        self.assertEqual(res["status"], "SENT")
        self.assertEqual(res["reply_text"], "Legacy helpful reply")
        mock_legacy_gemini.assert_called_once()
        fake_waha.send_text.assert_called_once_with(
            session_name="wa_rag_sess",
            chat_id="919876543210@c.us",
            text="Legacy helpful reply",
            reply_to=None,
        )

    @patch("whatsapp.client.get_waha_client")
    @patch("whatsapp_ai.gemini_service.generate_gemini_whatsapp_reply")
    def test_strict_rag_answers_from_kb_refuses_unrelated_and_never_falls_back_to_general_gemini(
        self, mock_legacy_gemini, mock_get_waha
    ):
        fake_waha = MagicMock()
        fake_waha.send_text.return_value = {"id": "waha-out-rag"}
        mock_get_waha.return_value = fake_waha

        with override_settings(
            RAG_LOCAL_STORAGE_DIR=self.temp_dir.name,
            RAG_QUEUE_BACKEND="local",
            WHATSAPP_AI_AUTO_REPLY_ENABLED=True,
        ):
            def mock_rag_gemini(model, system, user_prompt, schema, timeout):
                if "supported" in (schema.get("properties") or {}):
                    return json.dumps({"supported": True, "unsupported_claims": []})
                m = re.search(r'<evidence id="([^"]+)"', user_prompt)
                cid = m.group(1) if m else ""
                return json.dumps({
                    "answer": "Steel Bolt M10 is 18.00 INR per piece.",
                    "can_answer": True,
                    "source_chunk_ids": [cid],
                    "confidence": 0.96,
                    "refusal_reason": "",
                })

            with patched_Subsystems(gemini_transport=mock_rag_gemini):
                doc = document_upload_service.upload_document(
                    self.kb,
                    self.superadmin,
                    SimpleUploadedFile(
                        "prices.csv",
                        b"Product,Price,Currency\nSteel Bolt M10,18.00,INR\n",
                        content_type="text/csv",
                    ),
                )
                process_document(doc.pk)

                KnowledgeBaseSessionAssignment.objects.create(
                    session=self.session, knowledge_base=self.kb, is_active=True
                )
                SessionRAGConfig.objects.create(session=self.session, strict_rag_enabled=True)

                # 1. Answerable question -> grounded answer sent via WAHA on the exact session
                msg1 = self._create_inbound("What is the price of Steel Bolt M10?", idx=10)
                res1 = process_ai_auto_reply(msg1.pk)
                self.assertEqual(res1["status"], "SENT")
                self.assertEqual(res1["reply_text"], "Steel Bolt M10 is 18.00 INR per piece.")
                # Unrestricted legacy Gemini was NEVER called
                mock_legacy_gemini.assert_not_called()

                # Duplicate reply prevention: calling process_ai_auto_reply again for msg1 is skipped
                dup = process_ai_auto_reply(msg1.pk)
                self.assertEqual(dup["reason"], "already_processed")
                self.assertEqual(fake_waha.send_text.call_count, 1)

                # 2. Unrelated / unavailable KB question -> offers executive escalation cleanly, NEVER calls general Gemini
                from whatsapp_ai.assistant_workflows import ESCALATION_OFFER_MESSAGE
                msg2 = self._create_inbound("Who won the FIFA World Cup?", idx=11)
                res2 = process_ai_auto_reply(msg2.pk)
                self.assertEqual(res2["status"], "SENT")
                self.assertEqual(res2["reply_text"], ESCALATION_OFFER_MESSAGE)
                mock_legacy_gemini.assert_not_called()

                # 3. If RAG infrastructure fails (e.g., Bedrock down), Strict RAG skips sending rather than falling back
                from rag.exceptions import EmbeddingError

                with patch("rag.services.embedding_service.embed_query", side_effect=EmbeddingError("Bedrock down")):
                    msg3 = self._create_inbound("What is the price of Steel Bolt M10?", idx=12)
                    res3 = process_ai_auto_reply(msg3.pk)
                    self.assertEqual(res3["status"], "SKIPPED")
                    self.assertIn("strict_rag:", res3["reason"])
                    mock_legacy_gemini.assert_not_called()
                    log3 = WhatsAppAIReplyLog.objects.get(incoming_message=msg3)
                    self.assertEqual(log3.status, WhatsAppAIReplyLog.Status.SKIPPED)
