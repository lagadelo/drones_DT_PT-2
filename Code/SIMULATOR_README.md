# Fleet Simulator: Experimental Validation Tool

## Overview

This C-based simulator implements the distributed drone swarm architecture described in *Architectural_design.tex*. It reads CSV scenario parameters, simulates fleet dynamics under loss events, measures key resilience metrics, and outputs results for analysis.

## Key Features

- **CSV-driven experimentation**: Define multiple scenarios with different parameters
- **Failure injection**: Random drone failures with configurable rate and count
- **Spare insertion**: Dynamic insertion of replacement drones at computed gap midpoints
- **Multi-policy support**: Conservative, Aggressive, and Adaptive balancing strategies
- **Comprehensive metrics**: Density, coverage, speed dynamics, gap statistics, formation stability, energy consumption, recovery curves
- **State machine support**: Simulates STATE_NOMINAL (unidirectional) and STATE_0 (bidirectional) balancing

## Baseline `scenario.cfg` Parameters (key=value)

For the baseline/resilience runs driven by `sample_scenario_w*_seed.cfg`:

- `steps`: simulation steps (e.g., 3000)
- `num_losses`: max losses to generate if the loss file is absent (e.g., 15)
- `seed`: RNG seed for loss schedule generation
- `resilience`: 1 to enable spare insertion, 0 to disable
- `min_spare_delay_steps`: minimum steps between a loss and the next spare insertion (e.g., 15)
- `k_sym` (or legacy `w_back`), `k_rep`, `k_sym_rec`, `k_f`, `k_b`, `k_f_rec`, `k_b_rec`, `alpha`, `beta`, `V_cap`, `Vmax`, `V`, `d_star`, `d_safe`, `epsilon`, `dt`, `perimeter`, `n`: control/geometry constants. The local law is now symmetric: $v \leftarrow V + k_{sym} (d_f - d_b)$ with repulsion when $d_b < d_{safe}$ and caps at $V_{cap}$ during recovery.

Spare behavior: inserted at the midpoint of the largest gap after the delay; capped to observed losses and `num_losses`; each spare runs at nominal speed `V` for `incoming_hold_steps` before joining the controller (flagged as `INCOMING` in traces).

## Input CSV Format

```
perimeter,num_drones,v_nominal,v_max,sensing_radius,nominal_spacing,balancing_policy,density_threshold,speed_threshold,adaptation_window,failure_rate,num_failures
```

### Parameter Definitions

| Parameter | Type | Description |
|-----------|------|-------------|
| **perimeter** | double | Total length of patrol circuit (meters) |
| **num_drones** | int | Initial fleet size |
| **v_nominal** | double | Nominal cruise speed (m/s) |
| **v_max** | double | Maximum acceleration speed (m/s) |
| **sensing_radius** | double | r_d: radius for neighbor detection (meters) |
| **nominal_spacing** | double | Desired inter-drone spacing (meters) |
| **balancing_policy** | int | 0=Conservative, 1=Aggressive, 2=Adaptive |
| **density_threshold** | double | Trigger spare insertion when density < threshold |
| **speed_threshold** | double | Max sustained speed before intervention (m/s) |
| **adaptation_window** | double | T_adapt: window for DT decision making (seconds) |
| **failure_rate** | double | Probability of failure per simulation step (0-1) |
| **num_failures** | int | Target number of drones to fail during sim |

## Output CSV Format

The results file extends input columns with computed metrics:

```
[input columns],density,coverage,avg_speed,speed_stddev,max_gap,avg_gap,drones_active,formation_stability,energy_consumed,time_to_recover,recovery_slope
```

### Metric Definitions

