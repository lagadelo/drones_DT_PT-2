#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* Baseline local spacing control (Algorithm~\ref{alg:baseline} in methodology.tex)
 * - Inputs: simple key=value scenario file + CSV losses
 * - Outputs: final density/spacing metrics to stdout
 */

typedef struct {
    int n;
    double perimeter;
    double V;
    double Vmax;
    double d_star;
    double d_safe;
    double k_sym;            /* symmetric gap gain (front - back) */
    double k_sym_rec;        /* symmetric gain during recovery */
    double k_f, k_b, k_rep;
    double k_f_rec, k_b_rec;
    double alpha, beta;
    double V_cap;
    double epsilon;
    int steps;
    double dt;
    int num_losses;
    unsigned int seed;
    int resilience; /* enable spare insertion up to num_losses, only after losses */
    int min_spare_delay_steps; /* minimum steps after a loss before inserting a spare */
    int incoming_hold_steps;   /* steps a new spare stays at nominal speed */
} Scenario;

typedef struct {
    double s;      /* curvilinear position on perimeter */
    double v;      /* current speed */
    int alive;     /* 1 alive, 0 failed */
    int mode;      /* 0=BASELINE, 1=INCOMING (unused in this minimal build) */
    int incoming_timer; /* steps remaining at fixed speed when incoming */
    double gap_f;  /* front gap (computed per step) */
    double gap_b;  /* back gap (computed per step) */
} Drone;

typedef struct {
    int step;
    int idx;
} Loss;

static int parse_loss_line(const char *line, int *step, int *idx) {
    const char *sep = strpbrk(line, ",;");
    if (!sep) return 0;
    *step = atoi(line);
    *idx = atoi(sep + 1);
    return 1;
}

static int read_scenario(const char *path, Scenario *s) {
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    char line[256];
    while (fgets(line, sizeof(line), f)) {
        char key[64];
        double val;
        if (sscanf(line, "%63[^=]=%lf", key, &val) == 2) {
            if (strcmp(key, "n") == 0) s->n = (int)val;
            else if (strcmp(key, "perimeter") == 0) s->perimeter = val;
            else if (strcmp(key, "V") == 0) s->V = val;
            else if (strcmp(key, "Vmax") == 0) s->Vmax = val;
            else if (strcmp(key, "d_star") == 0) s->d_star = val;
            else if (strcmp(key, "d_safe") == 0) s->d_safe = val;
            else if (strcmp(key, "k_sym") == 0) s->k_sym = val;
            else if (strcmp(key, "k_sym_rec") == 0) s->k_sym_rec = val;
            else if (strcmp(key, "w_back") == 0) s->k_sym = val; /* backward compat: w_back now aliases k_sym */
            else if (strcmp(key, "k_f") == 0) s->k_f = val;
            else if (strcmp(key, "k_b") == 0) s->k_b = val;
            else if (strcmp(key, "k_rep") == 0) s->k_rep = val;
            else if (strcmp(key, "k_f_rec") == 0) s->k_f_rec = val;
            else if (strcmp(key, "k_b_rec") == 0) s->k_b_rec = val;
            else if (strcmp(key, "alpha") == 0) s->alpha = val;
            else if (strcmp(key, "beta") == 0) s->beta = val;
            else if (strcmp(key, "V_cap") == 0) s->V_cap = val;
            else if (strcmp(key, "epsilon") == 0) s->epsilon = val;
            else if (strcmp(key, "steps") == 0) s->steps = (int)val;
            else if (strcmp(key, "dt") == 0) s->dt = val;
            else if (strcmp(key, "num_losses") == 0) s->num_losses = (int)val;
            else if (strcmp(key, "seed") == 0) s->seed = (unsigned int)val;
            else if (strcmp(key, "resilience") == 0) s->resilience = (int)val;
            else if (strcmp(key, "min_spare_delay_steps") == 0) s->min_spare_delay_steps = (int)val;
            else if (strcmp(key, "incoming_hold_steps") == 0) s->incoming_hold_steps = (int)val;
        }
    }
    fclose(f);
    return 0;
}

