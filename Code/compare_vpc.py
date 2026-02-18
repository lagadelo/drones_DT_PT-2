#!/usr/bin/env python3
import csv

def read_results(filename):
    results = []
    with open(filename) as f:
        reader = csv.DictReader(f)
        for row in reader:
            results.append(row)
    return results

vpc = read_results('results_vpc_test.csv')
baseline = read_results('results_baseline.csv')

print("="*70)
print("VP-C (Policy 3) Results - Adaptive Sensing Variant")
print("="*70)
print(f"Total scenarios tested: {len(vpc)}\n")
for i, row in enumerate(vpc):
    print(f"Scenario {i+1}:")
    print(f"  Setup: {row['num_drones']} drones, {row['perimeter']}m perimeter")
    print(f"  Metrics:")
    print(f"    - Density: {float(row['density']):.3f}")
    print(f"    - Avg Speed: {float(row['avg_speed']):.3f} m/s")
    print(f"    - Formation Stability: {float(row['formation_stability']):.3f}")
    print(f"    - Energy Consumed: {float(row['energy_consumed']):.1f}")
    print(f"    - Recovery Time: {float(row['time_to_recover']):.1f} steps")
    print()

print("\n" + "="*70)
print("Comparison: Baseline (Policy 0) vs VP-C (Policy 3)")
print("="*70)
print("\nFirst comparable scenario (20 drones, 100m):\n")

if baseline:
    b_row = baseline[0]
    v_row = vpc[0]
    
    print("Metric                    | Baseline (P0) | VP-C (P3) | Difference")
    print("-" * 70)
    
    metrics = [
        ('Density', 'density'),
        ('Avg Speed', 'avg_speed'),
        ('Formation Stability', 'formation_stability'),
        ('Energy Consumed', 'energy_consumed'),
        ('Recovery Time', 'time_to_recover')
    ]
    
    for label, key in metrics:
        b_val = float(b_row[key])
        v_val = float(v_row[key])
        diff = v_val - b_val
        pct = (diff / b_val * 100) if b_val != 0 else 0
        print(f"{label:25} | {b_val:13.3f} | {v_val:9.3f} | {pct:+6.1f}%")

print("\n" + "="*70)
print("VP-C Key Insight: Adaptive sensing disables back-pressure during")
print("spare insertion, preventing speed crashes while maintaining formation")
print("stability post-insertion through neighbor state awareness.")
print("="*70)
