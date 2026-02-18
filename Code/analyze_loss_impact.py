#!/usr/bin/env python3
"""Analyze loss impact and spare-induced rebound from baseline_simulator outputs.

Computes:
- Speed jump and slope after each loss event
- Peak speed and time-to-peak
- Recovery time to nominal behavior (speed near V and spacing near d_star)
- Optional: spare insertion steps detected from trace (alive 0->1 transitions)

This is intended for paper-friendly tables/figures.

Example:
  python3 analyze_loss_impact.py \
    --summary Code/summary_w05_seed.csv \
    --losses Code/losses_seeded.csv \
    --V 1.0 --d-star 5.0
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class SummaryRow:
    step: int
    alive: int
    mean_v: float
    std_v: float
    mean_gap: float
    std_gap: float


def read_loss_steps(path: Path) -> list[int]:
    if not path.exists():
        return []
    steps: list[int] = []
    with path.open() as f:
        header = f.readline()
        delim = ";" if ";" in header else ","
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.replace(";", ",").split(",")
            if len(parts) < 2:
                continue
            try:
                steps.append(int(parts[0]))
            except ValueError:
                continue
    return sorted(set(steps))


def read_summary(path: Path) -> list[SummaryRow]:
    rows: list[SummaryRow] = []
    with path.open() as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(
                SummaryRow(
                    step=int(row["step"]),
                    alive=int(row["alive"]),
                    mean_v=float(row["mean_v"]),
                    std_v=float(row["std_v"]),
                    mean_gap=float(row["mean_gap"]),
                    std_gap=float(row["std_gap"]),
                )
            )
    rows.sort(key=lambda r: r.step)
    return rows


def read_spare_steps_from_trace(trace_path: Path) -> list[int]:
    if not trace_path or not trace_path.exists():
        return []
    prev_alive: dict[int, int] = {}
    spare_steps: set[int] = set()
    with trace_path.open() as f:
        f.readline()
        for line in f:
            parts = line.strip().split(";")
            if len(parts) < 3:
                continue
            try:
                step = int(parts[0])
                idx = int(parts[1])
                alive = int(parts[2])
            except ValueError:
                continue
            prev = prev_alive.get(idx)
            if prev is not None and prev == 0 and alive == 1:
                spare_steps.add(step)
            prev_alive[idx] = alive
    return sorted(spare_steps)


def index_by_step(rows: Iterable[SummaryRow]) -> dict[int, SummaryRow]:
    return {r.step: r for r in rows}


def linear_slope(y0: float, y1: float, dt_steps: int) -> float:
    if dt_steps <= 0:
        return 0.0
    return (y1 - y0) / dt_steps


def find_peak(rows: list[SummaryRow], start_step: int, window: int) -> tuple[int, float]:
    end_step = start_step + max(1, window)
    best_step = start_step
    best_v = float("-inf")
    for r in rows:
        if r.step < start_step:
            continue
        if r.step > end_step:
            break
        if r.mean_v > best_v:
            best_v = r.mean_v
            best_step = r.step
    return best_step, best_v


def first_recovery_step(
    rows: list[SummaryRow],
    start_step: int,
    V: float,
    d_star: float,
    speed_tol: float,
    gap_tol_frac: float,
    min_consecutive: int,
) -> int | None:
    ok_run = 0
    for r in rows:
        if r.step < start_step:
            continue
        speed_ok = abs(r.mean_v - V) <= speed_tol
        gap_ok = abs(r.mean_gap - d_star) <= gap_tol_frac * d_star
        if speed_ok and gap_ok:
            ok_run += 1
            if ok_run >= max(1, min_consecutive):
                return r.step - (min_consecutive - 1)
        else:
            ok_run = 0
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", type=Path, required=True)
    ap.add_argument("--losses", type=Path, required=True)
    ap.add_argument("--trace", type=Path, default=None)

    ap.add_argument(
        "--V",
        type=float,
        default=None,
        help="Nominal speed. If omitted, inferred from step 0 mean_v.",
    )
    ap.add_argument(
        "--d-star",
        type=float,
        default=None,
        help="Nominal spacing. If omitted, inferred from step 0 mean_gap.",
    )

    ap.add_argument("--pre", type=int, default=25, help="Steps before loss for baseline")
    ap.add_argument("--post", type=int, default=150, help="Steps after loss to analyze")
    ap.add_argument("--slope-window", type=int, default=25, help="Steps after loss for slope")

    ap.add_argument("--speed-tol", type=float, default=0.05, help="Recovery tolerance around V")
    ap.add_argument(
        "--gap-tol-frac",
        type=float,
        default=0.05,
        help="Recovery tolerance as fraction of d_star",
    )
    ap.add_argument("--min-consecutive", type=int, default=10, help="Consecutive steps for recovery")

    args = ap.parse_args()

    summary_rows = read_summary(args.summary)
    loss_steps = read_loss_steps(args.losses)
    spare_steps = read_spare_steps_from_trace(args.trace) if args.trace else []

    if not summary_rows:
        raise SystemExit("Empty summary file.")

    inferred_V = summary_rows[0].mean_v
    inferred_d_star = summary_rows[0].mean_gap
    V = float(args.V) if args.V is not None else float(inferred_V)
    d_star = float(args.d_star) if args.d_star is not None else float(inferred_d_star)

    by_step = index_by_step(summary_rows)

    print("summary_file", str(args.summary))
    print("loss_file", str(args.losses))
    if args.trace:
        print("trace_file", str(args.trace))
    print("V", V)
    print("d_star", d_star)
    if spare_steps:
        print("spare_steps", ",".join(map(str, spare_steps)))
    print()

    if not loss_steps:
        raise SystemExit("No loss steps found.")

    print("step,baseline_mean_v,baseline_mean_gap,peak_step,peak_v,delta_v,slope_v_per_step,recovery_step,recovery_delay")
    for loss_step in loss_steps:
        # Baseline just before loss
        pre0 = max(0, loss_step - args.pre)
        pre_steps = [s for s in range(pre0, loss_step) if s in by_step]
        if pre_steps:
            base_v = sum(by_step[s].mean_v for s in pre_steps) / len(pre_steps)
            base_g = sum(by_step[s].mean_gap for s in pre_steps) / len(pre_steps)
        else:
            base_v = by_step[loss_step].mean_v if loss_step in by_step else float("nan")
            base_g = by_step[loss_step].mean_gap if loss_step in by_step else float("nan")

        peak_step, peak_v = find_peak(summary_rows, loss_step, args.post)
        delta_v = peak_v - base_v

        s0 = loss_step
        s1 = loss_step + args.slope_window
        if s0 in by_step and s1 in by_step:
            slope = linear_slope(by_step[s0].mean_v, by_step[s1].mean_v, args.slope_window)
        else:
            slope = float("nan")

        rec_step = first_recovery_step(
            summary_rows,
            start_step=loss_step,
            V=V,
            d_star=d_star,
            speed_tol=args.speed_tol,
            gap_tol_frac=args.gap_tol_frac,
            min_consecutive=args.min_consecutive,
        )
        rec_delay = (rec_step - loss_step) if rec_step is not None else ""

        print(
            f"{loss_step},{base_v:.6f},{base_g:.6f},{peak_step},{peak_v:.6f},{delta_v:.6f},{slope if slope == slope else ''},{rec_step if rec_step is not None else ''},{rec_delay}"
        )


if __name__ == "__main__":
    main()
