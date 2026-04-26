from __future__ import annotations

import unittest

from pipeline.sop_cleanup import clean_sop_steps


def step(number: int, action: str, expected: str = "The expected screen is displayed.", **extra):
    data = {
        "step_number": number,
        "system": extra.pop("system", "Excel"),
        "action": action,
        "expected_output": expected,
        "confidence": extra.pop("confidence", "high"),
        "screenshot": extra.pop("screenshot", f"screenshots/step_{number}.jpg"),
        "time_sec": float(number * 5),
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

    def test_gold_standard_cleanup_is_demo_ready(self) -> None:
        result = clean_sop_steps(gold_steps())
        removed_numbers = {item["original_step_number"] for item in result["removed_steps"]}
        self.assertIn(30, removed_numbers)
        self.assertIn(31, removed_numbers)
        self.assertIn(4, removed_numbers)
        self.assertTrue(23 <= len(result["steps"]) <= 28)
        self.assertGreaterEqual(result["quality_report"]["quality_score"], 80)
        self.assertEqual(result["quality_report"]["readiness"], "demo_ready")

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


if __name__ == "__main__":
    unittest.main()
