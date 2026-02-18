#!/usr/bin/env python3
"""Quick numeric sanity-check for the paper plots.

Prints pre-loss vs post-loss vs end-of-run averages for mean/std of:
- speed (mean_v/std_v)
- gap (mean_gap/std_gap)

This is intentionally simple and dependency-free.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

BASE = Path(__file__).parent


def fmean(values: list[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def load_loss_steps(path: Path) -> list[int]:
    steps: list[int] = []
    if not path.exists():
        return steps
    with path.open() as f:
        next(f, None)  # header
        for line in f:
            parts = line.strip().replace(";", ",").split(",")
            if parts and parts[0].isdigit():
                steps.append(int(parts[0]))
    return sorted(steps)


def load_summary(path: Path) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    with path.open() as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(
                {
                    "step": int(row["step"]),
                    "alive": int(row["alive"]),
                    "mean_v": float(row["mean_v"]),
                    "std_v": float(row["std_v"]),
                    "mean_gap": float(row["mean_gap"]),
                    "std_gap": float(row["std_gap"]),
                }
            )
    return rows


def window_stats(rows: list[dict[str, float | int]], start: int, end: int) -> dict[str, float]:
    sel = [r for r in rows if start <= int(r["step"]) < end]
    return {
        "mean_v": fmean([float(r["mean_v"]) for r in sel]),
        "mean_gap": fmean([float(r["mean_gap"]) for r in sel]),
        "std_v": fmean([float(r["std_v"]) for r in sel]),
        "std_gap": fmean([float(r["std_gap"]) for r in sel]),
        "n": float(len(sel)),
    }


def fmt(stats: dict[str, float]) -> str:
    return (
        f"mean_v={stats['mean_v']:.4f} std_v={stats['std_v']:.4f} "
        f"mean_gap={stats['mean_gap']:.4f} std_gap={stats['std_gap']:.4f} (n={int(stats['n'])})"
    )


def main() -> None:
    loss_steps = load_loss_steps(BASE / "losses_seeded.csv")
    first_loss = loss_steps[0] if loss_steps else 0

    print("losses_seeded.csv")
    print("  loss steps (first 12):", loss_steps[:12], "total", len(loss_steps))
    print("  first_loss:", first_loss)

    print("\nBACKPRESSURE (seed)")
    for label, stem in [("w0.0", "w0"), ("w0.4", "w04"), ("w0.5", "w05"), ("w0.6", "w06")]:
        rows = load_summary(BASE / f"summary_{stem}_seed.csv")
        last_step = int(rows[-1]["step"]) + 1
        pre = window_stats(rows, 0, first_loss)
        post = window_stats(rows, first_loss + 1, last_step)
        end = window_stats(rows, int(last_step * 0.8), last_step)
        print(f"  {label} pre:  {fmt(pre)}")
        print(f"       post: {fmt(post)}")
        print(f"       end:  {fmt(end)}")

    print("\nHOLD SWEEP (w0.5) end-of-run (last 20%)")
    for hold in [50, 100, 200, 500, 1000]:
        rows = load_summary(BASE / f"summary_w05_hold{hold}.csv")
        last_step = int(rows[-1]["step"]) + 1
        end = window_stats(rows, int(last_step * 0.8), last_step)
        print(f"  hold{hold:4d}: {fmt(end)}")

    print("\nK_SYM SWEEP (hold=1000) end-of-run (last 20%)")
    for w, stem in [(0.2, "w02"), (0.4, "w04"), (0.5, "w05"), (0.6, "w06"), (0.8, "w08")]:
        rows = load_summary(BASE / f"summary_{stem}_hold1000.csv")
        last_step = int(rows[-1]["step"]) + 1
        end = window_stats(rows, int(last_step * 0.8), last_step)
        print(f"  k={w:0.1f}: {fmt(end)}")

    print("\nK_SYM SWEEP (hold=500) end-of-run (last 20%)")
    for w, stem in [(0.2, "w02"), (0.4, "w04"), (0.5, "w05"), (0.6, "w06"), (0.8, "w08")]:
        rows = load_summary(BASE / f"summary_{stem}_hold500.csv")
        last_step = int(rows[-1]["step"]) + 1
        end = window_stats(rows, int(last_step * 0.8), last_step)
        print(f"  k={w:0.1f}: {fmt(end)}")


if __name__ == "__main__":
    main()
