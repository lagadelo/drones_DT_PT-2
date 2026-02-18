#!/usr/bin/env python3
"""Plot one experiment time-series (mean±std) for speed and gap.

Reads simulator summary CSV (step;mean_v;std_v;mean_gap;std_gap) and plots:
- mean_v with ±1σ band
- mean_gap with ±1σ band
Also overlays loss (red dashed) and spare insertions (green) if trace is provided.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


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


def load_loss_steps(path: Path) -> list[int]:
    if not path.exists():
        return []
    steps: list[int] = []
    with path.open() as f:
        next(f, None)
        for line in f:
            parts = line.strip().replace(";", ",").split(",")
            if parts and parts[0].isdigit():
                steps.append(int(parts[0]))
    return sorted(steps)


def load_spare_steps(trace_path: Path) -> list[int]:
    if not trace_path.exists():
        return []
    prev_alive: dict[int, int] = {}
    spare_steps: set[int] = set()
    with trace_path.open() as f:
        next(f, None)
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


def plot_band(ax, x: list[int], y: list[float], s: list[float], *, color: str, label: str):
    lower = [m - st for m, st in zip(y, s)]
    upper = [m + st for m, st in zip(y, s)]
    ax.plot(x, y, color=color, linewidth=1.8, label=label)
    ax.fill_between(x, lower, upper, color=color, alpha=0.20, linewidth=0, label="±1σ")


def add_markers(ax, loss_steps: list[int], spare_steps: list[int]):
    for s in loss_steps:
        ax.axvline(s, color="red", linestyle="--", linewidth=1.6, alpha=0.85)
    for s in spare_steps:
        ax.axvline(s, color="darkgreen", linestyle="-", linewidth=1.4, alpha=0.85)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--summary", type=Path, required=True)
    ap.add_argument("--trace", type=Path, required=True)
    ap.add_argument("--losses", type=Path, required=True)
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()

    rows = load_summary(args.summary)
    x = [int(r["step"]) for r in rows]

    loss_steps = load_loss_steps(args.losses)
    spare_steps = load_spare_steps(args.trace)

    # speed
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=150)
    plot_band(
        ax,
        x,
        [float(r["mean_v"]) for r in rows],
        [float(r["std_v"]) for r in rows],
        color="tab:blue",
        label="mean speed",
    )
    add_markers(ax, loss_steps, spare_steps)
    ax.set_xlabel("step")
    ax.set_ylabel("speed")
    ax.set_title(f"{args.name} — speed")
    ax.legend(loc="best")
    fig.tight_layout()
    args.outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.outdir / f"{args.name}_speed.png")
    plt.close(fig)

    # gap
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=150)
    plot_band(
        ax,
        x,
        [float(r["mean_gap"]) for r in rows],
        [float(r["std_gap"]) for r in rows],
        color="tab:orange",
        label="mean gap",
    )
    add_markers(ax, loss_steps, spare_steps)
    ax.set_xlabel("step")
    ax.set_ylabel("gap")
    ax.set_title(f"{args.name} — gap")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(args.outdir / f"{args.name}_gap.png")
    plt.close(fig)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
