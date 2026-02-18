#!/usr/bin/env python3
"""Generate the PNG figures in Code/.

This script is intentionally simple:
- Optionally (re)build + (re)run the baseline simulator to regenerate the summary/trace CSVs
- Run the existing plotting scripts to (re)generate the PNG files

Typical usage:
  python3 Code/generate_pngs.py
  python3 Code/generate_pngs.py --regen-data
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parent


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def regen_one(cfg: Path, losses: Path, summary: Path, trace: Path) -> None:
    exe = BASE / "baseline_simulator"
    if not exe.exists():
        raise FileNotFoundError(f"Missing {exe}. Run with --build or --regen-data.")
    run([str(exe), str(cfg), str(losses), str(summary), str(trace)], cwd=BASE)


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate PNG plots for the baseline simulator")
    ap.add_argument(
        "--regen-data",
        action="store_true",
        help="Re-run baseline_simulator to regenerate the required summary/trace CSV inputs",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="With --regen-data: regenerate even if output CSVs already exist",
    )
    ap.add_argument(
        "--build",
        action="store_true",
        help="Build baseline_simulator via make before regenerating data",
    )
    args = ap.parse_args()

    try:
        import matplotlib  # noqa: F401
    except ModuleNotFoundError:
        print("ERROR: matplotlib is not installed for this Python.")
        print("Install it with: python3 -m pip install --user matplotlib")
        return 2

    losses_seeded = BASE / "losses_seeded.csv"

    # Data required by plot scripts (filenames are hardcoded in those scripts).
    data_jobs: list[tuple[Path, Path, Path, Path]] = []

    # backpressure plot (seed)
    data_jobs += [
        (BASE / "sample_scenario_w0_seed.cfg", losses_seeded, BASE / "summary_w0_seed.csv", BASE / "trace_w0_seed.csv"),
        (BASE / "sample_scenario_w04_seed.cfg", losses_seeded, BASE / "summary_w04_seed.csv", BASE / "trace_w04_seed.csv"),
        (BASE / "sample_scenario_w05_seed.cfg", losses_seeded, BASE / "summary_w05_seed.csv", BASE / "trace_w05_seed.csv"),
        (BASE / "sample_scenario_w06_seed.cfg", losses_seeded, BASE / "summary_w06_seed.csv", BASE / "trace_w06_seed.csv"),
    ]

    # hold sweep (w05)
    for hold in [50, 100, 200, 500, 1000]:
        stem = f"w05_hold{hold}"
        data_jobs.append(
            (
                BASE / f"sample_scenario_{stem}.cfg",
                losses_seeded,
                BASE / f"summary_{stem}.csv",
                BASE / f"trace_{stem}.csv",
            )
        )

    # k_sym sweeps (hold=500 and hold=1000)
    for kstem in ["w02", "w04", "w05", "w06", "w08"]:
        for hold in [500, 1000]:
            stem = f"{kstem}_hold{hold}"
            data_jobs.append(
                (
                    BASE / f"sample_scenario_{stem}.cfg",
                    losses_seeded,
                    BASE / f"summary_{stem}.csv",
                    BASE / f"trace_{stem}.csv",
                )
            )

    if args.build or args.regen_data:
        run(["make"], cwd=BASE)

    if args.regen_data:
        for cfg, losses, summary, trace in data_jobs:
            if not cfg.exists():
                raise FileNotFoundError(f"Missing scenario cfg: {cfg}")
            if not losses.exists():
                raise FileNotFoundError(f"Missing losses file: {losses}")
            if (not args.force) and summary.exists() and trace.exists():
                continue
            regen_one(cfg, losses, summary, trace)

    # Generate PNGs
    run([sys.executable, str(BASE / "plot_backpressure.py"), "--summary-suffix", "seed", "--auto-stride"])
    run([sys.executable, str(BASE / "plot_hold_sweep.py")])
    run([sys.executable, str(BASE / "plot_wback_sweep.py")])
    run([sys.executable, str(BASE / "plot_wsym_hold500.py")])

    print("PNG plots generated in Code/:")
    for name in [
        "plot_speed_backpressure.png",
        "plot_gap_backpressure.png",
        "plot_gap_backpressure_std.png",
        "plot_speed_hold_sweep.png",
        "plot_gap_hold_sweep.png",
        "plot_speed_wback_sweep.png",
        "plot_gap_wback_sweep.png",
        "plot_speed_k_sym_hold500.png",
        "plot_gap_k_sym_hold500.png",
    ]:
        p = BASE / name
        if p.exists():
            print(f"  - {p.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
