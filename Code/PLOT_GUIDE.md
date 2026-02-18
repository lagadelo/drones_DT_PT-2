# How to read the PNG plots (baseline simulator)

All PNGs in `Code/` are generated from:
- a **summary CSV** (`summary_*.csv`) that contains per-step statistics over the *currently alive* drones
- a **trace CSV** (`trace_*.csv`) used to detect when spares are inserted
- a **loss schedule** (`losses_seeded.csv`) used to place the loss markers

## What you see in the plots

### X-axis: `step`
Discrete simulation time step. The actual time is `t = step * dt` seconds (from the scenario `.cfg`).

### Colored line: mean value
- **Speed plots**: colored line = `mean_v` (mean speed of alive drones)
- **Gap plots**: colored line = `mean_gap` (mean inter-drone gap among alive drones)

These values come directly from the summary CSV columns.

### Semi-transparent bars: standard deviation
The bars are **not another mean**: they are the **standard deviation** across alive drones at that step.
- **Speed plots**: bars = `std_v`
- **Gap plots**: bars = `std_gap`

Interpretation:
- small std ⇒ the fleet is close to uniform (all drones have similar speeds / similar gaps)
- large std ⇒ heterogeneity (some drones are much faster than others, or gaps are uneven)

Because plotting a bar at every step would be unreadable, the plot scripts automatically choose a `stride` (power-of-two) to subsample bars.

### Red dashed vertical lines: loss events
Each red dashed line is a loss at a specific step (from `losses_seeded.csv`).

Interpretation:
- immediately after a loss, gaps increase and the controller often speeds up (mean speed rises)
- std bars typically increase right after a loss (the fleet is temporarily non-uniform)

### Dark-green vertical lines: spare insertions
Each dark-green line marks a step where a drone transitions from `alive=0` to `alive=1` in the trace (interpreted as **a spare being deployed/activated**).

Interpretation:
- after a spare insertion, gaps tend to shrink back toward `d_star`
- depending on parameters, you may see an overshoot (“rebound”) where mean speed remains high or gaps oscillate

If reinforcements are too close to losses (or too close to each other) and you only see one merged “peak”, increase:
- `min_spare_delay_steps` (delay after a loss)
- `min_spare_interval_steps` (minimum spacing between spare insertions)

## Where the numbers come from (summary CSV columns)
A typical summary header is:

`step;alive;mean_v;min_v;max_v;std_v;min_gap;max_gap;mean_gap;std_gap`

- `alive`: number of currently alive drones at that step
  - **density** (often mentioned in text) is typically `alive / n_initial`
- `mean_v`, `std_v`: mean and std of speeds across alive drones
- `mean_gap`, `std_gap`: mean and std of gaps across alive drones
- `min_*`/`max_*`: extrema across alive drones

## What each PNG is comparing

### Backpressure plots
- `plot_speed_backpressure.png`: compares **mean speed + std** for `w0.0 / w0.4 / w0.5 / w0.6` runs (seeded losses)
- `plot_gap_backpressure.png`: compares **mean gap + std** for the same runs

These use summary files like `summary_w05_seed.csv` and traces like `trace_w05_seed.csv`.

### Hold-time sweep (incoming_hold_steps)
- `plot_speed_hold_sweep.png`
- `plot_gap_hold_sweep.png`

These keep `k_sym` fixed (w0.5) and vary `incoming_hold_steps` (50/100/200/500/1000). They show how the **incoming window** affects recovery/rebound.

### k_sym sweep at hold=1000
- `plot_speed_wback_sweep.png`
- `plot_gap_wback_sweep.png`

These vary `k_sym` (w0.2/w0.4/w0.5/w0.6/w0.8) while keeping `incoming_hold_steps=1000`.

### k_sym sweep at hold=500
- `plot_speed_k_sym_hold500.png`
- `plot_gap_k_sym_hold500.png`

Same sweep, but with a shorter incoming window (`incoming_hold_steps=500`).

## Regenerating everything

1) (Optional) edit a scenario file (e.g. `sample_scenario_w05_seed.cfg`) or start from `scenario_template.cfg`.

2) Regenerate PNGs:

```bash
python3 Code/generate_pngs.py --regen-data
```

- Add `--force` to overwrite existing summary/trace CSVs.
- Without `--regen-data`, the script only re-plots from existing CSVs.
