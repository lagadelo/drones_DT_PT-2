#!/usr/bin/env python3
"""Fresh-start experiment runner.

Runs a curated set of scenarios into fresh_start/runs/, then generates:
- per-run time-series PNGs (speed and gap)
- a single metrics.csv summary

This intentionally does not touch the legacy Code/*.png pipeline.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
from dataclasses import dataclass
from pathlib import Path

BASE = Path(__file__).resolve().parent
CODE = BASE.parent
SIM = CODE / "baseline_simulator"
LOSSES = CODE / "losses_seeded.csv"

SCEN_DIR = BASE / "scenarios"
RUNS_DIR = BASE / "runs"
FIG_DIR = BASE / "figures"
AN_DIR = BASE / "analysis"


@dataclass(frozen=True)
class Experiment:
    name: str
    scenario: Path


EXPERIMENTS: list[Experiment] = [
    Experiment("baseline_loss_only", SCEN_DIR / "baseline_loss_only.cfg"),
    Experiment("baseline_loss_delayed", SCEN_DIR / "baseline_loss_delayed_insertion.cfg"),
    Experiment("baseline_preventive_buffer", SCEN_DIR / "baseline_preventive_buffer.cfg"),
    Experiment("variantA_delayed", SCEN_DIR / "variantA_delayed_insertion.cfg"),
    Experiment("variantC_delayed", SCEN_DIR / "variantC_delayed_insertion.cfg"),
]

# Variant B sweep: incoming_hold_steps duration effect (spares forced at nominal speed)
VARIANT_B_HOLDS = [0, 50, 100, 200, 500, 1000]


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def ensure_dirs() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    AN_DIR.mkdir(parents=True, exist_ok=True)


def regen_one(name: str, scenario_path: Path, *, tag: str = "") -> tuple[Path, Path]:
    out_dir = RUNS_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = out_dir / f"summary{tag}.csv"
    trace = out_dir / f"trace{tag}.csv"
    run([str(SIM), str(scenario_path), str(LOSSES), str(summary), str(trace)], cwd=CODE)
    return summary, trace


def write_variant_b_scenarios(tmp_dir: Path) -> list[Experiment]:
    """Create temporary per-hold scenarios (minimal, deterministic)."""

    template = (SCEN_DIR / "baseline_loss_delayed_insertion.cfg").read_text(encoding="utf-8")
    experiments: list[Experiment] = []
    for hold in VARIANT_B_HOLDS:
        name = f"variantB_hold{hold}"
        cfg = tmp_dir / f"{name}.cfg"
        cfg.write_text(
            template
            + "\n# --- Variant B override ---\n"
            + f"incoming_hold_steps={hold}\n"
            + "incoming_v=1.0\n",
            encoding="utf-8",
        )
        experiments.append(Experiment(name, cfg))
    return experiments


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


def plot_timeseries(exp_name: str, summary: Path, trace: Path) -> None:
    run(
        [
            "python3",
            str(BASE / "plot_timeseries.py"),
            "--name",
            exp_name,
            "--summary",
            str(summary),
            "--trace",
            str(trace),
            "--losses",
            str(LOSSES),
            "--outdir",
            str(FIG_DIR),
        ],
        cwd=CODE,
    )


def analyze_metrics(all_runs: list[tuple[str, Path]]) -> None:
    """Write a compact table with end-of-run metrics."""

    out_csv = AN_DIR / "metrics.csv"
    run(["python3", str(BASE / "summarize_metrics.py"), "--out", str(out_csv)] + [str(p) for _, p in all_runs], cwd=CODE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen", action="store_true", help="Re-run all simulations and re-generate all PNGs/CSVs")
    ap.add_argument("--build", action="store_true", help="Run make first")
    args = ap.parse_args()

    ensure_dirs()

    if args.build or args.regen:
        run(["make"], cwd=CODE)

    if not SIM.exists():
        raise FileNotFoundError(f"Missing {SIM}. Run with --build.")
    if not LOSSES.exists():
        raise FileNotFoundError(f"Missing {LOSSES}.")

    all_runs: list[tuple[str, Path]] = []

    # Core experiments
    for exp in EXPERIMENTS:
        out_dir = RUNS_DIR / exp.name
        summary = out_dir / "summary.csv"
        trace = out_dir / "trace.csv"
        if args.regen or (not summary.exists()) or (not trace.exists()):
            summary, trace = regen_one(exp.name, exp.scenario)
        all_runs.append((exp.name, summary))
        plot_timeseries(exp.name, summary, trace)

    # Variant B sweep
    tmp_dir = RUNS_DIR / "_tmp_scenarios"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for exp in write_variant_b_scenarios(tmp_dir):
        out_dir = RUNS_DIR / exp.name
        summary = out_dir / "summary.csv"
        trace = out_dir / "trace.csv"
        if args.regen or (not summary.exists()) or (not trace.exists()):
            summary, trace = regen_one(exp.name, exp.scenario)
        all_runs.append((exp.name, summary))
        plot_timeseries(exp.name, summary, trace)

    analyze_metrics(all_runs)

    print("Fresh-start outputs:")
    print(f"  figures: {FIG_DIR}")
    print(f"  metrics: {AN_DIR / 'metrics.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
