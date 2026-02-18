#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

/* ================================================================
   FLEET SIMULATOR: Multi-scenario drone swarm dynamics simulator
   Reads CSV parameters, simulates fleet operations under failures,
   outputs metrics including coverage, density, balancing, recovery.
   ================================================================ */

#define MAX_DRONES 20000
#define MAX_SCENARIOS 1000
#define MAX_SIMULATION_STEPS 5000
#define BUFFER_SIZE 1024

/* ================================================================
   DATA STRUCTURES
   ================================================================ */

typedef struct {
    double x, y;           /* Position along perimeter circuit */
    double v;              /* Current velocity */
    double v_nom;          /* Nominal velocity */
    double gap_to_pred;    /* Distance to predecessor */
    int alive;             /* 1 if active, 0 if failed */
    int state;             /* STATE_NOMINAL (0) or STATE_0 (1) for joining */
    double time_in_incoming;  /* Duration in INCOMING mode (for three-phase control) */
    int phase;             /* Phase: 1=soft entry, 2=positioning, 3=normal (used when state=INCOMING) */
} Drone;

typedef struct {
    double perimeter;
    int num_drones;          /* Total capacity (can include spare capacity) */
    int initial_active;      /* Drones active at start (<= num_drones) */
    double v_nominal;
    double v_max;
    double sensing_radius;
    double nominal_spacing;
    
    /* Balancing policy parameters */
    /* Policy codes (new):
       0 = predecessor-only (no back-pressure)
       1 = symmetric predecessor/successor
       2 = balanced with back-pressure factor 0.4
       3 = balanced with back-pressure factor 0.5
       4 = balanced with back-pressure factor 0.6
       5 = VP-C (state-aware) + three-phase spare insertion
       Legacy policies (<=2) are kept compatible. */
    int balancing_policy;
    double neighbor_balance_factor; /* Additional scaling of back-pressure (default 1.0) */
    double density_threshold;      /* Trigger spare insertion (legacy) */
    double speed_threshold;        /* Max sustained speed before intervention */
    double adaptation_window;      /* T_adapt in seconds */
    
    /* Spare insertion / antifragility */
    double spare_trigger_ratio;    /* Trigger when alive / initial_active < ratio */
    double spare_target_factor;    /* Target active count = initial_active * factor */
    
    /* Failure model */
    double failure_rate;   /* Failures per simulation step */
    int num_failures;      /* Total failures to inject (can be derived from strike_fraction) */
    double strike_fraction;/* If >0, overrides num_failures = strike_fraction * initial_active */
    int failure_distribution; /* 0=random, 1=spatial_clustered, 2=temporal_cascade */
    unsigned int seed;     /* Reproducible per-scenario seed (0 => time-based) */
} Scenario;

typedef struct {
    double density;
    double coverage;
    double avg_speed;
    double speed_stddev;
    double max_gap;
    double avg_gap;
    double peak_gap;
    double num_drones_active;
    double formation_stability; /* 0-1, how tightly packed */
    double energy_consumed;     /* Rough estimate from speed */
    double time_to_recover;     /* Steps until recovery after failure */
    double recovery_slope;      /* Rate of recovery */
    double oscillation_integral;/* Sum of speed stddev over time */
    int    oscillation_samples; /* Samples counted */
    double oscillation_metric;  /* Average speed stddev (proxy for oscillations) */
} Metrics;

/* ================================================================
   UTILITY FUNCTIONS
   ================================================================ */

double gaussian_random(double mean, double stddev) {
    /* Box-Muller transform for Gaussian samples */
    double u1 = (double)rand() / RAND_MAX;
    double u2 = (double)rand() / RAND_MAX;
    double z0 = sqrt(-2.0 * log(u1)) * cos(2.0 * M_PI * u2);
    return mean + z0 * stddev;
}

double uniform_random(double min, double max) {
    return min + (max - min) * ((double)rand() / RAND_MAX);
}

/* ================================================================
   CSV I/O
   ================================================================ */

