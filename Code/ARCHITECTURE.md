# Fleet Simulator: Architecture & Data Flow

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FLEET SIMULATOR TOOLKIT                         │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Input: CSV      │────▶│ Fleet Simulator  │────▶│  Output: CSV     │
│  (Scenarios)     │     │  (C, compiled)   │     │  (Results)       │
└──────────────────┘     └──────────────────┘     └──────────────────┘
                                │
                                │ (Python script)
                                ▼
                         ┌──────────────────┐
                         │ Analysis Suite   │
                         │  (Python)        │
                         │  • Statistics    │
                         │  • Plot gen.     │
                         │  • JSON export   │
                         └──────────────────┘
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
              Summary.txt  results.png  summary.json
```

## CSV Pipeline

```
scenarios.csv (INPUT)
┌────────────────────────────────────────────────────┐
│ perimeter,num_drones,v_nominal,v_max,sensing_radius│
│ ,nominal_spacing,balancing_policy,...              │
├────────────────────────────────────────────────────┤
│ 100.0,20,1.0,2.0,5.0,5.0,0,0.80,1.5,10.0,0.01,2  │  Line 1: Scenario 1
│ 100.0,20,1.0,2.0,5.0,5.0,1,0.75,1.8,10.0,0.01,2  │  Line 2: Scenario 2
│ ... (20 scenarios)                                  │
└────────────────────────────────────────────────────┘
           │
           │ fleet_simulator
           ▼
results.csv (OUTPUT)
┌─────────────────────────────────────────────────────────────────┐
│ [same input columns],density,coverage,avg_speed,speed_stddev,   │
│ max_gap,avg_gap,drones_active,formation_stability,...           │
├─────────────────────────────────────────────────────────────────┤
│ 100.0,20,...,0.85,85.0,1.087,0.094,3.21,2.87,17,0.823,...      │
│ 100.0,20,...,0.81,81.0,1.156,0.124,3.45,3.02,16,0.756,...      │
│ ...                                                              │
└─────────────────────────────────────────────────────────────────┘
           │
           │ analyze_results.py
           │
      ┌────┴────┬─────────┬──────────┐
      ▼         ▼         ▼          ▼
   stdout     PNG     JSON file   (optional)
 (statistics) (6 plots) (summary)
```

## Simulation Loop (pseudocode)

```c
for each scenario in scenarios.csv {
    
    fleet[0..num_drones-1] = initialize_fleet()
    
    for simulation_step = 1 to MAX_SIMULATION_STEPS {
        
        // Layer 1: PT Autonomy (distributed control)
        for each drone in fleet {
            if drone.alive {
                compute gap_to_pred
                update velocity based on local control law
                update position
            }
        }
        
        // Layer 2: DT Oversight (failure detection & spare insertion)
        if any drone reports loss {
            update DT state estimate
            predictive_simulation_over T_adapt
            if coverage degradation detected {
                insert_spare_at_gap_midpoint()
            }
        }
        
        // Layer 3: Metrics snapshot
        if step % 10 == 0 {
            compute_metrics(fleet) → density, coverage, avg_speed, etc.
        }
    }
    
    write_metrics_to_results.csv
}
```

## Control Law Hierarchy

```
┌──────────────────────────────────────────────────────┐
│       DRONE OPERATIONAL MODES (State Machine)        │
└──────────────────────────────────────────────────────┘

STATE_NOMINAL (Unidirectional)
┌─────────────────────────────────────────────β─────┐
│  Sense: predecessor within radius r_d              │
│  If gap > r_d (loss):        v_cmd = v_max         │
│  Else if gap > 1.2×d_nom:    v_cmd = 1.1×v_nom    │
│  Else if gap < 0.8×d_nom:    v_cmd = 0.9×v_nom    │
│  Else:                        v_cmd = v_nom         │
│  Ramp: v(t) smoothly toward v_cmd                  │
└─────────────────────────────────────────────────────┘
           ▲                              │
           │                              │
     (Entry at init)              (Exit via DT validation)
           │                              │
           ▼                              ▼
┌─────────────────────────────────────────────────────┐
│  STATE_0 (Bidirectional - Joining)                  │
├─────────────────────────────────────────────────────┤
│  Sense: predecessor AND successor within r_d        │
│  Balancing error: gap_pred - d_nom + d_nom - gap_succ
│  v_cmd = v_nom + 0.01 × error                      │
│  (Prevents reverse-cascade during recovery)         │
└─────────────────────────────────────────────────────┘

   [Future extension: STATE_0 → STATE_NOMINAL transition
    once gaps equilibrate AND DT confirms recovery]
