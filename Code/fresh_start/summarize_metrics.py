#!/usr/bin/env python3
"""Summarize end-of-run and post-loss metrics for many summary CSVs.

Usage:
  python3 fresh_start/summarize_metrics.py --out fresh_start/analysis/metrics.csv fresh_start/runs/*/summary.csv

Writes a compact table per run:
- pre-loss mean/std (average over steps [0, first_loss))
- post-loss mean/std (average over steps (first_loss, end])
- end-window mean/std (last 20%)

This is intended for seed sweeps and compact reporting.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent
LOSSES = CODE / "losses_seeded.csv"


def fmean(values: list[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def load_loss_steps(path: Path) -> list[int]:
    steps: list[int] = []
    if not path.exists():
        return steps
    with path.open() as f:
        next(f, None)
        for line in f:
            parts = line.strip().replace(";", ",").split(",")
            if parts and parts[0].isdigit():
                steps.append(int(parts[0]))
    return sorted(steps)


def load_summary(path: Path) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    with path.open() as f:
        r = csv.DictReader(f, delimiter=";")
        for row in r:
            rows.append(
                {
                    "step": int(row["step"]),
                    "mean_v": float(row["mean_v"]),
                    "std_v": float(row["std_v"]),
                    "mean_gap": float(row["mean_gap"]),
                    "std_gap": float(row["std_gap"]),
                }
            )
    return rows


def window(rows: list[dict[str, float | int]], start: int, end: int) -> dict[str, float]:
    sel = [r for r in rows if start <= int(r["step"]) < end]
    return {
        "mean_v": fmean([float(r["mean_v"]) for r in sel]),
        "std_v": fmean([float(r["std_v"]) for r in sel]),
        "mean_gap": fmean([float(r["mean_gap"]) for r in sel]),
        "std_gap": fmean([float(r["std_gap"]) for r in sel]),
        "n": float(len(sel)),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("summaries", nargs="+", type=Path)
    args = ap.parse_args()

    loss_steps = load_loss_steps(LOSSES)
    first_loss = loss_steps[0] if loss_steps else 0

    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "run",
                "summary_path",
                "first_loss_step",
                "pre_mean_v",
                "pre_std_v",
                "pre_mean_gap",
                "pre_std_gap",
                "post_mean_v",
                "post_std_v",
                "post_mean_gap",
                "post_std_gap",
                "end_mean_v",
                "end_std_v",
                "end_mean_gap",
                "end_std_gap",
            ]
        )

        for summary_path in args.summaries:
            run_name = summary_path.parent.name
            rows = load_summary(summary_path)
            if not rows:
                continue
            last_step = int(rows[-1]["step"]) + 1
            pre = window(rows, 0, first_loss)
            post = window(rows, first_loss + 1, last_step)
            end = window(rows, int(last_step * 0.8), last_step)
            w.writerow(
                [
                    run_name,
                    str(summary_path),
                    first_loss,
                    f"{pre['mean_v']:.6f}",
                    f"{pre['std_v']:.6f}",
                    f"{pre['mean_gap']:.6f}",
                    f"{pre['std_gap']:.6f}",
                    f"{post['mean_v']:.6f}",
                    f"{post['std_v']:.6f}",
                    f"{post['mean_gap']:.6f}",
                    f"{post['std_gap']:.6f}",
                    f"{end['mean_v']:.6f}",
                    f"{end['std_v']:.6f}",
                    f"{end['mean_gap']:.6f}",
                    f"{end['std_gap']:.6f}",
                ]
            )

    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