static int read_losses(const char *path, Loss **losses_out, int *count_out) {
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    int cap = 64, count = 0;
    Loss *arr = malloc(cap * sizeof(Loss));
    char line[256];
    /* optional header */
    fgets(line, sizeof(line), f);
    while (fgets(line, sizeof(line), f)) {
        int step, idx;
        if (parse_loss_line(line, &step, &idx)) {
            if (count >= cap) {
                cap *= 2;
                arr = realloc(arr, cap * sizeof(Loss));
            }
            arr[count].step = step;
            arr[count].idx = idx;
            count++;
        }
    }
    fclose(f);
    *losses_out = arr;
    *count_out = count;
    return 0;
}

typedef struct {
    int idx;
    double pos;
} Ordered;

static int cmp_pos(const void *a, const void *b) {
    const Ordered *pa = (const Ordered *)a;
    const Ordered *pb = (const Ordered *)b;
    if (pa->pos < pb->pos) return -1;
    if (pa->pos > pb->pos) return 1;
    return 0;
}

static void generate_losses(const Scenario *s, Loss **losses_out, int *count_out) {
    int count = s->num_losses;
    Loss *arr = calloc(count, sizeof(Loss));
    srand(s->seed);
    for (int i = 0; i < count; i++) {
        arr[i].step = rand() % (s->steps > 0 ? s->steps : 1);
        arr[i].idx = rand() % (s->n > 0 ? s->n : 1);
    }
    /* sort by step for deterministic processing */
    for (int i = 0; i < count - 1; i++) {
        for (int j = i + 1; j < count; j++) {
            if (arr[j].step < arr[i].step) {
                Loss tmp = arr[i];
                arr[i] = arr[j];
                arr[j] = tmp;
            }
        }
    }
    *losses_out = arr;
    *count_out = count;
}

static void compute_gaps(Drone *fleet, const Scenario *s) {
    int n = s->n;
    Ordered *order = malloc(n * sizeof(Ordered));
    int alive_count = 0;
    /* reset gaps each step; dead drones stay at zero */
    for (int i = 0; i < n; i++) {
        fleet[i].gap_f = 0.0;
        fleet[i].gap_b = 0.0;
        order[i].idx = i;
        order[i].pos = fleet[i].s;
        if (fleet[i].alive) alive_count++;
    }
    /* sort by position */
    qsort(order, n, sizeof(Ordered), cmp_pos);
    /* compute gaps only for alive drones */
    int prev_alive = -1;
    double prev_pos = 0;
    double first_pos = -1, last_pos = -1;
    for (int k = 0; k < n; k++) {
        int idx = order[k].idx;
        if (!fleet[idx].alive) continue;
        double pos = order[k].pos;
        if (first_pos < 0) first_pos = pos;
        if (prev_alive >= 0) {
            double gap = pos - prev_pos;
            fleet[idx].gap_b = gap;
            fleet[prev_alive].gap_f = gap;
        }
        prev_alive = idx;
        prev_pos = pos;
        last_pos = pos;
    }
    /* close the ring */
    if (alive_count > 1) {
        double wrap_gap = s->perimeter - last_pos + first_pos;
        fleet[prev_alive].gap_f = wrap_gap;
        for (int k = 0; k < n; k++) {
            int idx = order[k].idx;
            if (!fleet[idx].alive) continue;
            if (fleet[idx].gap_b == 0 && idx != prev_alive) {
                /* set back gap when not yet set */
                fleet[idx].gap_b = (idx == order[0].idx) ? wrap_gap : fleet[idx].gap_b;
            }
        }
        /* set back gap for first alive */
        for (int k = 0; k < n; k++) {
            int idx = order[k].idx;
            if (!fleet[idx].alive) continue;
            if (idx == order[0].idx) {
                fleet[idx].gap_b = wrap_gap;
                break;
            }
        }
    }
    free(order);
}

static int find_dead_drone(Drone *fleet, int n) {
    for (int i = 0; i < n; i++) {
        if (!fleet[i].alive) return i;
    }
    return -1;
}

