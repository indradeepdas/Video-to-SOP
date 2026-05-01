from __future__ import annotations

import os
import unittest
from unittest import mock

from pipeline.classify import classify_system
from pipeline.clean_ocr import clean_text
from pipeline.cluster import cluster_events, prune_events
from pipeline.generate import _extract_json, generate_steps
from pipeline.validate import group_phases, validate_steps
from pipeline.verify import mark_risks, verify_steps
from worker import _process_name_from_file


class PipelineRuleTests(unittest.TestCase):
    def test_clean_ocr_keeps_business_terms_and_removes_noise(self) -> None:
        raw = "File\nEdit\nSupplier ACME\nPayment terms Net 30\n12:30\n"
        cleaned = clean_text(raw)
        self.assertIn("Supplier ACME", cleaned)
        self.assertIn("Payment terms", cleaned)
        self.assertNotIn("File", cleaned)

    def test_classify_common_systems(self) -> None:
        self.assertEqual(classify_system("SAP company code vendor posting"), "SAP")
        self.assertEqual(classify_system("Excel workbook pivot column"), "Excel")
        self.assertEqual(classify_system("Outlook inbox subject reply"), "Email")
        self.assertEqual(classify_system("Teams chat meeting channel"), "Slack/Teams")

    def test_cluster_prune_removes_duplicates(self) -> None:
        events = [
            {
                "event_id": 1,
                "path": "a.jpg",
                "time_sec": 0,
                "diff_score": 0.2,
                "system": "SAP",
                "clean_text": "SAP invoice supplier review",
            },
            {
                "event_id": 2,
                "path": "b.jpg",
                "time_sec": 4,
                "diff_score": 0.01,
                "system": "SAP",
                "clean_text": "SAP invoice supplier review",
            },
            {
                "event_id": 3,
                "path": "c.jpg",
                "time_sec": 8,
                "diff_score": 0.3,
                "system": "Excel",
                "clean_text": "Excel export invoice amount status",
            },
        ]
        clustered = cluster_events(events)
        pruned = prune_events(clustered, max_events=3)
        self.assertLessEqual(len(pruned), 2)
        self.assertIn("evidence_frame", pruned[0])
        self.assertIn("action_hint", pruned[0])

    def test_risk_marking_and_no_api_sanitization(self) -> None:
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        old_disable = os.environ.get("VIDEO2SOP_DISABLE_OPENAI")
        os.environ["VIDEO2SOP_DISABLE_OPENAI"] = "1"
        try:
            steps = [
                {
                    "event_id": 1,
                    "system": "SAP",
                    "rule_system": "SAP",
                    "action": "Click save for invoice 123456",
                    "expected_output": "Document 900001 is posted",
                    "confidence": "high",
                }
            ]
            marked = mark_risks(steps)
            self.assertTrue(marked[0]["risky"])
            verified = verify_steps(steps)
            self.assertNotIn("123456", verified[0]["action"])
            self.assertEqual(verified[0]["confidence"], "medium")
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key
            if old_disable is None:
                os.environ.pop("VIDEO2SOP_DISABLE_OPENAI", None)
            else:
                os.environ["VIDEO2SOP_DISABLE_OPENAI"] = old_disable

    def test_validation_and_phase_grouping(self) -> None:
        steps = [
            {
                "event_id": 1,
                "system": "MadeUp",
                "rule_system": "Excel",
                "action": "Export the displayed data.",
                "expected_output": "The export is available.",
                "confidence": "high",
            },
            {
                "event_id": 2,
                "system": "MadeUp",
                "rule_system": "Excel",
                "action": "Export the displayed data.",
                "expected_output": "The export is available.",
                "confidence": "high",
            },
        ]
        valid = validate_steps(steps)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["system"], "Excel")
        phases = group_phases(valid)
        self.assertIn("Process in Excel", phases)

    def test_validation_does_not_globally_collapse_repeated_event_rows(self) -> None:
        steps = [
            {
                "event_id": index,
                "system": "Other",
                "rule_system": "Other",
                "action": "Review the visible process screen.",
                "expected_output": "The relevant process information is available on screen.",
                "confidence": "low",
                "screenshot": f"frame_{index}.jpg",
                "screen_state_id": index,
                "start_time_sec": float(index * 15),
            }
            for index in range(1, 36)
        ]
        valid = validate_steps(steps, max_steps=40)
        self.assertEqual(len(valid), 35)
        self.assertEqual(valid[20]["source_event_index"], 21)

    def test_model_json_robustness_and_fallback(self) -> None:
        parsed = _extract_json("```json\n[{\"event_id\":1,\"confidence\":\"weird\"}]\n```")
        self.assertEqual(parsed[0]["event_id"], 1)
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        old_disable = os.environ.get("VIDEO2SOP_DISABLE_OPENAI")
        os.environ["VIDEO2SOP_DISABLE_OPENAI"] = "1"
        try:
            steps = generate_steps(
                [
                    {
                        "event_id": 1,
                        "system": "SAP",
                        "path": "missing.jpg",
                        "clean_text": "SAP invoice supplier",
                        "time_sec": 0,
                    }
                ]
            )
            self.assertEqual(steps[0]["confidence"], "medium")
            self.assertIn("invoice", steps[0]["action"].lower())
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key
            if old_disable is None:
                os.environ.pop("VIDEO2SOP_DISABLE_OPENAI", None)
            else:
                os.environ["VIDEO2SOP_DISABLE_OPENAI"] = old_disable

    def test_generate_marks_diagnostic_fallback_without_openai_or_ocr(self) -> None:
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        old_disable = os.environ.get("VIDEO2SOP_DISABLE_OPENAI")
        os.environ["VIDEO2SOP_DISABLE_OPENAI"] = "1"
        try:
            steps = generate_steps(
                [
                    {
                        "event_id": 1,
                        "system": "Other",
                        "path": "missing.jpg",
                        "clean_text": "",
                        "screen_state_id": 1,
                        "time_sec": 0,
                    }
                ]
            )
            self.assertEqual(steps[0]["generation_source"], "diagnostic_fallback")
            self.assertTrue(steps[0]["diagnostic_only"])
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key
            if old_disable is None:
                os.environ.pop("VIDEO2SOP_DISABLE_OPENAI", None)
            else:
                os.environ["VIDEO2SOP_DISABLE_OPENAI"] = old_disable

    def test_generate_marks_local_ocr_without_openai(self) -> None:
        old_key = os.environ.pop("OPENAI_API_KEY", None)
        old_disable = os.environ.get("VIDEO2SOP_DISABLE_OPENAI")
        os.environ["VIDEO2SOP_DISABLE_OPENAI"] = "1"
        try:
            steps = generate_steps(
                [
                    {
                        "event_id": 1,
                        "system": "SAP",
                        "path": "missing.jpg",
                        "clean_text": "SAP invoice status posted",
                        "time_sec": 0,
                    }
                ]
            )
            self.assertEqual(steps[0]["generation_source"], "local_ocr")
            self.assertFalse(steps[0]["diagnostic_only"])
        finally:
            if old_key:
                os.environ["OPENAI_API_KEY"] = old_key
            if old_disable is None:
                os.environ.pop("VIDEO2SOP_DISABLE_OPENAI", None)
            else:
                os.environ["VIDEO2SOP_DISABLE_OPENAI"] = old_disable

    def test_generate_records_openai_failure(self) -> None:
        stats = {}
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=False):
            with mock.patch("pipeline.generate._call_openai", side_effect=RuntimeError("boom")):
                steps = generate_steps(
                    [
                        {
                            "event_id": 1,
                            "system": "Other",
                            "path": "missing.jpg",
                            "clean_text": "",
                            "screen_state_id": 1,
                            "time_sec": 0,
                        }
                    ],
                    run_stats=stats,
                )
        self.assertEqual(stats["openai_calls_attempted"], 1)
        self.assertEqual(stats["openai_calls_succeeded"], 0)
        self.assertTrue(stats["openai_errors"])
        self.assertTrue(steps[0]["openai_generation_failed"])

    def test_process_name_normalization_strips_downloader_noise(self) -> None:
        name = _process_name_from_file(
            "input.mp4",
            upload_name="YTDown_YouTube_Pivot-Table-Excel-Step-by-Step-Tutorial_Media_dvbLrwD2SpA_001_1080p.mp4",
        )
        self.assertEqual(name, "Pivot Table Excel Step By Step Tutorial")


if __name__ == "__main__":
    unittest.main()
