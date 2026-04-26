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


if __name__ == "__main__":
    unittest.main()
