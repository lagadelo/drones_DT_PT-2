#!/usr/bin/env python3
"""Plot hold-time sweep for symmetric controller (k_sym=0.5) using fixed losses.

This overlays mean/std of speed and gap for multiple incoming_hold_steps
values while keeping losses constant (losses_seeded.csv).
"""
import csv
import math
from pathlib import Path
import matplotlib.pyplot as plt

BASE = Path(__file__).parent
FIG_SIZE = (8, 4)
DPI = 150
MIN_BAR_PX = 2.0
LOSS_FILE = BASE / "losses_seeded.csv"

VARIANTS = [
    ("hold50", BASE / "summary_w05_hold50.csv", BASE / "trace_w05_hold50.csv"),
    ("hold100", BASE / "summary_w05_hold100.csv", BASE / "trace_w05_hold100.csv"),
    ("hold200", BASE / "summary_w05_hold200.csv", BASE / "trace_w05_hold200.csv"),
    ("hold500", BASE / "summary_w05_hold500.csv", BASE / "trace_w05_hold500.csv"),
    ("hold1000", BASE / "summary_w05_hold1000.csv", BASE / "trace_w05_hold1000.csv"),
]

COLORS = [
    "tab:green",
    "tab:blue",
    "tab:orange",
    "tab:red",
    "tab:purple",
]


def next_power_of_two(x: int) -> int:
    if x <= 1:
        return 1
    return 1 << (x - 1).bit_length()


def compute_auto_stride(summary_path: Path, bars_per_step: int, min_bar_px: float) -> int:
    width_px = FIG_SIZE[0] * DPI
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
        header = f.readline()
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


def get_last_step(summary_path: Path) -> int:
    last_step = 0
    with summary_path.open() as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            last_step = int(row["step"])
    return last_step


def plot_metric(mean_key: str, std_key: str, ylabel: str, title: str, output_name: str):
    stride = compute_auto_stride(VARIANTS[0][1], len(VARIANTS), MIN_BAR_PX)
    loss_steps = load_loss_steps(LOSS_FILE)
    spare_union: set[int] = set()
    for _, _, trace_path in VARIANTS:
        spare_union.update(load_spare_steps(trace_path))
    spare_steps = sorted(spare_union)
    plt.figure(figsize=FIG_SIZE)
    span = max(1, get_last_step(VARIANTS[0][1]))
    units_per_px = span / (FIG_SIZE[0] * DPI)
    bar_w = max(0.2, 0.1 * stride, MIN_BAR_PX * units_per_px)
    offset_scale = 1.1
    force = set(loss_steps)
    for idx, (label, summary_path, _) in enumerate(VARIANTS):
        data = load_summary(summary_path, stride, force)
        x = [r["step"] + (idx - (len(VARIANTS) - 1) / 2) * bar_w * offset_scale for r in data]
        x_line = [r["step"] for r in data]
        y = [r[mean_key] for r in data]
        yerr = [r[std_key] for r in data]
        color = COLORS[idx % len(COLORS)]
        plt.plot(x_line, y, color=color, linewidth=1.6, label=label)
        plt.bar(x, yerr, width=bar_w, alpha=0.35, color=color, label=f"{label} std")
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
    plt.title(f"{title} (stride {stride})")
    plt.legend()
    plt.tight_layout()
    plt.savefig(BASE / output_name, dpi=DPI)
    plt.close()


def main():
    plot_metric("mean_v", "std_v", "speed (m/s)", "Speed vs hold time", "plot_speed_hold_sweep.png")
    plot_metric("mean_gap", "std_gap", "gap (m)", "Gap vs hold time", "plot_gap_hold_sweep.png")


if __name__ == "__main__":
    main()
