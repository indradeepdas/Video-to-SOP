from __future__ import annotations

import unittest

from pipeline.sop_cleanup import clean_sop_steps, validate_chronological_order


def step(number: int, action: str, expected: str = "The expected screen is displayed.", **extra):
    data = {
        "step_number": number,
        "system": extra.pop("system", "Excel"),
        "action": action,
        "expected_output": expected,
        "confidence": extra.pop("confidence", "high"),
        "screenshot": extra.pop("screenshot", f"screenshots/step_{number}.jpg"),
        "time_sec": float(number * 5),
        "source_event_index": number,
    }
    data.update(extra)
    return data


def gold_steps() -> list[dict]:
    actions = [
        "Open the sales data workbook in Excel.",
        "Review the sales data table in the worksheet.",
        "Select the data range including the header row.",
        "Review the worksheet data.",
        "Start creating a table from the selected sales data.",
        "Confirm the table creation settings.",
        "Review the formatted Excel table.",
        "Start creating a PivotTable from the table.",
        "Confirm the PivotTable setup.",
        "Create a new PivotTable from the selected table.",
        "Review the PivotTable Fields pane.",
        "Review the source data table.",
        "Add Salesperson as a row field in the PivotTable.",
        "Add Sales Amount as a value field and summarize it by maximum.",
        "Change the Sales Amount value calculation from maximum back to sum.",
        "Add Region as a column field in the PivotTable.",
        "Move Region from columns to rows.",
        "Reorder row fields so Region appears above Salesperson.",
        "Review the pivot table summarized by salesperson.",
        "Add a second sales amount measure and display it as a percentage.",
        "Rename the percentage measure.",
        "Review the PivotTable Design tab.",
        "Insert a PivotChart.",
        "Remove the percentage series from the PivotChart.",
        "Reapply the sales amount measure to the PivotChart values.",
        "Open the Insert Slicers dialog.",
        "Add a Region slicer.",
        "Apply the Region slicer to include all listed regions.",
        "Review the pivot chart and Region slicer.",
        "Review the presenter outro screen.",
        "Review the presenter outro screen.",
    ]
    return [step(index, action) for index, action in enumerate(actions, start=1)]


