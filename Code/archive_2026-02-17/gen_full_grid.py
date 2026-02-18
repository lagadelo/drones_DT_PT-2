import csv, math

sizes = [25, 100, 1000, 10000, 12000]
strike_fracs = [0.10, 0.20, 0.30, 0.40, 0.50]
policies = [0, 1, 2, 3, 4, 5]
dists = [0, 1, 2]
vmax_ratios = [1.5, 2.0]

header = [
    "perimeter",
    "num_drones",
    "v_nominal",
    "v_max",
    "sensing_radius",
    "nominal_spacing",
    "balancing_policy",
    "density_threshold",
    "speed_threshold",
    "adaptation_window",
    "failure_rate",
    "num_failures",
    "failure_distribution",
    "initial_active",
    "spare_trigger_ratio",
    "spare_target_factor",
    "neighbor_balance_factor",
    "strike_fraction",
    "seed",
]

rows = []
seed_base = 5000
idx = 0

for n in sizes:
    nom_spacing = 5.0 if n < 10000 else 4.0
    perimeter = n * nom_spacing
    initial_active = n
    capacity = math.ceil(initial_active * 1.3)
    sensing_radius = 8.0 if n >= 1000 else (10.0 if n <= 100 else 8.0)
    for vmax_ratio in vmax_ratios:
        v_max = vmax_ratio * 1.0
        for dist in dists:
            for sf in strike_fracs:
                for policy in policies:
                    idx += 1
                    rows.append([
                        perimeter,
                        capacity,
                        1.0,
                        v_max,
                        sensing_radius,
                        nom_spacing,
                        policy,
                        0.90,
                        1.8,
                        10.0,
                        1.0,
                        0,
                        dist,
                        initial_active,
                        0.90,
                        1.3,
                        1.0,
                        sf,
                        seed_base + idx,
                    ])

with open("scenarios_full_grid.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)

print(f"wrote {len(rows)} scenarios to scenarios_full_grid.csv")