int read_scenarios_csv(const char *filename, Scenario *scenarios, int *num_scenarios) {
    FILE *f = fopen(filename, "r");
    if (!f) {
        fprintf(stderr, "Error: Cannot open input file %s\n", filename);
        return -1;
    }
    
    char line[BUFFER_SIZE];
    int count = 0;
    
    /* Skip header */
    if (fgets(line, sizeof(line), f) == NULL) {
        fclose(f);
        return -1;
    }
    
    while (fgets(line, sizeof(line), f) && count < MAX_SCENARIOS) {
        Scenario *s = &scenarios[count];
        
        /* Parse extended CSV (backward compatible):
           perimeter,num_drones,v_nominal,v_max,sensing_radius,nominal_spacing,
           balancing_policy,density_threshold,speed_threshold,adaptation_window,
              failure_rate,num_failures,failure_distribution,
              initial_active,spare_trigger_ratio,spare_target_factor,
              neighbor_balance_factor,strike_fraction,seed
        */
          int result = sscanf(line, "%lf,%d,%lf,%lf,%lf,%lf,%d,%lf,%lf,%lf,%lf,%d,%d,%d,%lf,%lf,%lf,%lf,%u",
                   &s->perimeter, &s->num_drones, &s->v_nominal, &s->v_max,
                   &s->sensing_radius, &s->nominal_spacing, &s->balancing_policy,
                   &s->density_threshold, &s->speed_threshold, &s->adaptation_window,
                   &s->failure_rate, &s->num_failures, &s->failure_distribution,
                         &s->initial_active, &s->spare_trigger_ratio, &s->spare_target_factor,
                         &s->neighbor_balance_factor, &s->strike_fraction, &s->seed);
        
        if (result < 12) {
            continue;
        }
        
        /* Defaults for optional fields */
        if (result < 13) s->failure_distribution = 0;
        if (result < 14) s->initial_active = s->num_drones;
        if (result < 15) s->spare_trigger_ratio = 0.9;
        if (result < 16) s->spare_target_factor = 1.0;
        if (result < 17) s->neighbor_balance_factor = 1.0;
        if (result < 18) s->strike_fraction = 0.0;
        if (result < 19) s->seed = 0;
        
        /* Ensure capacity covers antifragility target */
        int required_capacity = (int)ceil(s->initial_active * s->spare_target_factor);
        if (s->num_drones < required_capacity) {
            s->num_drones = required_capacity;
        }
        if (s->initial_active > s->num_drones) {
            s->initial_active = s->num_drones;
        }
        
        /* Derive failures from strike_fraction if provided */
        if (s->strike_fraction > 0.0) {
            s->num_failures = (int)round(s->strike_fraction * s->initial_active);
        }
        
        count++;
    }
    
    fclose(f);
    *num_scenarios = count;
    printf("Loaded %d scenarios from %s\n", count, filename);
    return 0;
}

int write_results_csv(const char *filename, Scenario *scenarios, Metrics *metrics, 
                      int num_results) {
    FILE *f = fopen(filename, "w");
    if (!f) {
        fprintf(stderr, "Error: Cannot write to %s\n", filename);
        return -1;
    }
    
    /* Header */
    fprintf(f, "perimeter,num_drones,v_nominal,v_max,sensing_radius,nominal_spacing,"
               "balancing_policy,density_threshold,speed_threshold,adaptation_window,"
               "failure_rate,num_failures,failure_distribution,seed,"
               "density,coverage,avg_speed,speed_stddev,max_gap,avg_gap,"
               "drones_active,formation_stability,energy_consumed,time_to_recover,recovery_slope\n");
    
    for (int i = 0; i < num_results; i++) {
        Scenario *s = &scenarios[i];
        Metrics *m = &metrics[i];
        
        fprintf(f, "%lf,%d,%lf,%lf,%lf,%lf,%d,%lf,%lf,%lf,%lf,%d,%d,%u,"
                   "%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf,%lf\n",
                s->perimeter, s->num_drones, s->v_nominal, s->v_max,
                s->sensing_radius, s->nominal_spacing, s->balancing_policy,
            s->density_threshold, s->speed_threshold, s->adaptation_window,
            s->failure_rate, s->num_failures, s->failure_distribution, s->seed,
                m->density, m->coverage, m->avg_speed, m->speed_stddev,
                m->max_gap, m->avg_gap, m->num_drones_active, m->formation_stability,
                m->energy_consumed, m->time_to_recover, m->recovery_slope);
    }
    
    fclose(f);
    printf("Results written to %s\n", filename);
    return 0;
}

/* ================================================================
   FLEET INITIALIZATION
   ================================================================ */

