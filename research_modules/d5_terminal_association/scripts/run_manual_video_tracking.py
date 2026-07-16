#!/usr/bin/env python3
"""Track multiple manually initialized local targets in an offline video."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = MODULE_ROOT.parents[1]
SRC = MODULE_ROOT / "src"
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d5_terminal_association.manual_video_tracker import (  # noqa: E402
    ManualVideoTrackingError,
    parse_rois,
    select_rois_from_first_frame,
    track_manual_rois_in_video,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("research_modules/b.mp4"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=MODULE_ROOT / "outputs" / "manual_video_tracking" / "b_csrt",
    )
    parser.add_argument(
        "--rois",
        help="headless ROI list in selection order: 'x,y,w,h;x,y,w,h;...'",
    )
    parser.add_argument("--tracker", choices=("csrt", "kcf"), default="csrt")
    parser.add_argument(
        "--association",
        choices=("tracker", "bright_hungarian"),
        default="tracker",
        help="optional one-to-one bright-target association after tracker proposals",
    )
    parser.add_argument("--blob-contrast-threshold", type=float, default=12.0)
    parser.add_argument("--association-gate-px", type=float, default=20.0)
    parser.add_argument("--display", action="store_true", help="show tracking; q/ESC exits")
    parser.add_argument("--tail-length", type=int, default=30)
    parser.add_argument("--codec", default="mp4v")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        rois = parse_rois(args.rois) if args.rois else select_rois_from_first_frame(args.input)
        result = track_manual_rois_in_video(
            args.input,
            rois=rois,
            output_dir=args.output_dir,
            tracker_backend=args.tracker,
            association_backend=args.association,
            display=args.display,
            tail_length=args.tail_length,
            codec=args.codec,
            blob_contrast_threshold=args.blob_contrast_threshold,
            association_gate_px=args.association_gate_px,
        )
    except (ManualVideoTrackingError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"output_video={result.output_video_path.resolve()}")
    print(f"records_csv={result.records_csv_path.resolve()}")
    print(f"summary_json={result.summary_json_path.resolve()}")
    for track in result.summary.tracks:
        print(
            f"{track.local_track_id}: valid={track.valid_frame_count} "
            f"lost={track.lost_frame_count} final={track.final_status}"
        )
    print(f"duplicate_measurement_count={result.summary.duplicate_measurement_count}")
    print(f"minimum_center_separation_px={result.summary.minimum_center_separation_px}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
