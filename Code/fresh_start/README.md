# Fresh-start experiments

This folder contains a clean, self-contained experiment set built on `baseline_simulator`.

Goals:
- Speed bounded to 150% of nominal (`Vmax = 1.5 * V`).
- Simple balancing baseline: drones try to stay at the midpoint between predecessor and follower (equalize front/back gaps).
- Three baseline strategies:
  1) Loss-only (no insertion)
  2) Loss + delayed insertion (100–300 steps after a loss)
  3) Preventive buffer insertion (keep up to 10% extra drones deployed)
- Variants A/B/C as described in the conversation.

## Quick run

From `Code/`:

- Run all experiments + plots + metrics:
  - `python3 fresh_start/run_all.py --regen`

Outputs:
- Runs: `fresh_start/runs/<exp_name>/{summary.csv,trace.csv}`
- Figures: `fresh_start/figures/*.png`
- Metrics: `fresh_start/analysis/metrics.csv`

## Seeds

This use-case run uses the existing `Code/losses_seeded.csv` and the simulator `seed` inside each scenario for deterministic spare-timing RNG.
For broader lessons-learned, use:
- `python3 fresh_start/sweep_seeds.py --scenario <name> --seeds 100`

(Produces aggregate CSVs suitable for boxplots/CI.)