void initialize_fleet(Drone *fleet, Scenario *scenario) {
    int n = scenario->num_drones;
    double spacing = scenario->nominal_spacing;
    double perimeter = scenario->perimeter;
    
    for (int i = 0; i < n; i++) {
        fleet[i].x = fmod(i * spacing, perimeter);  /* Fixed: use fmod for doubles */
        fleet[i].y = 0;  /* 1D circuit */
        fleet[i].v = scenario->v_nominal;
        fleet[i].v_nom = scenario->v_nominal;
        fleet[i].gap_to_pred = spacing;
        fleet[i].alive = (i < scenario->initial_active) ? 1 : 0;
        fleet[i].state = 0;  /* STATE_NOMINAL */
        fleet[i].time_in_incoming = 0.0;
        fleet[i].phase = 0;
    }
}

/* ================================================================
   FAILURE INJECTION WITH DISTRIBUTION MODES
   ================================================================ */

void inject_failure(Drone *fleet, Scenario *scenario, int *failures_injected, int step) {
    /* Randomly select a drone to fail based on distribution mode */
    if (*failures_injected >= scenario->num_failures) return;
    
    int target_idx = -1;
    int attempts = 0;
    
    switch (scenario->failure_distribution) {
        
        case 0: /* RANDOM: uniform distribution across fleet */
        {
            while (attempts < 100) {
                int idx = rand() % scenario->num_drones;
                if (fleet[idx].alive && fleet[idx].state == 0) {
                    target_idx = idx;
                    break;
                }
                attempts++;
            }
            break;
        }
        
        case 1: /* SPATIAL CLUSTERED: failures concentrated in fleet segment */
        {
            /* Select a random cluster center, then pick near it */
            int cluster_center = rand() % scenario->num_drones;
            int cluster_radius = scenario->num_drones / 5;  /* 20% of fleet */
            
            while (attempts < 100) {
                int offset = (rand() % (2 * cluster_radius + 1)) - cluster_radius;
                int idx = (cluster_center + offset + scenario->num_drones) % scenario->num_drones;
                if (fleet[idx].alive && fleet[idx].state == 0) {
                    target_idx = idx;
                    break;
                }
                attempts++;
            }
            break;
        }
        
        case 2: /* TEMPORAL CASCADE: failures spread across time (exponential-like) */
        {
            /* Early failures less likely; increases exponentially */
            double cascade_progression = (double)step / MAX_SIMULATION_STEPS;
            double cascade_factor = cascade_progression * cascade_progression;  /* exponential */
            
            if (uniform_random(0, 1) < cascade_factor) {
                /* Find neighbor of previously failed drone for cascade effect */
                int attempts_to_find_prev = 0;
                while (attempts_to_find_prev < 100) {
                    int idx = rand() % scenario->num_drones;
                    if (fleet[idx].alive == 0) {  /* Found a failed drone */
                        /* Try to fail its neighbors */
                        int succ_idx = (idx + 1) % scenario->num_drones;
                        if (fleet[succ_idx].alive && fleet[succ_idx].state == 0) {
                            target_idx = succ_idx;
                            break;
                        }
                        int pred_idx = (idx - 1 + scenario->num_drones) % scenario->num_drones;
                        if (fleet[pred_idx].alive && fleet[pred_idx].state == 0) {
                            target_idx = pred_idx;
                            break;
                        }
                    }
                    attempts_to_find_prev++;
                }
                
                /* Fallback to random if cascade didn't find target */
                if (target_idx < 0) {
                    while (attempts < 100) {
                        int idx = rand() % scenario->num_drones;
                        if (fleet[idx].alive && fleet[idx].state == 0) {
                            target_idx = idx;
                            break;
                        }
                        attempts++;
                    }
                }
            }
            break;
        }
        
        default: /* Unknown mode, fallback to random */
        {
            while (attempts < 100) {
                int idx = rand() % scenario->num_drones;
                if (fleet[idx].alive && fleet[idx].state == 0) {
                    target_idx = idx;
                    break;
                }
                attempts++;
            }
            break;
        }
    }
    
    if (target_idx >= 0) {
        fleet[target_idx].alive = 0;
        (*failures_injected)++;
    }
}

/* ================================================================
   FLEET DYNAMICS SIMULATION
   ================================================================ */