| Metric | Description |
|--------|-------------|
| **density** | Fraction of active drones relative to initial fleet |
| **coverage** | Percentage of nominal coverage maintained (simplified: 100 × density) |
| **avg_speed** | Mean velocity of active drones |
| **speed_stddev** | Standard deviation of drone speeds |
| **max_gap** | Largest inter-drone spacing |
| **avg_gap** | Mean inter-drone spacing |
| **drones_active** | Count of active drones post-recovery |
| **formation_stability** | 0-1 score: 1 = perfectly spaced, 0 = disorganized |
| **energy_consumed** | Rough proxy: avg_speed relative to nominal |
| **time_to_recover** | Simulation steps to recover density > 95% post-failure |
| **recovery_slope** | Rate of density increase during recovery phase |

## Usage

### Build

```bash
make
```

### Run with Default Parameters

```bash
make run
# Equivalent to: ./fleet_simulator scenarios.csv results.csv
```

### Run Custom Scenario

```bash
./fleet_simulator my_scenarios.csv my_results.csv
```

### Clean Build Artifacts

```bash
make clean
```

## Balancing Policies Explained

### Policy 0: Conservative
- Drones accelerate only when predecessor is beyond sensing radius
- Settles quickly at nominal spacing
- Lower sustained speeds → less energy depletion
- Slower response to coverage gaps
- **Use case**: Long-endurance missions with stable coverage

### Policy 1: Aggressive  
- Accelerate whenever gap > 1.2× nominal spacing
- Rapid recompaction, maintains high coverage
- Sustained speedup exhausts energy quickly
- Triggers spare insertion sooner
- **Use case**: High-threat scenarios requiring immediate response

### Policy 2: Adaptive
- Threshold adjusts dynamically based on fleet health
- Blends conservative and aggressive behaviors
- Attempts optimal balance between responsiveness and endurance
- *Currently simplified; candidates for extension*

## Architecture Simulation Details

### Fleet Representation
- Drones positioned on 1D circular patrol circuit
- Each drone maintains: position, velocity, gap to predecessor, alive status, state (NOMINAL or 0)
- 1K-step temporal simulation (0.1s dt) = 100 simulation seconds

### Failure Injection
- Random selection of active, NOMINAL-state drones
- Failures occur probabilistically per step
- Failed drones become "invisible" (gap treated as if predecessor is missing)

### Loss Detection
- Each drone updates gap_to_pred each step
- If gap > sensing_radius after loss, drone accelerates (Layer 1: PT autonomy)
- Cascade propagates backward through fleet

### Spare Insertion Logic (Layer 2: DT oversight)
- Trigger: `density < density_threshold`
- Insertion point: midpoint of largest gap
- Newcomer enters STATE_0 (bidirectional balancing)
- Prevents reverse-cascading destabilization

### State Transitions
- STATE_NOMINAL → STATE_0: Upon insertion (manually triggered)
- STATE_0 → STATE_NOMINAL: Not implemented (candidate extension)
- Transition requires DT validation (predictive simulation check)

## Extension Points

### 1. Enhanced Balancing Policies
Modify `update_drone_positions()` to implement:
- PID controller for gap error minimization
- Predictive lookahead (anticipate cascade)
- Energy-aware speed regulation

### 2. Multi-Layer Failure Models
Current: random instantaneous loss. Extend to:
- Gradual degradation (sensor noise increasing)
- Correlated failures (adversarial attacks on fleet segment)
- Byzantine faults (false loss reports matching Paper analysis)

### 3. DT Decision Refinement
Replace threshold-based `try_insert_spare()` with:
- Predictive simulation inside DT (embedded secondary simulator)
- Risk assessment before spare staging
- Historical pattern recognition (escalating threat detection)

### 4. Metrics Enhancement
Add:
- Intrusion window duration (time coverage falls below C_critical)
- Spare insertion latency (time DT detects need → actual insertion)
- Formation coherence (variability in inter-drone spacing)
- Communication load (exception events per simulation step)

### 5. Visualization Output
Extend CSV results with trajectory snapshots:
- Position field for density heatmaps
- Timestamp field for temporal animation
- State field for STATE_0 tracking

## Example Workflow

### Step 1: Create Scenario File