```

## Data Structure: Drone Agent

```c
typedef struct {
    double x;              // Position on perimeter (0..perimeter)
    double v;              // Current velocity (m/s)
    double v_nom;          // Nominal velocity (m/s)
    double gap_to_pred;    // Distance to predecessor (m)
    int alive;             // 1=active, 0=failed
    int state;             // 0=STATE_NOMINAL, 1=STATE_0
} Drone;

┌─────────────────────────────────────────────────────┐
│  Drone Fleet (circular linked list conceptually)    │
├─────────────────────────────────────────────────────┤
│  fleet[0]  →  fleet[1]  →  fleet[2]  → ... → fleet[0]
│  x=0.0        x=5.0         x=10.0      (periodic boundary)
│  v=1.0        v=1.1         v=0.9
│  alive=1      alive=0       alive=1
│  state=0      (skipped)     state=0
│
│  If drone[i] fails:
│    drone[i].alive = 0
│    Successor perceives: gap_to_pred > sensing_radius
│    Successor accelerates: v_cmd = v_max
│    Cascade propagates backward
└─────────────────────────────────────────────────────┘
```

## Failure Injection & Recovery Timeline

```
Timeline (simulation steps):

Step 0-100:  Nominal operation (all drones alive, v=v_nom)
             ┌─────────────────────────────────────────┐
             │ density = 1.0, avg_gap ≈ nominal_spacing│
             └─────────────────────────────────────────┘

Step 100:    FAILURE INJECTED (drone randomly selected)
             ┌─────────────────────────────────────────┐
             │ Successor detects loss: gap > r_d        │
             │ → Accelerates to v_max                   │
             │ → Creates gap to successor               │
             │ → Cascade propagates backward            │
             └─────────────────────────────────────────┘

Step 100-150: TRANSITORY PHASE (Cascading Speedup)
             ┌─────────────────────────────────────────┐
             │ density decreases (failed drone gone)    │
             │ avg_speed increases (cascade speedup)    │
             │ max_gap increases (coverage hole opens)  │
             │ formation_stability drops                │
             └─────────────────────────────────────────┘

Step 150:    DT DECISION: Is PT self-adaptation sufficient?
             ┌─────────────────────────────────────────┐
             │ Criterion: density < density_threshold?  │
             │ If YES → Insert spare at max gap        │
             │ If NO  → Monitor and wait               │
             └─────────────────────────────────────────┘

Step 151:    SPARE INSERTION (if triggered)
             ┌─────────────────────────────────────────┐
             │ Newcomer activated at gap midpoint       │
             │ Newcomer enters STATE_0 (bidirectional) │
             │ Existing fleet absorbs via density-bal. │
             │ No reverse cascade (STATE_0 logic)      │
             └─────────────────────────────────────────┘

Step 200-500: RECOVERY PHASE
             ┌─────────────────────────────────────────┐
             │ Drones decelerate to v_nominal          │
             │ Gaps equilibrate to nominal_spacing     │
             │ density gradually increases             │
             │ formation_stability improves            │
             │ (Exponential-like recovery curve)       │
             └─────────────────────────────────────────┘

Step 500-1000: RESTORED NOMINAL
             ┌─────────────────────────────────────────┐
             │ density ≈ 0.95 (mission success!)       │
             │ formation_stability ≈ original          │
             │ avg_speed ≈ v_nominal                   │
             │ Metrics stabilize                       │
             └─────────────────────────────────────────┘
```

## Metrics Computation Timeline

```
Each simulation step:
├─ Update drone positions & velocities
├─ Check for failures
├─ Check for spare insertion need
└─ Every 10 steps: compute & log metrics