void update_drone_positions(Drone *fleet, Scenario *scenario, double dt) {
    int n = scenario->num_drones;
    double perimeter = scenario->perimeter;
    double r_d = scenario->sensing_radius;
    double nom_spacing = scenario->nominal_spacing;
    
    /* First pass: update gaps and detect losses */
    for (int i = 0; i < n; i++) {
        if (!fleet[i].alive) continue;
        
        int pred_idx = (i - 1 + n) % n;
        
        /* Find nearest alive predecessor */
        while (!fleet[pred_idx].alive && pred_idx != i) {
            pred_idx = (pred_idx - 1 + n) % n;
        }
        
        double pred_x = fleet[pred_idx].x;
        double my_x = fleet[i].x;
        
        /* Circular distance */
        double gap = fmod(pred_x - my_x + perimeter, perimeter);
        fleet[i].gap_to_pred = gap;
    }
    
    /* Second pass: update velocities based on balancing policy */
    for (int i = 0; i < n; i++) {
        if (!fleet[i].alive) continue;
        
        double gap = fleet[i].gap_to_pred;
        double cmd_v = scenario->v_nominal;
        int succ_idx = (i + 1) % n;
        int succ_state = fleet[succ_idx].state;  /* VP-C: detect if successor is INCOMING */
        
        /* Compute predecessor-following term */
        double gap_error = gap - nom_spacing;
        double k_f = 0.5;  /* baseline front gain */
        double k_f_rec = 2.0;  /* recovery front gain */
        double k_b = 0.5;  /* baseline back gain */
        double k_b_rec = 2.0;  /* recovery back gain */
        
        /* Detect recovery condition: large gap (loss) or small gap (compression) */
        int recovery_mode = (gap > 1.2 * nom_spacing) || (fleet[succ_idx].gap_to_pred < 0.8 * nom_spacing);
        
        double effective_k_f = recovery_mode ? k_f_rec : k_f;
        double effective_k_b = recovery_mode ? k_b_rec : k_b;
        
        /* Apply gain schedule: nonlinear gain for large errors */
        double gain_schedule = 1.0;
        if (fabs(gap_error) > 0.1) {
            gain_schedule = 1.0 + 0.5 * (fabs(gap_error) / nom_spacing);
        }
        
        if (fleet[i].state == 0) {
            /* STATE_NOMINAL: unidirectional predecessor-following (standard balancing policy) */
            cmd_v = scenario->v_nominal + effective_k_f * gain_schedule * gap_error;
            
            /* Policy-specific adjustments */
            if (scenario->balancing_policy == 0) {
                /* Conservative: weak recovery, reduced gain scheduling */
                effective_k_f = 0.3 + (recovery_mode ? 0.7 : 0.0);
                gain_schedule = 1.0;  /* no nonlinearity */
                cmd_v = scenario->v_nominal + effective_k_f * gap_error;
            } else if (scenario->balancing_policy == 1) {
                /* Aggressive: strong recovery, strong gain scheduling */
                effective_k_f = 0.7 + (recovery_mode ? 1.5 : 0.0);
                gain_schedule = 1.0 + 0.8 * (fabs(gap_error) / nom_spacing);
                cmd_v = scenario->v_nominal + effective_k_f * gain_schedule * gap_error;
            } else if (scenario->balancing_policy == 2) {
                /* Adaptive: moderate balancing with bidirectional awareness (if successor not joining) */
                effective_k_f = 0.5 + (recovery_mode ? 0.8 : 0.0);
                gain_schedule = 1.0 + 0.4 * (fabs(gap_error) / nom_spacing);
                
                /* VP-C logic: check if successor is in INCOMING mode, disable k_b if so */
                double back_pressure = 0.0;
                if (succ_state == 0) {  /* successor is in BASELINE, apply back-pressure */
                    double succ_gap_error = fleet[succ_idx].gap_to_pred - nom_spacing;
                    back_pressure = 0.3 * succ_gap_error;  /* proportional to successor's gap error */
                } else {
                    /* succ_state == 1: successor is INCOMING (joining spare), disable back-pressure */
                    back_pressure = 0.0;
                }
                cmd_v = scenario->v_nominal + effective_k_f * gain_schedule * gap_error - back_pressure;
            } else if (scenario->balancing_policy == 3) {
                /* VP-C (Adaptive Sensing): enable neighbor-aware state adaptation */
                effective_k_f = 0.5 + (recovery_mode ? 0.8 : 0.0);
                gain_schedule = 1.0 + 0.4 * (fabs(gap_error) / nom_spacing);
                
                /* VP-C: disable back-pressure during spare insertion */
                double back_pressure = 0.0;
                if (succ_state == 0) {  /* successor is BASELINE, full bidirectional control */
                    double succ_gap_error = fleet[succ_idx].gap_to_pred - nom_spacing;
                    back_pressure = effective_k_b * succ_gap_error;
                } else {
                    /* succ_state == 1: successor is INCOMING, zero back-pressure (VP-C key insight) */
                    back_pressure = 0.0;
                }
                cmd_v = scenario->v_nominal + effective_k_f * gain_schedule * gap_error - back_pressure;
            }
        } else {
            /* STATE_1 (INCOMING): Three-phase spare insertion control */
            double gap_to_succ = fleet[succ_idx].gap_to_pred;
            double dt = 0.1;  /* timestep */
            fleet[i].time_in_incoming += dt;
            
            /* Phase timing parameters (in seconds) */
            double ramp_time = 0.5;      /* Phase 1: soft entry (5 steps) */
            double position_time = 1.5;  /* Phase 2: positioning lock (20 steps) */
            double min_transition_time = 2.0;  /* Minimum time before Phase 3 */
            
            /* Detect phase based on time and criteria */
            double gap_balance_error = fabs(gap - gap_to_succ);
            int spare_centered = (gap_balance_error < 0.2 * nom_spacing && 
                                 fabs(gap_to_succ - nom_spacing) < 0.1 * nom_spacing);
            int velocity_close = (fabs(fleet[i].v - scenario->v_nominal) < 0.05 * scenario->v_nominal);
            
            if (fleet[i].time_in_incoming > min_transition_time && 
                spare_centered && velocity_close) {
                /* Transition to BASELINE */
                fleet[i].state = 0;
                fleet[i].phase = 3;
                cmd_v = scenario->v_nominal;
            } else if (fleet[i].time_in_incoming < ramp_time) {
                /* PHASE 1: Soft Entry - ramp speed from entry to nominal */
                fleet[i].phase = 1;
                double v_entry = 0.6 * scenario->v_nominal;
                double target_v = v_entry + (scenario->v_nominal - v_entry) * 
                                 (fleet[i].time_in_incoming / ramp_time);
                
                /* Back-regulation only: respond to successor gap (positioning) */
                double back_term = 0.3 * (gap_to_succ - nom_spacing);
                cmd_v = target_v - back_term;
                
                /* Bound to not exceed ramp target */
                cmd_v = fmin(cmd_v, target_v);
                
            } else if (fleet[i].time_in_incoming < position_time) {
                /* PHASE 2: Positioning Lock - distance-weighted bidirectional */
                fleet[i].phase = 2;
                
                /* Distance-weighted gain */
                double gap_diff = fabs(gap - gap_to_succ);
                double w_center = nom_spacing / (nom_spacing + gap_diff / 2.0);
                
                /* Reduced front gain (don't chase predecessor aggressively) */
                double front_term = 0.2 * w_center * (gap - nom_spacing);
                double back_term = 0.5 * w_center * (gap_to_succ - nom_spacing);
                
                cmd_v = scenario->v_nominal + front_term - back_term;
                
            } else {
                /* PHASE 3: Approaching normal operation */
                fleet[i].phase = 3;
                
                /* Standard bidirectional but not yet transitioned to BASELINE state */
                double front_term = 0.5 * (gap - nom_spacing);
                double back_term = 0.5 * (gap_to_succ - nom_spacing);
                cmd_v = scenario->v_nominal + front_term - back_term;
            }
            
            cmd_v = fmax(0.0, fmin(scenario->v_max, cmd_v));
        }
        
        /* Bounding */
        cmd_v = fmax(0.0, fmin(scenario->v_max, cmd_v));
        
        /* Ramp velocity smoothly */
        double v_prev = fleet[i].v;
        double accel = 0.5; /* m/s^2 */
        if (cmd_v > v_prev) {
            fleet[i].v = fmin(cmd_v, v_prev + accel * dt);
        } else {
            fleet[i].v = fmax(cmd_v, v_prev - accel * dt);
        }
    }
    
    /* Third pass: state transitions (INCOMING -> BASELINE when stable) */
    for (int i = 0; i < n; i++) {
        if (!fleet[i].alive) continue;
        if (fleet[i].state == 1) {  /* INCOMING mode */
            double gap = fleet[i].gap_to_pred;
            int succ_idx = (i + 1) % n;
            double gap_to_succ = fleet[succ_idx].gap_to_pred;
            
            /* Transition to BASELINE when both gaps within tolerance */
            if (fabs(gap - nom_spacing) < 0.1 * nom_spacing && 
                fabs(gap_to_succ - nom_spacing) < 0.1 * nom_spacing) {
                fleet[i].state = 0;  /* Transition to BASELINE */
            }
        }
    }
    
    /* Fourth pass: move drones */
    for (int i = 0; i < n; i++) {
        if (!fleet[i].alive) continue;
        
        fleet[i].x = fmod(fleet[i].x + fleet[i].v * dt, scenario->perimeter);
    }
}