static int find_largest_gap(const Drone *fleet, const Scenario *s, int *from_idx, double *from_pos, double *gap_out) {
    int n = s->n;
    Ordered *order = malloc(n * sizeof(Ordered));
    int alive_count = 0;
    for (int i = 0; i < n; i++) {
        order[i].idx = i;
        order[i].pos = fleet[i].s;
        if (fleet[i].alive) alive_count++;
    }
    if (alive_count < 2) {
        free(order);
        return 0;
    }
    qsort(order, n, sizeof(Ordered), cmp_pos);
    double best_gap = -1.0;
    int best_from = -1;
    double best_pos = 0.0;
    int first_alive_seen = 0;
    double first_pos = 0.0;
    int first_idx = -1;
    double prev_pos = 0.0;
    int prev_idx = -1;
    for (int k = 0; k < n; k++) {
        int idx = order[k].idx;
        if (!fleet[idx].alive) continue;
        double pos = order[k].pos;
        if (!first_alive_seen) {
            first_alive_seen = 1;
            first_pos = pos;
            first_idx = idx;
        }
        if (prev_idx != -1) {
            double gap = pos - prev_pos;
            if (gap > best_gap) {
                best_gap = gap;
                best_from = prev_idx;
                best_pos = prev_pos;
            }
        }
        prev_idx = idx;
        prev_pos = pos;
    }
    /* wrap gap */
    double wrap_gap = s->perimeter - prev_pos + first_pos;
    if (wrap_gap > best_gap) {
        best_gap = wrap_gap;
        best_from = prev_idx;
        best_pos = prev_pos;
    }
    free(order);
    if (best_gap <= 0 || best_from < 0) return 0;
    *from_idx = best_from;
    *from_pos = best_pos;
    *gap_out = best_gap;
    return 1;
}