```csv
perimeter,num_drones,v_nominal,v_max,sensing_radius,nominal_spacing,balancing_policy,density_threshold,speed_threshold,adaptation_window,failure_rate,num_failures
100.0,20,1.0,2.0,5.0,5.0,0,0.80,1.5,10.0,0.01,2
100.0,20,1.0,2.0,5.0,5.0,1,0.75,1.8,10.0,0.01,2
100.0,20,1.0,2.0,5.0,5.0,2,0.78,1.6,10.0,0.01,2
```

### Step 2: Build & Run

```bash
gcc -Wall -O2 -o fleet_simulator fleet_simulator.c -lm
./fleet_simulator scenarios.csv results.csv
```

### Step 3: Analyze Results

Open `results.csv` in spreadsheet or Python/R for:
- Policy comparison scatter plots (density vs recovery_slope)
- Sensitivity analysis (sensing_radius → formation_stability)
- Trade-off curves (avg_speed vs energy_consumed)

## Implementation Notes

### Simplifications
- 1D circuit (real perimeter boundaries are polygonal)
- Instantaneous spare insertion (no launch/arrival latency)
- No communication delays (immediate exception reporting)
- Deterministic predecessor-following (ignores noise)

### Assumptions
- Each drone knows its waypoint circuit and perimeter polygon
- Spare drones available at base (infinite supply)
- No adversarial intrusion detection (that logic is in PT/DT arch)
- All measurements are perfect (no sensor noise)

## Theory-to-Implementation Mapping

| Theory (Architecture Paper) | Simulator Implementation |
|-----------------------------|-------------------------|
| STATE NOMINAL unidirectional | `state == 0` in drone struct; predecessor-following logic |
| STATE 0 bidirectional balancing | `state == 1`; gap-balancing error control |
| Loss detection (neighbor radius r_d) | Gap update; compare to sensing_radius |
| Cascading speedup | Velocity ramp logic; backward propagation |
| Spare insertion at gap midpoint | `try_insert_spare()` finds max gap and inserts newcmer |
| DT predictive simulation | `simulate_scenario()` entire flight as forward prediction |
| Density threshold (σ²_max) | `density_threshold` parameter |
| Energy exhaustion monitoring | `avg_speed` vs nominal; triggers spare insertion |

## Performance Characteristics

**Typical runtime** (for 20 scenarios on modern CPU):
- ~1-2 seconds terminal time
- 1K steps × 20 scenarios × O(drone_count) dynamics updates
- CSV I/O overhead negligible

**Memory footprint**:
- ~500 KB (20 scenarios × 500 drones × structure size)
- Scales linearly with num_scenarios and drone count

## Known Limitations & Future Work

1. **STATE_0 Exit Condition**: Currently drones never transition back to STATE_NOMINAL
   - Extension: Implement transition threshold (gaps equalized + DT validation)

2. **DT/PT Coupling Fidelity**: Simulator treats spare insertion as instantaneous
   - Extension: Add launch → waypoint travel latency; DT must account for insertion-point drift

3. **Byzantine Resilience**: No false-positive loss reports modeled
   - Extension: Add parameterized false-positive rate; measure over-triggered spare deployments

4. **Multi-Failure Concurrency**: Failures injected one-by-one
   - Extension: Allow simultaneous failures; stress-test cascade recovery under concurrent losses

5. **Intrusion Detection**: Not simulated (ray-casting algorithm in PT, not tested here)
   - Extension: Add external element positions; measure detection latency and false-positive rate

## References

- See `Architectural_design.tex` for theoretical foundation
- Algorithm~ref{alg:baseline}: distributed control law executed in simulation
- Algorithm~ref{alg:intrusion_detection}: not yet integrated into simulator
- Coupling Requirements (CR°1, CR°2, CR°3): validated implicitly by simulator fidelity

---

**Author**: Fleet Resilience Research Team  
**Contact**: [User email/affiliation]  
**Last Updated**: 2026-02-12
