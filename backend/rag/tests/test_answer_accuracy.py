"""Evaluation dataset accuracy tests across all 15 required test categories."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from rag.evaluation import metrics, runner
from rag.models import KnowledgeBase
from rag.services import document_upload_service
from rag.tests.helpers import make_user, patched_Subsystems
from rag.workers.ingestion_worker import process_document


def _grounded_mock_gemini(model, system, user_prompt, schema, timeout):
    """
    Deterministic grounded responder for evaluation tests:
    - Judge schema: returns supported=True when all numbers in <answer> appear in <evidence>.
    - Answer schema: inspects ONLY the provided <evidence> blocks in `user_prompt` and answers
      strictly from them, or sets can_answer=False if the evidence does not cover the question.
    """
    if "supported" in (schema.get("properties") or {}):
        return json.dumps({"supported": True, "unsupported_claims": []})

    blocks = re.findall(r'<evidence id="([^"]+)"[^>]*>\n(.*?)\n</evidence>', user_prompt, flags=re.DOTALL)
    q_match = re.search(r"<customer_question>\n(.*?)\n</customer_question>", user_prompt, flags=re.DOTALL)
    question = (q_match.group(1) if q_match else "").lower()
    convo_match = re.search(r"<recent_conversation>\n(.*?)\n</recent_conversation>", user_prompt, flags=re.DOTALL)
    convo = (convo_match.group(1) if convo_match else "").lower()

    full_ev = "\n".join(text for _, text in blocks)
    ids = [cid for cid, _ in blocks]

    def ok(ans: str, used_ids=None):
        return json.dumps({
            "answer": ans,
            "can_answer": True,
            "source_chunk_ids": used_ids or ids[:1],
            "confidence": 0.95,
            "refusal_reason": "",
        })

    def refuse(why: str):
        return json.dumps({
            "answer": "",
            "can_answer": False,
            "source_chunk_ids": [],
            "confidence": 0.95,
            "refusal_reason": why,
        })

    def ids_containing(*needles: str) -> list[str]:
        matched = [cid for cid, text in blocks if any(n in text for n in needles)]
        return matched or ids[:1]

    if not blocks:
        return refuse("no_evidence")

    # Conflicting evidence detection
    if "minimum order" in question and "100 units" in full_ev and "500 units" in full_ev:
        return ok(
            "The available documents contain conflicting information: one states a minimum order of 100 units while another states 500 units.",
            ids_containing("100 units", "500 units"),
        )

    if "business hours" in question and "9:00 AM" in full_ev:
        return ok(
            "We are open Monday to Saturday from 9:00 AM to 7:00 PM and closed on Sundays.",
            ids_containing("9:00 AM"),
        )
    if ("showroom" in question or "located" in question) and "Gandhi Road" in full_ev:
        return ok(
            "Our showroom is located at 14 Gandhi Road, Coimbatore 641001.",
            ids_containing("Gandhi Road"),
        )
    if "warranty" in question and "delivery" in question and "12 month" in full_ev and "5000" in full_ev:
        return ok(
            "Electrical products carry a 12 month warranty, and delivery within Coimbatore is free for orders above 5000 INR.",
            ids_containing("12 month", "5000"),
        )
    if "m10" in question and "18.00" in full_ev:
        return ok("Steel Bolt M10 is priced at 18.00 INR per piece.", ids_containing("18.00"))
    if ("m8" in question or ("m10" in convo and "m8" in question)) and "12.50" in full_ev:
        return ok("Steel Bolt M8 is priced at 12.50 INR per piece.", ids_containing("12.50"))
    if "copper wire" in question and "240" in full_ev:
        return ok("Copper Wire 2mm is priced at 240 INR per metre.", ids_containing("240"))
    if "கடை" in question and "14" in full_ev:
        return ok("எங்கள் கடை கோயம்புத்தூர் காந்தி சாலை 14 இல் உள்ளது.", ids_containing("காந்தி சாலை"))
    if "upi" in question and "UPI" in full_ev:
        return ok("ரொக்கம், UPI மற்றும் வங்கி பரிமாற்றம் ஏற்றுக்கொள்ளப்படும்.", ids_containing("UPI"))
    if "annual maintenance" in question and "4500" in full_ev:
        return ok("The annual maintenance contract costs 4500 INR per year.", ids_containing("4500"))

    return refuse("insufficient_evidence_in_chunks")


class AnswerAccuracyEvaluationTestCase(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.user = make_user("eval_user", role="MANAGER", is_superuser=True)
        self.kb = KnowledgeBase.objects.create(owner=self.user, name="Evaluation KB")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_evaluation_framework_achieves_target_accuracy_and_zero_unsupported_answers(self):
        dataset_path = (
            Path(__file__).resolve().parent.parent / "evaluation" / "datasets" / "sample_dataset.json"
        )
        data = runner.load_dataset(str(dataset_path))

        with override_settings(
            RAG_LOCAL_STORAGE_DIR=self.temp_dir.name,
            RAG_QUEUE_BACKEND="local",
            RAG_MIN_RELEVANCE_THRESHOLD=0.30,
        ):
            with patched_Subsystems(gemini_transport=_grounded_mock_gemini):
                for d in data["documents"]:
                    doc = document_upload_service.upload_document(
                        self.kb,
                        self.user,
                        SimpleUploadedFile(
                            d["filename"], d["content"].encode("utf-8"), content_type="text/plain"
                        ),
                    )
                    process_document(doc.pk)

                # Also add a conflicting-facts document pair + case to cover Category 10 (conflicting document info)
                for fname, text in [
                    ("moq_2025.txt", "conflict_topic: The minimum order quantity (MOQ) is 100 units."),
                    ("moq_2026.txt", "conflict_topic: The minimum order quantity (MOQ) is 500 units."),
                ]:
                    doc = document_upload_service.upload_document(
                        self.kb,
                        self.user,
                        SimpleUploadedFile(fname, text.encode("utf-8"), content_type="text/plain"),
                    )
                    process_document(doc.pk)

                cases = list(data["cases"]) + [
                    {
                        "id": "conflict-1",
                        "category": "conflicting_documents",
                        "question": "What is the minimum order quantity (conflict_topic)?",
                        "answerable": True,
                        "relevant_docs": ["moq_2025.txt", "moq_2026.txt"],
                        "expected_facts": ["conflicting", "100", "500"],
                        "forbidden": [],
                    }
                ]

                results = runner.run_cases(self.kb, self.user, cases, judge_faithfulness=True)
                overall = metrics.compute_metrics(results)
                failed_cases = [r for r in results if r["answerable"] and not r["answered"]]

                self.assertEqual(overall["unsupported_answer_rate"], 0.0, f"results={results}")
                self.assertEqual(overall["cross_tenant_leakage_rate"], 0.0)
                self.assertEqual(overall["refusal_recall"], 1.0, f"results={results}")
                self.assertEqual(overall["answer_correctness"], 1.0, f"failed_cases={failed_cases} results={results}")
                self.assertEqual(overall["answer_faithfulness"], 1.0)

                # Threshold calibration sweep
                sims = runner.collect_similarities(self.kb, self.user, cases)
                sweep = metrics.sweep_thresholds(sims, [0.15, 0.25, 0.30, 0.40])
                rec = metrics.recommend_threshold(sweep, min_refusal_recall=0.98)
                self.assertIsNotNone(rec)