class SopCleanupTests(unittest.TestCase):
    def test_removes_presenter_outro_social_banner_end_card_steps(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Open the workbook in Excel."),
                step(2, "Review the presenter outro screen."),
                step(3, "Review the YouTube end card with a social media follow banner."),
            ]
        )
        self.assertEqual(len(result["removed_steps"]), 2)
        self.assertEqual(result["steps"][0]["action"], "Open the workbook in Excel.")

    def test_removes_generic_review_visible_process_screen_steps(self) -> None:
        result = clean_sop_steps([step(1, "Review the visible process screen.")])
        self.assertEqual(result["quality_report"]["step_count_after"], 0)
        self.assertEqual(result["removed_steps"][0]["original_step_number"], 1)

    def test_keeps_validation_steps_that_confirm_business_output(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Validate that the PivotTable shows sales totals by region."),
                step(2, "Verify that the exported file appears in the download folder."),
            ]
        )
        self.assertEqual(len(result["steps"]), 2)
        self.assertEqual(result["removed_steps"], [])

    def test_merges_duplicate_pivottable_creation_steps(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Confirm the PivotTable setup."),
                step(2, "Create a new PivotTable from the selected table."),
            ]
        )
        self.assertEqual(len(result["steps"]), 1)
        self.assertEqual(result["merged_steps"][0]["source_step_numbers"], [1, 2])
        self.assertIn("blank PivotTable worksheet", result["steps"][0]["action"])

    def test_does_not_merge_distinct_pivottable_field_configuration_steps(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Add Salesperson as a row field in the PivotTable."),
                step(2, "Add Sales Amount as a value field and summarize it by maximum."),
                step(3, "Add Region as a column field in the PivotTable."),
            ]
        )
        self.assertEqual(len(result["steps"]), 3)
        self.assertEqual(result["merged_steps"], [])

    def test_assigns_excel_pivottable_phases_correctly(self) -> None:
        result = clean_sop_steps(gold_steps())
        phases = result["phase_summary"]["phase_order"]
        self.assertIn("Prepare source data", phases)
        self.assertIn("Create PivotTable", phases)
        self.assertIn("Configure PivotTable fields", phases)
        self.assertIn("Build chart and slicer", phases)

    def test_impossible_excel_phase_pairs_are_corrected(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Insert a PivotChart.", system="Excel"),
                step(2, "Add a Region slicer.", system="Excel"),
                step(3, "Apply the Region slicer to Los Angeles.", system="Excel"),
            ]
        )
        self.assertEqual(
            [item["phase"] for item in result["steps"]],
            ["Build chart and slicer", "Build chart and slicer", "Validate final output"],
        )

    def test_gold_standard_cleanup_is_demo_ready(self) -> None:
        result = clean_sop_steps(gold_steps())
        removed_numbers = {item["original_step_number"] for item in result["removed_steps"]}
        self.assertIn(30, removed_numbers)
        self.assertIn(31, removed_numbers)
        self.assertIn(4, removed_numbers)
        self.assertTrue(23 <= len(result["steps"]) <= 28)
        self.assertGreaterEqual(result["quality_report"]["quality_score"], 80)
        self.assertEqual(result["quality_report"]["readiness"], "demo_ready")

    def test_excel_benchmark_preserves_coverage_with_event_metadata(self) -> None:
        result = clean_sop_steps(gold_steps(), metadata={"event_segments": 35})
        actions = " ".join(item["action"] for item in result["steps"]).lower()
        self.assertTrue(24 <= len(result["steps"]) <= 30)
        self.assertIn("salesperson", actions)
        self.assertIn("sales amount", actions)
        self.assertIn("pivotchart", actions)
        self.assertIn("region slicer", actions)
        self.assertFalse(result["quality_report"]["coverage_guardrail_triggered"])
        self.assertEqual(result["quality_report"]["readiness"], "demo_ready")

    def test_under_coverage_blocks_demo_ready_and_warns(self) -> None:
        result = clean_sop_steps(
            [step(index, f"Complete operational action {index}.", system="Browser") for index in range(1, 14)],
            metadata={"event_segments": 35},
        )
        self.assertEqual(result["quality_report"]["event_segments"], 35)
        self.assertTrue(result["quality_report"]["coverage_guardrail_triggered"])
        self.assertLess(result["quality_report"]["coverage_ratio_after_cleanup"], 0.60)
        self.assertNotEqual(result["quality_report"]["readiness"], "demo_ready")
        self.assertIn(
            "Possible under-coverage: many workflow events were not represented as SOP steps.",
            result["quality_report"]["warnings"],
        )

    def test_diagnostic_fallback_rows_cannot_be_demo_ready(self) -> None:
        result = clean_sop_steps(
            [
                step(
                    index,
                    f"Review the process state shown at event {index}.",
                    expected=f"Screen state {index} is visible for the next workflow action.",
                    system="Other",
                    confidence="low",
                    generation_source="diagnostic_fallback",
                    diagnostic_only=True,
                )
                for index in range(1, 36)
            ],
            metadata={
                "event_segments": 35,
                "generation_mode": "diagnostic_only",
                "openai_configured": False,
                "ocr_available": False,
                "ocr_non_empty_count": 0,
            },
        )
        self.assertEqual(result["quality_report"]["readiness"], "not_ready")
        self.assertGreater(result["quality_report"]["diagnostic_step_count"], 0)
        self.assertIn(
            "Diagnostic draft mode was used because no production evidence source was available.",
            result["quality_report"]["readiness_blockers"],
        )

    def test_openai_failure_blocks_demo_ready(self) -> None:
        result = clean_sop_steps(
            [step(index, f"Complete operational action {index}.", system="Browser") for index in range(1, 10)],
            metadata={
                "event_segments": 9,
                "generation_mode": "production_vision",
                "openai_configured": True,
                "openai_calls_attempted": 1,
                "openai_calls_succeeded": 0,
                "openai_errors": ["boom"],
                "ocr_available": True,
                "ocr_non_empty_count": 5,
            },
        )
        self.assertNotEqual(result["quality_report"]["readiness"], "demo_ready")
        self.assertIn(
            "OpenAI vision generation was attempted but did not succeed.",
            result["quality_report"]["readiness_blockers"],
        )

    def test_local_ocr_draft_records_mode_and_semantic_counts(self) -> None:
        result = clean_sop_steps(
            [step(index, f"Update customer field {index}.", system="Browser", generation_source="local_ocr") for index in range(1, 6)],
            metadata={
                "event_segments": 5,
                "generation_mode": "local_ocr_draft",
                "openai_configured": False,
                "ocr_available": True,
                "ocr_non_empty_count": 5,
            },
        )
        self.assertEqual(result["quality_report"]["generation_mode"], "local_ocr_draft")
        self.assertEqual(result["quality_report"]["generation_source_counts"]["local_ocr"], 5)
        self.assertEqual(result["quality_report"]["diagnostic_step_count"], 0)

    def test_missing_percentage_configuration_blocks_demo_ready(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Open the sales data workbook in Excel."),
                step(2, "Create a PivotTable from the selected table.", system="Excel"),
                step(3, "Rename the percentage measure.", system="Excel", ocr="Show Values As Percentage"),
                step(4, "Insert a PivotChart.", system="Excel", ocr="PivotChart"),
                step(5, "Apply the Region slicer to Los Angeles.", system="Excel", ocr="Insert Slicer Region"),
            ],
            metadata={"event_segments": 8},
        )
        self.assertIn(
            "Percentage measure configuration may be under-described.",
            result["quality_report"]["missing_action_patterns"],
        )
        self.assertNotEqual(result["quality_report"]["readiness"], "demo_ready")

    def test_distinct_menu_and_dialog_confirmation_actions_are_preserved(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Open the Insert menu.", system="Excel"),
                step(2, "Choose the PivotChart option.", system="Excel"),
                step(3, "Confirm the PivotChart dialog settings.", system="Excel"),
            ],
            metadata={"event_segments": 3},
        )
        self.assertEqual([item["original_step_number"] for item in result["steps"]], [1, 2, 3])
        self.assertEqual(result["merged_steps"], [])

    def test_noisy_output_needs_review_or_not_ready(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Review the presenter outro screen."),
                step(2, "Review the visible process screen."),
                step(3, "Review the screen.", confidence="low"),
            ]
        )
        self.assertIn(result["quality_report"]["readiness"], {"needs_review", "not_ready"})

    def test_empty_cleaned_output_is_not_demo_ready(self) -> None:
        result = clean_sop_steps([step(1, "Review the visible process screen.")])
        self.assertEqual(result["quality_report"]["step_count_after"], 0)
        self.assertEqual(result["quality_report"]["readiness"], "not_ready")

    def test_conservative_cleanup_warns_when_more_than_40_percent_at_risk(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Open the workbook in Excel."),
                step(2, "Review the worksheet data."),
                step(3, "Review the PivotTable Fields pane."),
                step(4, "Review the visible process screen."),
                step(5, "Review the presenter outro screen."),
            ]
        )
        self.assertIn("Cleanup was conservative because too many steps were at risk of removal.", result["quality_report"]["warnings"])
        self.assertGreaterEqual(result["quality_report"]["step_count_after"], 3)

    def test_preserves_screenshot_evidence_fields(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Confirm the PivotTable setup.", screenshot="a.png"),
                step(2, "Create a new PivotTable from the selected table.", screenshot="b.png"),
            ]
        )
        self.assertEqual(result["steps"][0]["screenshot"], "b.png")

    def test_validate_chronological_order_reports_violations(self) -> None:
        report = validate_chronological_order(
            [
                step(1, "Open the app.", start_time_seconds=20),
                step(2, "Search for the customer.", start_time_seconds=10),
            ]
        )
        self.assertFalse(report["is_chronological"])
        self.assertEqual(len(report["violations"]), 1)

    def test_cleanup_preserves_chronological_order_after_phase_assignment(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Submit the customer update.", system="Browser", start_time_seconds=30),
                step(2, "Open the customer web app.", system="Browser", start_time_seconds=0),
                step(3, "Search for the customer record.", system="Browser", start_time_seconds=10),
            ]
        )
        actions = [item["action"] for item in result["steps"]]
        self.assertEqual(actions[0], "Open the customer web app.")
        self.assertEqual(actions[-1], "Submit the customer update.")
        self.assertTrue(result["quality_report"]["chronological_order_valid"])
        self.assertEqual(result["quality_report"]["chronological_violations_count"], 1)

    def test_phase_headers_can_repeat_in_timeline_order(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Open the customer web app.", system="Browser", start_time_seconds=0),
                step(2, "Update the customer status field.", system="Browser", start_time_seconds=10),
                step(3, "Validate that the update appears on the customer record.", system="Browser", start_time_seconds=20),
                step(4, "Update the customer priority field.", system="Browser", start_time_seconds=30),
            ]
        )
        self.assertEqual(
            result["phase_summary"]["phase_order"],
            ["Navigate to record", "Update fields", "Validate result", "Update fields"],
        )

    def test_steps_are_not_moved_to_group_similar_phase_labels(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Open the customer web app.", system="Browser", start_time_seconds=0),
                step(2, "Update the customer status field.", system="Browser", start_time_seconds=10),
                step(3, "Validate that the update appears on the customer record.", system="Browser", start_time_seconds=20),
                step(4, "Update the customer priority field.", system="Browser", start_time_seconds=30),
            ]
        )
        self.assertEqual([item["original_step_number"] for item in result["steps"]], [1, 2, 3, 4])

    def test_merging_uses_time_and_context_not_fixed_step_numbers(self) -> None:
        result = clean_sop_steps(
            [
                step(10, "Open the report page.", system="Browser", start_time_seconds=0),
                step(20, "Open the report page.", system="Browser", start_time_seconds=8),
                step(30, "Export the report.", system="Browser", start_time_seconds=70),
            ]
        )
        self.assertEqual(len(result["merged_steps"]), 1)
        self.assertEqual(result["merged_steps"][0]["source_step_numbers"], [10, 20])

    def test_generic_non_excel_workflow_cleanup(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Open the customer web app.", system="Browser", start_time_seconds=0),
                step(2, "Search for the customer record.", system="Browser", start_time_seconds=10),
                step(3, "Update the customer status field.", system="Browser", start_time_seconds=20),
                step(4, "Submit the changes.", system="Browser", start_time_seconds=30),
                step(5, "Validate that the confirmation message appears.", system="Browser", start_time_seconds=40),
                step(6, "Export the customer report.", system="Browser", start_time_seconds=50),
                step(7, "Review the presenter outro screen.", system="Browser", start_time_seconds=60),
            ]
        )
        self.assertEqual([item["original_step_number"] for item in result["steps"]], [1, 2, 3, 4, 5, 6])
        self.assertEqual(result["removed_steps"][0]["original_step_number"], 7)
        self.assertIn("Navigate to record", result["phase_summary"]["phase_order"])
        self.assertIn("Validate result", result["phase_summary"]["phase_order"])
        self.assertIn("Export, save, or close process", result["phase_summary"]["phase_order"])

    def test_generic_non_excel_workflow_preserves_coverage(self) -> None:
        steps = [
            step(1, "Open the customer web app.", system="Browser", start_time_seconds=0),
            step(2, "Search for the customer record.", system="Browser", start_time_seconds=10),
            step(3, "Open the customer profile.", system="Browser", start_time_seconds=20),
            step(4, "Update the customer status field.", system="Browser", start_time_seconds=30),
            step(5, "Update the customer priority field.", system="Browser", start_time_seconds=40),
            step(6, "Apply the account settings change.", system="Browser", start_time_seconds=50),
            step(7, "Submit the changes.", system="Browser", start_time_seconds=60),
            step(8, "Validate that the confirmation message appears.", system="Browser", start_time_seconds=70),
            step(9, "Export the customer report.", system="Browser", start_time_seconds=80),
            step(10, "Review the presenter outro screen.", system="Browser", start_time_seconds=90),
        ]
        result = clean_sop_steps(steps, metadata={"event_segments": 10})
        self.assertEqual([item["original_step_number"] for item in result["steps"]], list(range(1, 10)))
        self.assertEqual(result["removed_steps"][0]["original_step_number"], 10)
        self.assertFalse(result["quality_report"]["coverage_guardrail_triggered"])

    def test_business_validation_review_steps_are_preserved(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Confirm that the invoice status changed to Posted.", system="SAP"),
                step(2, "Review the visible process screen.", system="SAP"),
            ]
        )
        self.assertEqual(len(result["steps"]), 1)
        self.assertEqual(result["steps"][0]["original_step_number"], 1)

    def test_production_vision_low_step_density_blocks_demo_ready(self) -> None:
        result = clean_sop_steps(
            [
                step(index, f"Update workflow record field {index}.", system="Browser", start_time_seconds=index * 25)
                for index in range(1, 18)
            ],
            metadata={
                "event_segments": 21,
                "generation_mode": "production_vision",
                "video_duration_seconds": 516,
                "target_event_density": 3.0,
                "openai_configured": True,
                "openai_calls_attempted": 2,
                "openai_calls_succeeded": 2,
                "ocr_available": True,
                "ocr_non_empty_count": 17,
            },
        )
        self.assertLess(result["quality_report"]["workflow_density_score"], 3.0)
        self.assertLessEqual(result["quality_report"]["quality_score"], 79)
        self.assertNotEqual(result["quality_report"]["readiness"], "demo_ready")
        self.assertIn(
            "Step density is too low for a production-vision workflow of this duration.",
            result["quality_report"]["readiness_blockers"],
        )

    def test_long_single_step_segment_blocks_demo_ready(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Open the customer web app.", system="Browser", source_segment_duration_seconds=8),
                step(2, "Search for the customer record.", system="Browser", source_segment_duration_seconds=9),
                step(3, "Update the customer status field.", system="Browser", source_segment_duration_seconds=62),
                step(4, "Submit the changes.", system="Browser", source_segment_duration_seconds=7),
                step(5, "Validate that the confirmation message appears.", system="Browser", source_segment_duration_seconds=7),
                step(6, "Export the customer report.", system="Browser", source_segment_duration_seconds=9),
                step(7, "Save the downloaded report.", system="Browser", source_segment_duration_seconds=6),
                step(8, "Close the process.", system="Browser", source_segment_duration_seconds=5),
            ],
            metadata={
                "event_segments": 8,
                "generation_mode": "production_vision",
                "video_duration_seconds": 180,
                "target_event_density": 3.0,
                "openai_configured": True,
                "openai_calls_attempted": 1,
                "openai_calls_succeeded": 1,
                "ocr_available": True,
                "ocr_non_empty_count": 8,
            },
        )
        self.assertEqual(result["quality_report"]["long_segment_single_step_count"], 1)
        self.assertNotEqual(result["quality_report"]["readiness"], "demo_ready")
        self.assertIn(
            "One or more long workflow segments are represented by a single broad step.",
            result["quality_report"]["readiness_blockers"],
        )

    def test_excel_pivot_phase_classifier_uses_action_intent(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Open the sales data workbook in Excel.", system="Excel"),
                step(2, "Format the selected range as an Excel table.", system="Excel"),
                step(3, "Create a PivotTable from the Excel table.", system="Excel"),
                step(4, "Add Salesperson as a row field in the PivotTable.", system="Excel"),
                step(5, "Rename the percentage measure.", system="Excel"),
                step(6, "Insert a PivotChart.", system="Excel"),
                step(7, "Apply the Region slicer to include all listed regions.", system="Excel"),
            ],
            metadata={"event_segments": 7},
        )
        self.assertEqual(
            [item["phase"] for item in result["steps"]],
            [
                "Prepare source data",
                "Create Excel table",
                "Create PivotTable",
                "Configure PivotTable fields",
                "Add calculations and formatting",
                "Build chart and slicer",
                "Validate final output",
            ],
        )

    def test_excel_pivot_benchmark_synonyms_do_not_trigger_false_missing_patterns(self) -> None:
        result = clean_sop_steps(
            [
                step(1, "Display a PivotChart for the sales summary by salesperson.", system="Excel", ocr="PivotChart"),
                step(2, "Open the Insert Slicers dialog for the PivotChart.", system="Excel", ocr="Insert Slicers Region"),
                step(3, "Insert a Region slicer for the PivotChart.", system="Excel", ocr="Region slicer"),
                step(4, "Apply a Region slicer selection to filter the PivotChart.", system="Excel", ocr="Region slicer filtered chart"),
                step(5, "Use the Region slicer to show all regions.", system="Excel", ocr="Region slicer PivotChart all regions"),
            ],
            metadata={"event_segments": 5},
        )
        self.assertNotIn(
            "Slicer application appears in the evidence but is not described operationally.",
            result["quality_report"]["missing_action_patterns"],
        )
        self.assertNotIn(
            "PivotChart creation appears in the evidence but is not described clearly.",
            result["quality_report"]["missing_action_patterns"],
        )


if __name__ == "__main__":
    unittest.main()