static void simulate(Scenario *s, Loss *losses, int loss_count, FILE *summary, FILE *trace) {
    int n = s->n;
    Drone *fleet = calloc(n, sizeof(Drone));
    for (int i = 0; i < n; i++) {
        fleet[i].s = fmod(i * (s->perimeter / n), s->perimeter);
        fleet[i].v = s->V;
        fleet[i].alive = 1;
        fleet[i].mode = 0;
        fleet[i].incoming_timer = 0;
    }
    int loss_idx = 0;
    int total_losses_seen = 0;
    int total_spares_inserted = 0;
    int last_loss_step = -1000000;
    double dt = s->dt;

    /* Optional headers */
    if (summary) {
        fprintf(summary, "step;alive;mean_v;min_v;max_v;std_v;min_gap;max_gap;mean_gap;std_gap\n");
    }
    if (trace) {
        fprintf(trace, "step;idx;alive;s;v;gap_f;gap_b\n");
    }

    for (int step = 0; step < s->steps; step++) {
        int loss_this_step = 0;
        /* apply losses scheduled at this step */
        while (loss_idx < loss_count && losses[loss_idx].step == step) {
            int idx = losses[loss_idx].idx;
            if (idx >= 0 && idx < n && fleet[idx].alive) {
                fleet[idx].alive = 0;
                loss_this_step = 1;
                last_loss_step = step;
            }
            loss_idx++;
        }

        compute_gaps(fleet, s);

        /* optional spare insertion: only after losses, capped by num_losses */
        if (s->resilience && !loss_this_step) {
            /* count how many are dead to gate spare pool */
            int dead_now = 0;
            for (int i = 0; i < n; i++) {
                if (!fleet[i].alive) dead_now++;
            }
            if (total_losses_seen < dead_now) total_losses_seen = dead_now;
            if (total_spares_inserted < total_losses_seen && total_spares_inserted < s->num_losses && (step - last_loss_step) >= s->min_spare_delay_steps) {
                int from_idx = -1; 
                double from_pos = 0.0; 
                double gap = 0.0;
                if (find_largest_gap(fleet, s, &from_idx, &from_pos, &gap)) {
                    int slot = find_dead_drone(fleet, n);
                    if (slot >= 0) {
                        double insert_pos = fmod(from_pos + 0.5 * gap + s->perimeter, s->perimeter);
                        fleet[slot].alive = 1;
                        fleet[slot].s = insert_pos;
                        fleet[slot].v = s->V;
                        fleet[slot].mode = 1;
                        fleet[slot].incoming_timer = s->incoming_hold_steps;
                        total_spares_inserted++;
                        compute_gaps(fleet, s);
                    }
                }
            }
        }

        /* update speeds */
        for (int i = 0; i < n; i++) {
            if (!fleet[i].alive) continue;
            double d_f = fleet[i].gap_f;
            double d_b = fleet[i].gap_b;
            int rec = (d_f > s->alpha * s->d_star) || (d_b < s->beta * s->d_star);
            double k_sym = rec && s->k_sym_rec > 0 ? s->k_sym_rec : s->k_sym;
            double gap_delta = d_f - d_b; /* accelerate if front gap > back gap, brake otherwise */
            double v = s->V + k_sym * gap_delta;
            if (d_f < s->d_safe) {
                double cap = s->V * (d_f / s->d_safe);
                if (v > cap) v = cap;
            }
            if (d_b < s->d_safe) {
                v += s->k_rep * (s->d_safe - d_b);
            }
            if (rec && v > s->V_cap) v = s->V_cap;
            if (v < 0) v = 0;
            if (v > s->Vmax) v = s->Vmax;
            /* incoming drones stay at nominal speed for a fixed window */
            if (fleet[i].mode == 1 && fleet[i].incoming_timer > 0) {
                v = s->V;
                fleet[i].incoming_timer--;
                if (fleet[i].incoming_timer == 0) {
                    fleet[i].mode = 0;
                }
            }
            fleet[i].v = v;
        }

        /* per-step summary */
        if (summary) {
            int alive = 0;
            double min_v = 0, max_v = 0, sum_v = 0, sum_v2 = 0;
            double min_g = 0, max_g = 0, sum_g = 0, sum_g2 = 0; int gap_count = 0;
            for (int i = 0; i < n; i++) {
                if (!fleet[i].alive) continue;
                alive++;
                double v = fleet[i].v;
                if (alive == 1) {
                    min_v = max_v = v;
                } else {
                    if (v < min_v) min_v = v;
                    if (v > max_v) max_v = v;
                }
                sum_v += v;
                sum_v2 += v * v;
                double g = fleet[i].gap_f;
                if (gap_count == 0) {
                    min_g = max_g = g;
                } else {
                    if (g < min_g) min_g = g;
                    if (g > max_g) max_g = g;
                }
                sum_g += g;
                sum_g2 += g * g;
                gap_count++;
            }
            double std_v = 0, std_g = 0; double mean_g = 0; double mean_v = 0;
            if (alive > 0) {
                mean_v = sum_v / alive;
                double var_v = (sum_v2 / alive) - (mean_v * mean_v);
                if (var_v < 0) var_v = 0;
                std_v = sqrt(var_v);
            }
            if (gap_count > 0) {
                mean_g = sum_g / gap_count;
                double var_g = (sum_g2 / gap_count) - (mean_g * mean_g);
                if (var_g < 0) var_g = 0;
                std_g = sqrt(var_g);
            }
                fprintf(summary, "%d;%d;%.6f;%.6f;%.6f;%.6f;%.6f;%.6f;%.6f;%.6f\n",
                    step, alive,
                    mean_v,
                    alive ? min_v : 0.0, alive ? max_v : 0.0, std_v,
                    gap_count ? min_g : 0.0, gap_count ? max_g : 0.0,
                    gap_count ? mean_g : 0.0, std_g);
        }

        /* emit trace after speed update, before position advance */
        if (trace) {
            for (int i = 0; i < n; i++) {
                if (fleet[i].alive) {
                    fprintf(trace, "%d;%d;%d;%.6f;%.6f;%.6f;%.6f\n",
                            step, i, fleet[i].alive, fleet[i].s, fleet[i].v,
                            fleet[i].gap_f, fleet[i].gap_b);
                } else {
                    /* dead drone: gaps left empty to signal no neighbors */
                    fprintf(trace, "%d;%d;%d;%.6f;%.6f;;\n",
                            step, i, fleet[i].alive, fleet[i].s, fleet[i].v);
                }
            }
        }

        /* advance positions */
        for (int i = 0; i < n; i++) {
            if (!fleet[i].alive) continue;
            fleet[i].s = fmod(fleet[i].s + fleet[i].v * dt + s->perimeter, s->perimeter);
        }
    }

    /* final metrics */
    int alive = 0;
    double sum_v = 0, sum_v2 = 0, sum_gap = 0; int gap_count = 0;
    for (int i = 0; i < n; i++) if (fleet[i].alive) alive++;
    compute_gaps(fleet, s);
    double max_gap = 0;
    for (int i = 0; i < n; i++) {
        if (!fleet[i].alive) continue;
        sum_v += fleet[i].v;
        sum_v2 += fleet[i].v * fleet[i].v;
        sum_gap += fleet[i].gap_f;
        gap_count++;
        if (fleet[i].gap_f > max_gap) max_gap = fleet[i].gap_f;
    }
    double density = (double)alive / n;
    double avg_speed = alive ? sum_v / alive : 0;
    double var = alive ? (sum_v2 / alive - avg_speed * avg_speed) : 0;
    double speed_std = var > 0 ? sqrt(var) : 0;
    double avg_gap = gap_count ? sum_gap / gap_count : 0;
    double stability = 0;
    if (avg_gap > 0) stability = 1.0 / (1.0 + fabs(avg_gap - s->d_star) / s->d_star);

    printf("density=%.4f\n", density);
    printf("avg_speed=%.4f\n", avg_speed);
    printf("speed_std=%.4f\n", speed_std);
    printf("max_gap=%.4f\n", max_gap);
    printf("avg_gap=%.4f\n", avg_gap);
    printf("stability=%.4f\n", stability);

    free(fleet);
}

