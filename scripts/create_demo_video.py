from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _draw_screen(title: str, lines: list[str], accent: tuple[int, int, int]) -> np.ndarray:
    frame = np.full((540, 960, 3), 248, dtype=np.uint8)
    cv2.rectangle(frame, (0, 0), (960, 74), accent, -1)
    cv2.putText(frame, title, (32, 47), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    cv2.rectangle(frame, (42, 112), (918, 470), (255, 255, 255), -1)
    cv2.rectangle(frame, (42, 112), (918, 470), (210, 215, 220), 2)
    y = 170
    for line in lines:
        cv2.putText(frame, line, (76, y), cv2.FONT_HERSHEY_SIMPLEX, 0.76, (28, 32, 36), 2)
        y += 56
    return frame


def build_demo_video(video_path: Path) -> Path:
    video_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, 1.0, (960, 540))
    screens = [
        (
            "Customer Portal",
            ["Open customer search", "Search: Acme Retail", "Customer status: Active"],
            (38, 92, 138),
        ),
        (
            "Customer Record",
            ["Open customer profile", "Review account owner and payment terms", "Last activity visible"],
            (38, 92, 138),
        ),
        (
            "Edit Customer Fields",
            ["Update payment terms to Net 30", "Choose priority support flag", "Save button enabled"],
            (66, 117, 88),
        ),
        (
            "Submission",
            ["Submit customer update", "Confirmation: Changes saved", "Audit entry created"],
            (66, 117, 88),
        ),
        (
            "Reports",
            ["Open customer activity report", "Filter to updated customer", "Export report to Excel"],
            (96, 91, 150),
        ),
        (
            "Download Folder",
            ["Validate exported file", "customer_activity_report.xlsx", "Ready for review"],
            (96, 91, 150),
        ),
    ]
    for title, lines, accent in screens:
        frame = _draw_screen(title, lines, accent)
        for _ in range(2):
            writer.write(frame)
    writer.release()
    return video_path


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "jobs" / "demo_input.mp4"
    path = build_demo_video(output)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
