from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from pipeline.segmentation import (
    adaptive_threshold,
    build_initial_segments,
    find_boundary_candidates,
    reject_scroll_only_segments,
    segment_frames,
    select_segment_evidence,
    token_jaccard,
)
from pipeline.video import _average_hash


def _write_frame(path: Path, title: str, body: str, color: tuple[int, int, int]) -> dict:
    frame = np.full((360, 640, 3), 245, dtype=np.uint8)
    cv2.rectangle(frame, (0, 0), (640, 55), color, -1)
    cv2.putText(frame, title, (25, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    y = 125
    for line in body.split("\n"):
        cv2.putText(frame, line, (40, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (25, 25, 25), 2)
        y += 55
    cv2.imwrite(str(path), frame)
    return {
        "frame_id": int(path.stem.split("_")[-1]),
        "time_sec": float(path.stem.split("_")[-1]),
        "path": str(path),
        "width": 640,
        "height": 360,
        "diff_score": 0.0,
        "image_hash": _average_hash(frame),
    }


class SegmentationTests(unittest.TestCase):
    def test_adaptive_threshold_selects_spikes(self) -> None:
        metrics = [{"boundary_score": score, "time_sec": i, "metric_index": i} for i, score in enumerate([0, 0.01, 0.02, 0.5, 0.02, 0.55])]
        threshold = adaptive_threshold(metrics)
        candidates, _ = find_boundary_candidates(metrics, max_segments=4, min_stable_seconds=1)
        self.assertGreater(threshold["threshold"], 0.02)
        self.assertTrue(any(candidate["metric_index"] in {3, 5} for candidate in candidates))

    def test_ocr_jaccard_detects_content_changes(self) -> None:
        self.assertGreater(token_jaccard("supplier invoice amount", "supplier invoice status"), 0.4)
        self.assertLess(token_jaccard("supplier invoice amount", "teams meeting chat"), 0.4)

    def test_scroll_only_segments_collapse(self) -> None:
        segments = [
            {
                "event_id": 1,
                "system": "SAP",
                "ocr_text": "supplier invoice amount status",
                "screen_state_id": 1,
                "boundary_score": 0.2,
                "segment_frame_count": 2,
            },
            {
                "event_id": 2,
                "system": "SAP",
                "ocr_text": "supplier invoice amount status reviewed",
                "screen_state_id": 1,
                "boundary_score": 0.05,
                "segment_frame_count": 2,
            },
        ]
        collapsed = reject_scroll_only_segments(segments)
        self.assertEqual(len(collapsed), 1)
        self.assertTrue(collapsed[0]["scroll_collapsed"])

    def test_synthetic_sap_excel_sap_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frames = []
            specs = [
                ("SAP Invoice", "Supplier invoice worklist", (32, 88, 120)),
                ("SAP Invoice", "Supplier invoice worklist", (32, 88, 120)),
                ("Excel Export", "Supplier Invoice Amount Status", (30, 120, 60)),
                ("Excel Export", "Supplier Invoice Amount Status", (30, 120, 60)),
                ("SAP Posting", "Document status visible", (32, 88, 120)),
                ("SAP Posting", "Document status visible", (32, 88, 120)),
            ]
            for index, (title, body, color) in enumerate(specs):
                frames.append(_write_frame(root / f"frame_{index}.jpg", title, body, color))
            result = segment_frames(
                frames,
                max_segments=6,
                max_ocr_frames=6,
                ocr_dir=root / "ocr",
                ambiguous_reviews=0,
            )
            self.assertGreaterEqual(len(result["event_segments"]), 2)
            self.assertLessEqual(len(result["event_segments"]), 5)
            self.assertGreaterEqual(len(result["screen_states"]), 2)

    def test_recurring_screen_state_is_not_globally_dropped(self) -> None:
        metrics = [
            {
                "metric_index": i,
                "time_sec": i,
                "path": f"frame_{i}.jpg",
                "boundary_score": 0.4 if i in {2, 4} else 0.01,
                "visual_score": 0.01,
                "diff_score": 0.01,
                "image_hash": "aaaa" if i in {0, 1, 4, 5} else "bbbb",
                "confidence_components": {},
            }
            for i in range(6)
        ]
        candidates, _ = find_boundary_candidates(metrics, max_segments=4, min_stable_seconds=1)
        segments = build_initial_segments(metrics, candidates, max_segments=4)
        self.assertGreaterEqual(len(segments), 3)

    def test_long_operational_span_is_forced_split(self) -> None:
        metrics = [
            {
                "metric_index": i,
                "time_sec": float(i * 10),
                "path": f"frame_{i}.jpg",
                "boundary_score": 0.04 if i in {3, 6, 9} else 0.005,
                "visual_score": 0.03 if i in {3, 6, 9} else 0.004,
                "diff_score": 0.01,
                "image_hash": f"{i:016x}",
                "confidence_components": {"visual": 0.03 if i in {3, 6, 9} else 0.004},
            }
            for i in range(13)
        ]
        segments = build_initial_segments(
            metrics,
            candidates=[],
            max_segments=10,
            max_segment_duration_seconds=30.0,
        )
        self.assertGreaterEqual(len(segments), 4)
        self.assertTrue(any(segment.get("forced_split") for segment in segments))
        self.assertLessEqual(max(segment["end_time_sec"] - segment["start_time_sec"] for segment in segments), 35.0)

    def test_duplicate_hash_skip_keeps_high_boundary_segments_for_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = root / "first.jpg"
            second = root / "second.jpg"
            first.write_bytes(b"x")
            second.write_bytes(b"y")
            evidence = select_segment_evidence(
                [
                    {"event_id": 1, "stable_frame": str(first), "image_hash": "00ffffffffffffff", "boundary_score": 0.01},
                    {"event_id": 2, "stable_frame": str(second), "image_hash": "00ffffffffffffff", "boundary_score": 0.31},
                ],
                max_frames=4,
            )
            self.assertEqual(len(evidence), 2)


if __name__ == "__main__":
    unittest.main()
