#!/usr/bin/env python3
"""Seed sweep runner (lessons-learned).

Runs the same scenario multiple times with different simulator seeds.
This impacts the spare timing RNG (loss-to-spare delay and spare intervals), while
keeping the *loss schedule file* fixed (losses_seeded.csv).

For large sweeps you typically want to:
- keep outputs compact (just metrics.csv per seed)
- aggregate later (mean/CI or boxplots)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
CODE = BASE.parent
SIM = CODE / "baseline_simulator"
LOSSES = CODE / "losses_seeded.csv"
SCEN_DIR = BASE / "scenarios"
OUT_DIR = BASE / "analysis" / "seed_sweeps"


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def patch_seed(cfg_text: str, seed: int) -> str:
    lines = []
    replaced = False
    for line in cfg_text.splitlines():
        if line.strip().startswith("seed="):
            lines.append(f"seed={seed}")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        lines.append(f"seed={seed}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, help="scenario filename in fresh_start/scenarios (e.g., baseline_loss_delayed_insertion.cfg)")
    ap.add_argument("--seeds", type=int, default=100)
    ap.add_argument("--start", type=int, default=1)
    args = ap.parse_args()

    cfg_path = SCEN_DIR / args.scenario
    if not cfg_path.exists():
        raise FileNotFoundError(cfg_path)
    if not SIM.exists():
        run(["make"], cwd=CODE)
    if not LOSSES.exists():
        raise FileNotFoundError(LOSSES)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sweep_dir = OUT_DIR / cfg_path.stem
    if sweep_dir.exists():
        shutil.rmtree(sweep_dir)
    sweep_dir.mkdir(parents=True, exist_ok=True)

    cfg_template = cfg_path.read_text(encoding="utf-8")

    summaries: list[Path] = []

    for seed in range(args.start, args.start + args.seeds):
        tmp_cfg = sweep_dir / f"seed_{seed}.cfg"
        tmp_cfg.write_text(patch_seed(cfg_template, seed), encoding="utf-8")
        summary = sweep_dir / f"summary_seed_{seed}.csv"
        trace = sweep_dir / f"trace_seed_{seed}.csv"
        run([str(SIM), str(tmp_cfg), str(LOSSES), str(summary), str(trace)], cwd=CODE)
        summaries.append(summary)

    metrics_csv = sweep_dir / "metrics.csv"
    run(["python3", str(BASE / "summarize_metrics.py"), "--out", str(metrics_csv)] + [str(p) for p in summaries], cwd=CODE)
    print(f"Wrote sweep metrics: {metrics_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
