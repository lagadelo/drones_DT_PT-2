#!/usr/bin/env python3
import argparse
import csv
import math
from pathlib import Path
import matplotlib.pyplot as plt

BASE = Path(__file__).parent
WEIGHTS = ["w0.0", "w0.4", "w0.5", "w0.6"]
WEIGHT_STEMS = {
    "w0.0": "w0",
    "w0.4": "w04",
    "w0.5": "w05",
    "w0.6": "w06",
}
DEFAULT_LOSS_FILE = BASE / "losses_seeded.csv"
FIG_SIZE = (8, 4)
DPI = 150

MIN_BAR_PX_DEFAULT = 2.0

COLORS = {
    "w0.0": "tab:purple",
    "w0.4": "tab:blue",
    "w0.5": "tab:green",
    "w0.6": "tab:orange",
}


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


def build_runs(summary_suffix: str) -> dict[str, Path]:
    return {w: BASE / f"summary_{WEIGHT_STEMS[w]}_{summary_suffix}.csv" for w in WEIGHTS}


def build_traces(trace_suffix: str) -> dict[str, Path]:
    return {w: BASE / f"trace_{WEIGHT_STEMS[w]}_{trace_suffix}.csv" for w in WEIGHTS}


def get_last_step(summary_path: Path) -> int:
    last_step = 0
    with summary_path.open() as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            last_step = int(row["step"])
    return last_step


def load_loss_steps(path: Path) -> list[int]:
    steps = []
    if not path.exists():
        return steps
    with path.open() as f:
        f.readline()  # header
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
            prev = prev_alive.get(idx, None)
            if prev is not None and prev == 0 and alive == 1:
                spare_steps.add(step)
            prev_alive[idx] = alive
    return sorted(spare_steps)


def detect_losses_from_summary(path: Path, stride: int) -> list[int]:
    steps = []
    last_alive = None
    with path.open() as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            step = int(row["step"])
            if stride > 1 and step % stride != 0:
                continue
            alive = int(row["alive"])
            if last_alive is None:
                last_alive = alive
                continue
            if alive < last_alive:
                steps.append(step)
            last_alive = alive
    return steps


def plot_speed(runs: dict[str, Path], loss_steps: list[int], spare_steps: list[int], stride: int, output_tag: str):
    plt.figure(figsize=FIG_SIZE)
    labels = list(runs.keys())
    force = set(loss_steps)
    for idx, label in enumerate(labels):
        data = load_summary(runs[label], stride, force)
        x = [r["step"] for r in data]
        y = [r["mean_v"] for r in data]
        ystd = [r["std_v"] for r in data]
        lower = [m - s for m, s in zip(y, ystd)]
        upper = [m + s for m, s in zip(y, ystd)]
        plt.plot(x, y, color=COLORS[label], linewidth=1.6, label=f"{label} avg v")
        band_label = "±1σ" if idx == 0 else None
        plt.fill_between(x, lower, upper, color=COLORS[label], alpha=0.20, linewidth=0, label=band_label)
    for s in loss_steps:
        plt.axvline(s, color="red", linestyle="--", linewidth=2.0, alpha=0.9, zorder=5)
    if loss_steps:
        plt.axvline(loss_steps[0], color="red", linestyle="--", linewidth=2.0, alpha=0.9, zorder=5, label="loss")
    for s in spare_steps:
        plt.axvline(s, color="darkgreen", linestyle="-", linewidth=2.0, alpha=0.9, zorder=4)
    if spare_steps:
        plt.axvline(spare_steps[0], color="darkgreen", linestyle="-", linewidth=2.0, alpha=0.9, zorder=4, label="spare")
    plt.xlabel("step")
    plt.ylabel("speed (m/s)")
    plt.title(f"Speed: mean line, ±1σ band (every {stride} steps)")
    plt.legend()
    plt.tight_layout()
    suffix = f"_{output_tag}" if output_tag else ""
    plt.savefig(BASE / f"plot_speed_backpressure{suffix}.png", dpi=DPI)
    plt.close()