/* ================================================================
   SPARE INSERTION (simplified: insert at gap midpoint)
   ================================================================ */

void try_insert_spare(Drone *fleet, Scenario *scenario, int *spares_inserted) {
    /* Find largest gap */
    int n = scenario->num_drones;
    int max_gap_idx = 0;
    double max_gap = 0;
    int num_alive = 0;
    
    for (int i = 0; i < n; i++) {
        if (fleet[i].alive) {
            num_alive++;
            if (fleet[i].gap_to_pred > max_gap) {
                max_gap = fleet[i].gap_to_pred;
                max_gap_idx = i;
            }
        }
    }
    
    /* Decision threshold */
    double density = (double)num_alive / scenario->num_drones;
    
    if (density < scenario->density_threshold && num_alive < scenario->num_drones) {
        /* Find an inactive slot and activate it at gap midpoint */
        for (int i = 0; i < n; i++) {
            if (!fleet[i].alive) {
                fleet[i].x = fmod(fleet[max_gap_idx].x - max_gap / 2.0 + scenario->perimeter,
                                 scenario->perimeter);
                /* Three-phase entry: start at reduced speed (0.6*v_nominal) */
                fleet[i].v = 0.6 * scenario->v_nominal;
                fleet[i].alive = 1;
                fleet[i].state = 1;  /* Enter INCOMING mode */
                fleet[i].time_in_incoming = 0.0;  /* Reset phase timer */
                fleet[i].phase = 1;  /* Start in Phase 1: soft entry */
                (*spares_inserted)++;
                return;
            }
        }
    }
}