Metrics snapshot includes:
┌──────────────────────────────────────────┐
│ density        = num_alive / num_total   │
│ coverage       = 100 × density           │
│ avg_speed      = mean(v[i])              │
│ speed_stddev   = stdev(v[i])             │
│ max_gap        = max(gap_to_pred[i])     │
│ avg_gap        = mean(gap_to_pred[i])    │
│ formation_stab = 1/(1+|avg_gap-d_nom|)   │
│ energy_consumed= sum(v[i])/v_nom         │
│ time_to_recover= steps until density>0.95│
│ recovery_slope = (density-0.5)/duration  │
└──────────────────────────────────────────┘
```

## Python Analysis Pipeline

```
results.csv (multi-scenario output)
    │
    ├─► load_results()
    │   └─► Parse CSV rows into Python dicts
    │
    ├─► group_by_policy()
    │   └─► Organize results by balancing_policy (0,1,2,...)
    │
    ├─► summarize_results()
    │   └─► Text output: per-policy statistics
    │       {μ, σ, min, max} for each metric
    │
    ├─► plot_results()
    │   └─► Matplotlib 6-panel visualization
    │       • Sensing vs density
    │       • Recovery slope boxplot
    │       • Speed-energy scatter
    │       • Formation stability histogram
    │       • Threshold impact scatter
    │       • Recovery latency boxplot
    │
    └─► export_json_summary()
        └─► JSON output for downstream tools
            R, MATLAB, Jupyter, etc.
```

## File Dependency Graph

```
Compile:
  fleet_simulator.c  ──┬─(gcc -lm)──▶  fleet_simulator
                       │
                  Makefile

Runtime:
  scenarios.csv  ──┐
                  ├─▶  fleet_simulator  ──▶  results.csv
       [run_pipeline.sh]
                  │
                  ▼
          analyze_results.py  ◀──┐
                  │              │
          ┌───────┼───────┐      │
          ▼       ▼       ▼      │
      stdout  results.png  results_summary.json
```

## Theoretical Mapping: Paper → Simulator

```
ARCHITECTURE PAPER                    SIMULATOR IMPLEMENTATION
─────────────────────                 ───────────────────────────

PT (Physical Twin)                    fleet[0..num_drones-1] array
├─ Drones                             Each drone struct
├─ Neighbor sensing                   gap_to_pred < sensing_radius
├─ Local control                      update_drone_positions()
└─ Exception reporting                loss detection via gap jump

DT (Digital Twin)                     predictive simulation logic
├─ Fleet state estimation             Last known [position,v,status]
├─ Dead-reckoning                     Forward dynamics from last event
├─ Predictive simulation              simulate_scenario() re-run
└─ Spare staging decision             if density < threshold

Coupling Requirements
├─ CR°1: State fidelity               Perfect state view (no latency)
├─ CR°2: Initialization consistency   All drones init w/ same params
└─ CR°3: Code uniformity              Same control law (update_drone_positions)

Layer 1: PT Autonomy                  STATE_NOMINAL control
├─ Gap detection (r_d)                gap_to_pred check
├─ Loss-triggered acceleration        v_cmd = v_max
└─ Cascade propagation                Backward speedup chain

Layer 2: DT Oversight                 Spare insertion logic
├─ Density monitoring                 Check num_alive vs threshold
├─ Spare staging                      Any-empty-slot insertion
└─ Insertion position                 Midpoint of largest gap

Layer 3: Byzantine Resilience         (Extension point)
└─ False-positive handling            Graceful degradation planned

Layer 4: DSE & Validation             Scenario.csv + analysis
└─ Multi-scenario testing             20 configs tested
```

## Extension Architecture: Adding Byzantine Resilience

```
Current:  Loss Detector → Cascade → Spare Insertion
          (perfectly accurate)

Extended: Loss Detector ──┬──▶ Real Loss (PT handles)
                         │
                         └──▶ False Positive
                              ├─► Option A: Delayed confirmation
                              │   (reduce false positives, → slower recovery)
                              │
                              └─► Option B: DT cross-check
                                  (accept occasional false spare, → fast)

Metrics added:
├─ false_positive_count
├─ over_triggered_spares
├─ missed_losses
└─ latency_of_confirmation
```

---

## Quick Reference: Key Constants

| Constant | Value | Notes |
|----------|-------|-------|
| **MAX_DRONES** | 500 | Compile-time fleet size limit |
| **MAX_SIMULATION_STEPS** | 10,000 | ~100 seconds simulation time (Δt=0.1s) |
| **MAX_SCENARIOS** | 1,000 | Loaded scenarios limit |
| **dt (time step)** | 0.1 s | Forward Euler integration step |
| **accel limit** | 0.5 m/s² | Smooth ramp to commanded velocity |
| **metrics interval** | 10 steps | Capture metrics every 10 steps |

---

This architecture enables **systematic experimental validation** of the PT/DT hybrid autonomy framework described in *Architectural_design.tex*.