int main(int argc, char **argv) {
    if (argc < 3 || argc > 5) {
        fprintf(stderr, "Usage: %s <scenario.cfg> <losses.csv> [summary.csv] [trace.csv]\n", argv[0]);
        fprintf(stderr, "scenario.cfg: key=value per line (see sample_scenario.cfg)\n");
        fprintf(stderr, "  supports seed=<uint> and num_losses=<int> for auto-generated losses\n");
        fprintf(stderr, "losses.csv: step,idx per line (header optional, ',' or ';'); if missing/empty and num_losses>0, losses are generated with seed\n");
        fprintf(stderr, "summary.csv (optional): per-step aggregates (alive, mean/min/max/std of v and gaps)\n");
        fprintf(stderr, "trace.csv (optional): per-step dump of s,v,gaps per drone\n");
        return 1;
    }
    Scenario s = {0};
    s.V = 1.0; s.Vmax = 2.0; s.d_star = 5.0; s.d_safe = 1.0;
    s.k_sym = 0.5; s.k_sym_rec = 0.5; /* symmetric gap controller (front-back) */
    s.k_f = 0.5; s.k_b = 0.3; s.k_rep = 0.2; s.k_f_rec = 0.8; s.k_b_rec = 0.0;
    s.alpha = 1.2; s.beta = 0.8; s.V_cap = 1.5; s.epsilon = 0.1; s.steps = 500; s.dt = 0.1;
    s.num_losses = 0; s.seed = 1; s.resilience = 0; s.min_spare_delay_steps = 0; s.incoming_hold_steps = 50;

    if (read_scenario(argv[1], &s) != 0) {
        fprintf(stderr, "Could not read scenario file %s\n", argv[1]);
        return 1;
    }
    Loss *losses = NULL; int loss_count = 0;
    int read_ok = read_losses(argv[2], &losses, &loss_count);
    if (read_ok != 0 || loss_count == 0) {
        if (s.num_losses > 0) {
            /* auto-generate losses with seed */
            if (losses) free(losses);
            generate_losses(&s, &losses, &loss_count);
            FILE *out = fopen(argv[2], "w");
            if (out) {
                fprintf(out, "step;idx\n");
                for (int i = 0; i < loss_count; i++) {
                    fprintf(out, "%d;%d\n", losses[i].step, losses[i].idx);
                }
                fclose(out);
            }
        } else {
            fprintf(stderr, "Could not read losses file %s and num_losses not set\n", argv[2]);
            if (losses) free(losses);
            return 1;
        }
    }

    FILE *summary = NULL;
    FILE *trace = NULL;
    if (argc >= 4) {
        summary = fopen(argv[3], "w");
        if (!summary) {
            fprintf(stderr, "Could not open summary file %s\n", argv[3]);
            return 1;
        }
    }
    if (argc == 5) {
        trace = fopen(argv[4], "w");
        if (!trace) {
            fprintf(stderr, "Could not open trace file %s\n", argv[4]);
            if (summary) fclose(summary);
            return 1;
        }
    }

    simulate(&s, losses, loss_count, summary, trace);
    if (summary) fclose(summary);
    if (trace) fclose(trace);
    free(losses);
    return 0;
}