def plot_gap(runs: dict[str, Path], loss_steps: list[int], spare_steps: list[int], stride: int, output_tag: str):
    plt.figure(figsize=FIG_SIZE)
    labels = list(runs.keys())
    force = set(loss_steps)
    for idx, label in enumerate(labels):
        data = load_summary(runs[label], stride, force)
        x = [r["step"] for r in data]
        y = [r["mean_gap"] for r in data]
        ystd = [r["std_gap"] for r in data]
        lower = [m - s for m, s in zip(y, ystd)]
        upper = [m + s for m, s in zip(y, ystd)]
        plt.plot(x, y, color=COLORS[label], linewidth=1.6, label=f"{label} mean gap")
        band_label = "±1σ" if idx == 0 else None
        plt.fill_between(x, lower, upper, color=COLORS[label], alpha=0.20, linewidth=0, label=band_label)
    for s in loss_steps:
        plt.axvline(s, color="red", linestyle="--", linewidth=2.0, alpha=0.9, zorder=5)
    if loss_steps:
        plt.axvline(loss_steps[0], color="red", linestyle="--", linewidth=2.0, alpha=0.9, zorder=5, label="loss")
    for s in spare_steps:
        plt.axvline(s, color="darkgreen", linestyle="-", linewidth=2.0, alpha=0.9, zorder=4)
    if spare_steps:
        plt.axvline(spare_steps[0], color="darkgreen", linestyle="-", linewidth=2.0, alpha=0.9, zorder=4, label="spare")
    plt.xlabel("step")
    plt.ylabel("gap (m)")
    plt.title(f"Gap: mean line, ±1σ band (every {stride} steps)")
    plt.legend()
    plt.tight_layout()
    suffix = f"_{output_tag}" if output_tag else ""
    plt.savefig(BASE / f"plot_gap_backpressure{suffix}.png", dpi=DPI)
    plt.close()


def plot_gap_std_only(runs: dict[str, Path], loss_steps: list[int], spare_steps: list[int], stride: int, output_tag: str):
    """Simplified view: plot only std(gap) vs time.

    In the seeded backpressure runs, mean_gap is nearly identical across k,
    while std_gap differentiates the controllers. This plot makes that visible.
    """

    plt.figure(figsize=FIG_SIZE)
    labels = list(runs.keys())
    force = set(loss_steps)
    for label in labels:
        data = load_summary(runs[label], stride, force)
        x = [r["step"] for r in data]
        y = [r["std_gap"] for r in data]
        plt.plot(x, y, color=COLORS[label], linewidth=1.8, label=f"{label} std(gap)")

    for s in loss_steps:
        plt.axvline(s, color="red", linestyle="--", linewidth=2.0, alpha=0.9, zorder=5)
    if loss_steps:
        plt.axvline(loss_steps[0], color="red", linestyle="--", linewidth=2.0, alpha=0.9, zorder=5, label="loss")
    for s in spare_steps:
        plt.axvline(s, color="darkgreen", linestyle="-", linewidth=2.0, alpha=0.9, zorder=4)
    if spare_steps:
        plt.axvline(spare_steps[0], color="darkgreen", linestyle="-", linewidth=2.0, alpha=0.9, zorder=4, label="spare")

    plt.xlabel("step")
    plt.ylabel("std gap (m)")
    plt.title(f"Backpressure: std(gap) only (every {stride} steps)")
    plt.legend()
    plt.tight_layout()
    suffix = f"_{output_tag}" if output_tag else ""
    plt.savefig(BASE / f"plot_gap_backpressure_std{suffix}.png", dpi=DPI)
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="Plot back-pressure variants")
    parser.add_argument("--stride", type=int, default=2, help="sampling stride in steps (default: 2)")
    parser.add_argument(
        "--auto-stride",
        action="store_true",
        help="auto-compute stride (power of two, >=2) to reduce bar overlap based on figure width",
    )
    parser.add_argument(
        "--min-bar-px",
        type=float,
        default=MIN_BAR_PX_DEFAULT,
        help="minimum pixels per bar when auto stride is enabled (default: 2)",
    )
    parser.add_argument("--summary-suffix", type=str, default="seed", help="suffix for summary files (summary_wXX_<suffix>.csv)")
    parser.add_argument("--trace-suffix", type=str, default=None, help="suffix for trace files (trace_wXX_<suffix>.csv), default=summary suffix")
    parser.add_argument("--output-tag", type=str, default="", help="tag appended to output PNG filenames")
    parser.add_argument("--loss-file", type=Path, default=DEFAULT_LOSS_FILE, help="loss file to locate red marker (default: losses_t20.csv)")
    args = parser.parse_args()
    trace_suffix = args.trace_suffix if args.trace_suffix is not None else args.summary_suffix
    runs = build_runs(args.summary_suffix)
    traces = build_traces(trace_suffix)
    if args.auto_stride:
        stride = compute_auto_stride(runs["w0.0"], len(runs), args.min_bar_px)
        print(f"auto stride -> {stride}")
    else:
        stride = max(1, args.stride)
    loss_steps = load_loss_steps(args.loss_file)
    if not loss_steps:
        # fallback: detect from first summary (w0.0)
        loss_steps = detect_losses_from_summary(runs["w0.0"], stride)
    spare_union: set[int] = set()
    for path in traces.values():
        spare_union.update(load_spare_steps(path))
    spare_steps = sorted(spare_union)
    plot_speed(runs, loss_steps, spare_steps, stride, args.output_tag)
    plot_gap(runs, loss_steps, spare_steps, stride, args.output_tag)
    plot_gap_std_only(runs, loss_steps, spare_steps, stride, args.output_tag)


if __name__ == "__main__":
    main()