/* ================================================================
   METRICS COMPUTATION
   ================================================================ */

void compute_metrics(Drone *fleet, Scenario *scenario, Metrics *m, 
                     int step, int step_at_failure, int recovery_started) {
    int n = scenario->num_drones;
    int num_alive = 0;
    double sum_v = 0, sum_v2 = 0;
    double max_gap = 0, sum_gap = 0, gap_count = 0;
    
    for (int i = 0; i < n; i++) {
        if (fleet[i].alive) {
            num_alive++;
            sum_v += fleet[i].v;
            sum_v2 += fleet[i].v * fleet[i].v;
            
            double gap = fleet[i].gap_to_pred;
            if (gap > 0) {
                sum_gap += gap;
                gap_count++;
                max_gap = fmax(max_gap, gap);
            }
        }
    }
    
    /* Density */
    m->num_drones_active = num_alive;
    m->density = (double)num_alive / n;
    
    /* Coverage: perimeter length maintained by active drones */
    m->coverage = m->density * 100.0; /* Simplified: % of nominal coverage */
    
    /* Speed statistics */
    m->avg_speed = (num_alive > 0) ? sum_v / num_alive : scenario->v_nominal;
    double var = (num_alive > 0) ? (sum_v2 / num_alive - m->avg_speed * m->avg_speed) : 0;
    m->speed_stddev = sqrt(fmax(0, var));
    
    /* Gap statistics */
    m->max_gap = max_gap;
    m->avg_gap = (gap_count > 0) ? sum_gap / gap_count : 0;
    
    /* Formation stability: how close to nominal spacing (0-1) */
    double nom_spacing = scenario->nominal_spacing;
    double stability = 0;
    if (num_alive > 1) {
        double gap_error = fabs(m->avg_gap - nom_spacing);
        stability = 1.0 / (1.0 + gap_error / nom_spacing);
    }
    m->formation_stability = stability;
    
    /* Energy: sum of speed deviations from nominal (rough estimate) */
    m->energy_consumed = sum_v / scenario->v_nominal;
    
    /* Recovery metrics */
    if (step_at_failure >= 0 && recovery_started == 0) {
        if (m->density > 0.95) { /* Recovered to 95% */
            m->time_to_recover = step - step_at_failure;
            recovery_started = 1;
        }
    }
    
    /* Recovery slope: density increase per step during recovery */
    if (recovery_started && step_at_failure >= 0) {
        double recovery_duration = step - step_at_failure;
        if (recovery_duration > 0) {
            m->recovery_slope = (m->density - 0.5) / recovery_duration;
        }
    }
}

