import csv, statistics
from collections import defaultdict

path = 'results_full_grid.csv'
rows = []
with open(path) as f:
    reader = csv.DictReader(f)
    for r in reader:
        for k in ['balancing_policy','failure_distribution','num_drones','v_max']:
            r[k] = float(r[k])
        rows.append(r)

name = {0:'pred-only',1:'sym',2:'k0.4',3:'k0.5',4:'k0.6',5:'VP-C'}
dist = {0:'random',1:'spatial',2:'temporal'}

combos = defaultdict(list)
for r in rows:
    p = int(r['balancing_policy'])
    if p not in (0,1,5):
        continue
    key = (p, int(r['failure_distribution']), r['v_max'])
    combos[key].append(r)

print('policy,dist,v_max,count,density,stability,max_gap,avg_speed,speed_stddev')
for (p,d,vmax), rs in sorted(combos.items()):
    def avg(field):
        return statistics.mean(float(x[field]) for x in rs)
    print(f"{name[p]},{dist[d]},{vmax:.1f},{len(rs)},"
          f"{avg('density'):.4f},{avg('formation_stability'):.4f},"
          f"{avg('max_gap'):.1f},{avg('avg_speed'):.3f},{avg('speed_stddev'):.3f}")

for p in (0,1,5):
    subset = [r for r in rows if int(r['balancing_policy'])==p]
    grp = defaultdict(list)
    for r in subset:
        grp[r['v_max']].append(r)
    print('\npolicy', name[p])
    for vmax, rs in sorted(grp.items()):
        dens = statistics.mean(float(x['density']) for x in rs)
        avgv = statistics.mean(float(x['avg_speed']) for x in rs)
        stdv = statistics.mean(float(x['speed_stddev']) for x in rs)
        print(f"  v_max={vmax:.1f} n={len(rs)} density={dens:.4f} avg_speed={avgv:.3f} speed_std={stdv:.3f}")
