# Fleet Simulator: Quick Start Guide

## Complete Workflow

### 1. Build the Simulator

```bash
cd /path/to/drones_DT_PT
make clean
make
```

Expected output:
```
gcc -Wall -Wextra -O2 -lm -c fleet_simulator.c -o fleet_simulator.o
gcc -Wall -Wextra -O2 -lm -o fleet_simulator fleet_simulator.o -lm
```

### 2. Run Experiments

The project includes a pre-configured `scenarios.csv` with 20 diverse test cases:

```bash
./fleet_simulator scenarios.csv results.csv
```

Expected output:
```
Loaded 20 scenarios from scenarios.csv
Starting simulation of 20 scenarios...
  Scenario 1/20: 20 drones, perimeter=100.0, policy=0
  Scenario 2/20: 20 drones, perimeter=100.0, policy=1
  ...
  Scenario 20/20: 250 drones, perimeter=250.0, policy=1
All simulations completed.
Results written to results.csv
Simulation complete.
```

### 3. Analyze Results

#### Text Summary (basic)
```bash
python3 analyze_results.py results.csv
```

Expected output shows per-policy statistics:
```
======================================================================
FLEET SIMULATOR RESULTS SUMMARY
======================================================================

Total scenarios simulated: 20

Conservative Policy (0)
----------------------------------------------------------------------
  density               → μ=0.8234  σ=0.0456
  coverage             → μ=82.3400  σ=4.5600
  avg_speed            → μ=1.0892  σ=0.1234
  formation_stability   → μ=0.7845  σ=0.0987
  energy_consumed      → μ=1.0892  σ=0.1234
  time_to_recover      → μ=23.4500  σ=5.6700
  recovery_slope       → μ=0.0023  σ=0.0008

Aggressive Policy (1)
...
```

#### Generate Plots
```bash
python3 analyze_results.py results.csv --plot
```

This creates `results.png` with 6-panel visualization:
- Sensing radius vs density maintenance
- Recovery slope comparison (boxplot)
- Speed-energy trade-off scatter
- Formation stability distribution
- Spare insertion threshold impact
- Recovery latency (boxplot)

#### Export JSON Summary (for further analysis)
```bash
python3 analyze_results.py results.csv --json
```

Creates `results_summary.json`:
```json
{
  "Conservative": {
    "density": {
      "mean": 0.823,
      "stdev": 0.045,
      "min": 0.76,
      "max": 0.91,
      "count": 7
    },
    ...
  },
  "Aggressive": { ... },
  "Adaptive": { ... }
}
```

---

## Creating Custom Scenarios

### Example: High-Density Fleet with Aggressive Sensing

Create `custom_scenarios.csv`:

```csv
perimeter,num_drones,v_nominal,v_max,sensing_radius,nominal_spacing,balancing_policy,density_threshold,speed_threshold,adaptation_window,failure_rate,num_failures
500,100,1.0,3.0,8.0,5.0,0,0.80,2.0,20.0,0.02,8
500,100,1.0,3.0,8.0,5.0,1,0.75,2.2,20.0,0.02,8
500,100,1.0,3.0,8.0,5.0,2,0.78,2.1,20.0,0.02,8
```

### Run Custom Scenarios

```bash
./fleet_simulator custom_scenarios.csv custom_results.csv
python3 analyze_results.py custom_results.csv --plot
```

---

## Understanding the Metrics

### Input Parameters

**Fleet Geometry:**
- `perimeter`: Total patrol circuit length
- `nominal_spacing`: Desired distance between adjacent drones
- `sensing_radius`: r_d, max detection distance

**Control:**
- `v_nominal`: Cruise velocity (m/s)
- `v_max`: Max acceleration speed
- `balancing_policy`: 0=Conservative, 1=Aggressive, 2=Adaptive
- `density_threshold`: Spare insertion trigger (fraction of fleet)
- `speed_threshold`: Max sustained speed before DT intervention

**Failure Model:**
- `failure_rate`: Probability per sim step
- `num_failures`: Target count of drones to fail

### Output Metrics

**Coverage & Density:**
- `density`: Ratio of active drones to initial fleet size
- `coverage`: Simplified proxy (100 × density %)

**Speed Dynamics:**
- `avg_speed`: Mean velocity of active fleet
- `speed_stddev`: Variability in individual drone speeds
  - **High σ**: Uneven acceleration → potential cascading
  - **Low σ**: Coordinated balancing → stable formation

**Formation Quality:**
- `avg_gap`: Mean inter-drone spacing
- `max_gap`: Largest gap (intrusion window indicator)
- `formation_stability`: 0-1 score
  - 1.0 = perfect nominal spacing
  - <0.5 = fragmented formation

**Resilience:**
- `time_to_recover`: Simulation steps to restore 95% density
  - **Lower = faster recovery** (better PT autonomy)
  - **Higher = DT intervention delayed** (slower coverage restoration)
- `recovery_slope`: Rate of density increase per step
  - **Steeper slope** = more rapid recovery
  - **Gradual slope** = prolonged degradation

**Energy Proxy:**
- `energy_consumed`: Sum of speed deviations from nominal
  - **~1.0 = nominal speed maintained** (conservative policy)
  - **>1.2 = sustained speedup** (aggressive policy, higher burn rate)

---

## Design-Space Exploration: Typical Questions

