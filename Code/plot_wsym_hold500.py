#!/usr/bin/env python3
"""Plot symmetric gain (k_sym) sweep at fixed hold=500 using seeded losses.

Variants: k_sym in {0.2,0.4,0.5,0.6,0.8} with incoming_hold_steps=500 and losses_seeded.csv.
"""
import csv
import math
from pathlib import Path
import matplotlib.pyplot as plt

BASE = Path(__file__).parent
FIG_SIZE = (8, 4)
Q = 150
MIN_BAR_PX = 2.0
LOSS_FILE = BASE / "losses_seeded.csv"

VARIANTS = [
    ("k0.2", BASE / "summary_w02_hold500.csv", BASE / "trace_w02_hold500.csv"),
    ("k0.4", BASE / "summary_w04_hold500.csv", BASE / "trace_w04_hold500.csv"),
    ("k0.5", BASE / "summary_w05_hold500.csv", BASE / "trace_w05_hold500.csv"),
    ("k0.6", BASE / "summary_w06_hold500.csv", BASE / "trace_w06_hold500.csv"),
    ("k0.8", BASE / "summary_w08_hold500.csv", BASE / "trace_w08_hold500.csv"),
]

COLORS = ["tab:red", "tab:blue", "tab:green", "tab:orange", "tab:purple"]


def next_power_of_two(x: int) -> int:
    if x <= 1:
        return 1
    return 1 << (x - 1).bit_length()


def compute_stride(summary_path: Path, bars_per_step: int, min_bar_px: float) -> int:
    width_px = FIG_SIZE[0] * Q
    target_bars = max(1, int(width_px // max(min_bar_px, 1)))
    last_step = 0
    with summary_path.open() as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            last_step = int(row["step"])
    steps = last_step + 1
    total_bars = steps * bars_per_step
    stride = math.ceil(total_bars / target_bars) if target_bars else 1
    stride = max(2, stride)
    return next_power_of_two(stride)


def load_loss_steps(path: Path) -> list[int]:
    steps = []
    if not path.exists():
        return steps
    with path.open() as f:
        f.readline()
        for line in f:
            parts = line.strip().replace(";", ",").split(",")
            if len(parts) >= 2 and parts[0].isdigit():
                steps.append(int(parts[0]))
    return steps


def load_summary(path: Path, stride: int, force_steps: set[int]):
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            step = int(row["step"])
            if stride > 1 and (step % stride != 0) and (step not in force_steps):
                continue
            rows.append(
                {
                    "step": step,
                    "mean_v": float(row["mean_v"]),
                    "std_v": float(row["std_v"]),
                    "mean_gap": float(row["mean_gap"]),
                    "std_gap": float(row["std_gap"]),
                }
            )
    return rows


def load_spare_steps(trace_path: Path) -> list[int]:
    if not trace_path.exists():
        return []
    prev_alive = {}
    spare_steps = set()
    with trace_path.open() as f:
        f.readline()
        for line in f:
            parts = line.strip().split(";")
            if len(parts) < 3:
                continue
            try:
                step = int(parts[0]); idx = int(parts[1]); alive = int(parts[2])
            except ValueError:
                continue
            prev = prev_alive.get(idx)
            if prev is not None and prev == 0 and alive == 1:
                spare_steps.add(step)
            prev_alive[idx] = alive
    return sorted(spare_steps)


def get_last_step(summary_path: Path) -> int:
    last_step = 0
    with summary_path.open() as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            last_step = int(row["step"])
    return last_step


def plot_metric(mean_key: str, std_key: str, ylabel: str, title: str, output_name: str):
    stride = compute_stride(VARIANTS[0][1], len(VARIANTS), MIN_BAR_PX)
    loss_steps = load_loss_steps(LOSS_FILE)
    spare_union: set[int] = set()
    for _, _, trace_path in VARIANTS:
        spare_union.update(load_spare_steps(trace_path))
    spare_steps = sorted(spare_union)
    plt.figure(figsize=FIG_SIZE)
    force = set(loss_steps)
    for idx, (label, summary_path, _) in enumerate(VARIANTS):
        data = load_summary(summary_path, stride, force)
        x = [r["step"] for r in data]
        y = [r[mean_key] for r in data]
        ystd = [r[std_key] for r in data]
        lower = [m - s for m, s in zip(y, ystd)]
        upper = [m + s for m, s in zip(y, ystd)]
        color = COLORS[idx % len(COLORS)]
        plt.plot(x, y, color=color, linewidth=1.6, label=label)
        band_label = "±1σ" if idx == 0 else None
        plt.fill_between(x, lower, upper, color=color, alpha=0.20, linewidth=0, label=band_label)
    for s in loss_steps:
        plt.axvline(s, color="red", linestyle="--", linewidth=2.0, alpha=0.9, zorder=5)
    if loss_steps:
        plt.axvline(loss_steps[0], color="red", linestyle="--", linewidth=2.0, alpha=0.9, zorder=5, label="loss")
    for s in spare_steps:
        plt.axvline(s, color="darkgreen", linestyle="-", linewidth=2.0, alpha=0.9, zorder=4)
    if spare_steps:
        plt.axvline(spare_steps[0], color="darkgreen", linestyle="-", linewidth=2.0, alpha=0.9, zorder=4, label="spare")
    plt.xlabel("step")
    plt.ylabel(ylabel)
    plt.title(f"{title}: mean line, ±1σ band (stride {stride})")
    plt.legend()
    plt.tight_layout()
    plt.savefig(BASE / output_name, dpi=Q)
    plt.close()


def main():
    plot_metric("mean_v", "std_v", "speed (m/s)", "Speed vs k_sym (hold=500)", "plot_speed_k_sym_hold500.png")
    plot_metric("mean_gap", "std_gap", "gap (m)", "Gap vs k_sym (hold=500)", "plot_gap_k_sym_hold500.png")


if __name__ == "__main__":
    main()