/* ================================================================
   SIMULATION EXECUTOR
   ================================================================ */

void simulate_scenario(Scenario *scenario, Metrics *result) {
    Drone fleet[MAX_DRONES];
    
    /* Initialize metrics */
    memset(result, 0, sizeof(Metrics));
    
    /* Initialize fleet */
    initialize_fleet(fleet, scenario);
    
    int failures_injected = 0;
    int spares_inserted = 0;
    int step_at_failure = -1;
    int recovery_started = 0;
    double dt = 0.1; /* Simulation time step */
    
    /* Main simulation loop */
    for (int step = 0; step < MAX_SIMULATION_STEPS; step++) {
        /* Inject failures randomly based on distribution mode */
        if (step > 100 && failures_injected < scenario->num_failures) {
            if (uniform_random(0, 1) < scenario->failure_rate) {
                inject_failure(fleet, scenario, &failures_injected, step);
                if (step_at_failure < 0 && failures_injected > 0) {
                    step_at_failure = step;
                }
            }
        }
        
        /* Update fleet dynamics */
        update_drone_positions(fleet, scenario, dt);
        
        /* Try to insert spares if needed */
        try_insert_spare(fleet, scenario, &spares_inserted);
        
        /* Compute metrics every 10 steps */
        if (step % 10 == 0) {
            compute_metrics(fleet, scenario, result, step, step_at_failure, recovery_started);
        }
    }
    
    /* Final metric snapshot */
    compute_metrics(fleet, scenario, result, MAX_SIMULATION_STEPS - 1, step_at_failure, recovery_started);
}

/* ================================================================
   MAIN PROGRAM
   ================================================================ */

int main(int argc, char *argv[]) {
    if (argc != 3) {
        fprintf(stderr, "Usage: %s <input_csv> <output_csv>\n", argv[0]);
        fprintf(stderr, "Example: %s scenarios.csv results.csv\n", argv[0]);
        return 1;
    }
    
    const char *input_file = argv[1];
    const char *output_file = argv[2];
    
    srand(time(NULL));
    
    /* Read scenarios */
    Scenario scenarios[MAX_SCENARIOS];
    Metrics results[MAX_SCENARIOS];
    int num_scenarios = 0;
    
    if (read_scenarios_csv(input_file, scenarios, &num_scenarios) < 0) {
        return 1;
    }
    
    if (num_scenarios == 0) {
        fprintf(stderr, "Error: No scenarios loaded\n");
        return 1;
    }
    
    printf("Starting simulation of %d scenarios...\n", num_scenarios);
    
    /* Run simulations with per-scenario reproducible seeds */
    for (int i = 0; i < num_scenarios; i++) {
        const char *dist_mode = "unknown";
        if (scenarios[i].failure_distribution == 0) dist_mode = "random";
        else if (scenarios[i].failure_distribution == 1) dist_mode = "spatial_clustered";
        else if (scenarios[i].failure_distribution == 2) dist_mode = "temporal_cascade";
        
        if (scenarios[i].seed == 0) {
            scenarios[i].seed = (unsigned int)(time(NULL) + i * 7919);
        }
        srand(scenarios[i].seed);
        
        printf("  Scenario %d/%d: %d drones, perimeter=%.1f, policy=%d, failures=%s, seed=%u\n",
               i + 1, num_scenarios, scenarios[i].num_drones, scenarios[i].perimeter,
               scenarios[i].balancing_policy, dist_mode, scenarios[i].seed);
        
        simulate_scenario(&scenarios[i], &results[i]);
    }
    
    printf("All simulations completed.\n");
    
    /* Write results */
    if (write_results_csv(output_file, scenarios, results, num_scenarios) < 0) {
        return 1;
    }
    
    printf("Simulation complete.\n");
    return 0;
}