### Q1: How does sensing radius affect recovery?
```bash
# Create scenarios with varying r_d
# sensing_radius: 3.0, 4.0, 5.0, 6.0, 7.0, 8.0

# Predict: Larger r_d → earlier loss detection → faster recovery
# Check in results: recovery_slope vs sensing_radius should trend positive
```

### Q2: Which policy minimizes energy while maintaining coverage?
```bash
# Compare across all policies on energy_consumed and coverage
# Conservative: low energy, slower recovery
# Aggressive: high energy, fast recovery
# Adaptive: should balance both

# Use plots to find Pareto frontier
```

### Q3: How many spares are needed for N drones over K failures?
```bash
# Vary num_failures while monitoring final density
# If density < density_threshold, spare insertion triggers

# Extract relationship: failures → spare count → final coverage
```

---

## Extending the Simulator

### Add a Custom Balancing Policy

Edit `fleet_simulator.c`, function `update_drone_positions()`:

```c
} else if (fleet[i].state == 0) {
    // STATE_0: bidirectional balancing (existing)
    ...
}

// Add custom policy:
if (scenario->balancing_policy == 3) {  // My custom policy
    double gap = fleet[i].gap_to_pred;
    double error = gap - scenario->nominal_spacing;
    
    // Example: PID-like control
    double P_gain = 0.5;
    cmd_v = scenario->v_nominal + P_gain * error;
    cmd_v = fmax(scenario->v_nominal * 0.8, fmin(scenario->v_max, cmd_v));
}
```

Rebuild and test:
```bash
make
./fleet_simulator my_scenarios.csv my_results.csv
```

### Add Byzantine Failure Injection

Modify `inject_failure()` to report false losses:

```c
void inject_false_positive(Drone *fleet, Scenario *scenario) {
    int idx = rand() % scenario->num_drones;
    if (fleet[idx].alive) {
        // Drone reports losing predecessor (but doesn't actually lose it)
        // This cascades into unnecessary acceleration → wasted energy
        // DT must detect via predictive simulation
    }
}
```

### Add Intrusion Event Tracking

Create new metric:
```c
int intrusions_detected = 0;
int false_positives = 0;

// During simulation, count intrusion reports vs ground truth
// Compute: precision, recall, latency of detection
```

---

## Performance Tips

### For Large-Scale Experiments

**Scenario count:** 100+ scenarios
**Drone count:** 200-500 per scenario

```bash
# Sequential (simple, single-thread)
./fleet_simulator scenarios.csv results.csv

# Parallel (GNU Parallel, if available)
cat scenarios.csv | parallel --pipe --block 10M \
  "./fleet_simulator /dev/stdin results_{#}.csv"
# Then merge results CSV files
```

### Memory Optimization

If hitting limits (~500 drones max per scenario):
- Reduce MAX_SIMULATION_STEPS
- Use smaller fleet sizes
- Batch scenarios (run in multiple passes)

---

## Example: Reproducing Architecture-Paper Results

To validate the P T/DT architecture described in `Architectural_design.tex`:

```csv
# Baseline nominal condition
100,20,1.0,2.0,5.0,5.0,0,1.0,1.5,10.0,0.0,0

# Single loss, PT-only recovery
100,20,1.0,2.0,5.0,5.0,0,1.0,1.5,10.0,0.1,1

# Single loss, PT+DT with spare (lower threshold)
100,20,1.0,2.0,5.0,5.0,0,0.80,1.5,10.0,0.1,1

# Cascading losses, PT-only
100,20,1.0,2.0,5.0,5.0,0,1.0,1.5,10.0,0.05,4

# Cascading losses, PT+DT
100,20,1.0,2.0,5.0,5.0,0,0.80,1.5,10.0,0.05,4
```

Expected findings:
- **R₀ (baseline)**: density=1.0, coverage=100
- **R₁ (PT-only, 1 loss)**: density≈0.8–0.85, recovery_slope small
- **R₂ (PT+DT, 1 loss)**: density≈0.9–0.95, recovery_slope larger
- **PT+DT advantage**: Faster restoration of coverage via spare insertion

---

## Troubleshooting

### Compile Error: Undefined reference to math functions
```bash
# Solution: Ensure -lm flag is used
gcc -Wall -O2 -o fleet_simulator fleet_simulator.c -lm
```

### Python script: ModuleNotFoundError: No module named 'matplotlib'
```bash
# Solution: Install optional dependencies
pip install matplotlib numpy
# Then re-run:
python3 analyze_results.py results.csv --plot
```

### Simulator produces all zeros in metrics
```bash
# Likely causes:
# 1. Fleet not initialized (check initialize_fleet())
# 2. All drones failed immediately
# 3. Output file permission denied

# Debug: Add verbose output to simulator (modify fleet_simulator.c)
printf("Step %d: %d drones active, avg_speed=%.4f\n", 
       step, num_alive, m->avg_speed);
```

---

## Next Steps

1. **Run baseline scenarios** with `make run`
2. **Analyze results** with `python3 analyze_results.py results.csv --plot`
3. **Design custom scenarios** for your hypothesis
4. **Extend simulator** with Byzantine faults, intrusion detection, etc.
5. **Validate against architecture paper** predictions
6. **Document findings** for review and publication

---

**Document Version**: 1.0  
**Date**: 2026-02-12  
**Contact**: Fleet Resilience Research Team
