#!/usr/bin/env python3
"""
Analyze fleet simulator results: statistical summary and visualization.
Supports text output, matplotlib plots, and JSON export.
"""

import csv
import json
import sys
from collections import defaultdict
import statistics

try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available. Plots disabled.", file=sys.stderr)
    print("Install with: pip3 install matplotlib numpy", file=sys.stderr)


def read_results_csv(filename):
    """Read and parse simulation results CSV."""
    results = []
    with open(filename, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric fields
            for key in row:
                try:
                    row[key] = float(row[key])
                except ValueError:
                    pass
            results.append(row)
    return results


def analyze_by_policy(results):
    """Group results by balancing policy and compute statistics."""
    by_policy = defaultdict(list)
    policy_names = {
        0: "Predecessor-only",
        1: "Symmetric",
        2: "Balanced k=0.4",
        3: "Balanced k=0.5",
        4: "Balanced k=0.6",
        5: "VP-C + 3-phase",
    }
    
    for row in results:
        policy = int(row['balancing_policy'])
        by_policy[policy].append(row)
    
    stats = {}
    for policy_id, rows in by_policy.items():
        name = policy_names.get(policy_id, f"Unknown({policy_id})")
        
        metrics = {
            'density': [r['density'] for r in rows],
            'coverage': [r['coverage'] for r in rows],
            'avg_speed': [r['avg_speed'] for r in rows],
            'max_gap': [r['max_gap'] for r in rows],
            'formation_stability': [r['formation_stability'] for r in rows],
            'recovery_slope': [r['recovery_slope'] for r in rows if r['recovery_slope'] > 0],
        }
        
        stats[name] = {
            'count': len(rows),
            'density_mean': statistics.mean(metrics['density']),
            'density_stdev': statistics.stdev(metrics['density']) if len(metrics['density']) > 1 else 0,
            'coverage_mean': statistics.mean(metrics['coverage']),
            'avg_speed_mean': statistics.mean(metrics['avg_speed']),
            'avg_speed_stdev': statistics.stdev(metrics['avg_speed']) if len(metrics['avg_speed']) > 1 else 0,
            'max_gap_mean': statistics.mean(metrics['max_gap']),
            'formation_stability_mean': statistics.mean(metrics['formation_stability']),
            'recovery_slope_mean': statistics.mean(metrics['recovery_slope']) if metrics['recovery_slope'] else 0,
            'recovery_count': len(metrics['recovery_slope']),
        }
    
    return stats


def analyze_by_distribution(results):
    """Group results by failure distribution mode."""
    by_dist = defaultdict(list)
    dist_names = {0: "Random", 1: "Spatial Clustered", 2: "Temporal Cascade"}
    
    for row in results:
        dist = int(row['failure_distribution'])
        by_dist[dist].append(row)
    
    stats = {}
    for dist_id, rows in by_dist.items():
        name = dist_names.get(dist_id, f"Unknown({dist_id})")
        
        metrics = {
            'density': [r['density'] for r in rows],
            'avg_gap': [r['avg_gap'] for r in rows],
        }
        
        stats[name] = {
            'count': len(rows),
            'density_mean': statistics.mean(metrics['density']),
            'density_stdev': statistics.stdev(metrics['density']) if len(metrics['density']) > 1 else 0,
            'avg_gap_mean': statistics.mean(metrics['avg_gap']),
        }
    
    return stats


def generate_text_summary(results):
    """Generate text-based analysis summary."""
    print("\n" + "=" * 70)
    print("FLEET SIMULATOR ANALYSIS SUMMARY")
    print("=" * 70)
    print(f"Total scenarios: {len(results)}\n")
    
    # By policy
    print("BY BALANCING POLICY:")
    print("-" * 70)
    stats_by_policy = analyze_by_policy(results)
    for policy, stats in sorted(stats_by_policy.items()):
        print(f"\n{policy}:")
        print(f"  Scenarios:           {stats['count']}")
        print(f"  Density:             {stats['density_mean']:.4f} ± {stats['density_stdev']:.4f}")
        print(f"  Coverage:            {stats['coverage_mean']:.2f}%")
        print(f"  Avg Speed:           {stats['avg_speed_mean']:.4f} ± {stats['avg_speed_stdev']:.4f} m/s")
        print(f"  Max Gap:             {stats['max_gap_mean']:.4f} m")
        print(f"  Formation Stability: {stats['formation_stability_mean']:.4f}")
        if stats['recovery_count'] > 0:
            print(f"  Recovery Slope:      {stats['recovery_slope_mean']:.6f} (n={stats['recovery_count']})")
    
    # By distribution
    print("\n\nBY FAILURE DISTRIBUTION:")
    print("-" * 70)
    stats_by_dist = analyze_by_distribution(results)
    for dist, stats in sorted(stats_by_dist.items()):
        print(f"\n{dist}:")
        print(f"  Scenarios:           {stats['count']}")
        print(f"  Density:             {stats['density_mean']:.4f} ± {stats['density_stdev']:.4f}")
        print(f"  Avg Gap:             {stats['avg_gap_mean']:.4f} m")
    
    print("\n" + "=" * 70)


def generate_plots(results, output_file='results.png'):
    """Generate 6-panel matplotlib visualization."""
    if not MATPLOTLIB_AVAILABLE:
        print("Skipping plots (matplotlib not available)", file=sys.stderr)
        return
    
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle('Fleet Simulator Results: Comprehensive Analysis', fontsize=16, fontweight='bold')
    
    # Extract data by policy (all supported codes)
    policies = {
        0: "Predecessor-only",
        1: "Symmetric",
        2: "Balanced k=0.4",
        3: "Balanced k=0.5",
        4: "Balanced k=0.6",
        5: "VP-C + 3-phase",
    }
    colors = {
        0: 'royalblue',
        1: 'darkorange',
        2: 'seagreen',
        3: 'orchid',
        4: 'goldenrod',
        5: 'firebrick',
    }
    
    policy_data = defaultdict(lambda: {
        'density': [], 'avg_speed': [], 'max_gap': [], 
        'formation_stability': [], 'energy': [], 'sensing': []
    })
    
    for row in results:
        policy = int(row['balancing_policy'])
        policy_data[policy]['density'].append(row['density'])
        policy_data[policy]['avg_speed'].append(row['avg_speed'])
        policy_data[policy]['max_gap'].append(row['max_gap'])
        policy_data[policy]['formation_stability'].append(row['formation_stability'])
        policy_data[policy]['energy'].append(row['energy_consumed'])
        policy_data[policy]['sensing'].append(row['sensing_radius'])
    
    # Panel 1: Density by policy
    ax = axes[0, 0]
    for policy_id in sorted(policies.keys()):
        data = policy_data[policy_id]['density']
        if data:
            ax.bar(policies[policy_id], sum(data) / len(data), 
                  color=colors[policy_id], alpha=0.7, label=policies[policy_id])
    ax.set_ylabel('Mean Density')
    ax.set_title('Fleet Density by Balancing Policy')
    ax.set_ylim([0, 1.0])
    ax.grid(True, alpha=0.3)
    
    # Panel 2: Speed distribution
    ax = axes[0, 1]
    speed_pairs = [(policies[p], policy_data[p]['avg_speed']) for p in sorted(policies.keys()) if policy_data[p]['avg_speed']]
    if speed_pairs:
        labels, speed_data = zip(*speed_pairs)
        ax.boxplot(speed_data, tick_labels=labels)
    ax.set_ylabel('Avg Speed (m/s)')
    ax.set_title('Speed Distribution by Policy')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Panel 3: Formation stability scatter
    ax = axes[0, 2]
    for policy_id in sorted(policies.keys()):
        energy = policy_data[policy_id]['energy']
        stability = policy_data[policy_id]['formation_stability']
        if energy and stability:
            ax.scatter(energy, stability, s=80, alpha=0.6, 
                      color=colors[policy_id], label=policies[policy_id])
    ax.set_xlabel('Energy Consumed')
    ax.set_ylabel('Formation Stability')
    ax.set_title('Energy-Stability Tradeoff')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Panel 4: Max gap by policy
    ax = axes[1, 0]
    gap_pairs = [(policies[p], policy_data[p]['max_gap']) for p in sorted(policies.keys()) if policy_data[p]['max_gap']]
    if gap_pairs:
        labels, gap_data = zip(*gap_pairs)
        ax.boxplot(gap_data, tick_labels=labels)
    ax.set_ylabel('Max Gap (meters)')
    ax.set_title('Maximum Inter-drone Gap')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Panel 5: Distribution mode comparison
    ax = axes[1, 1]
    dist_mapping = {0: "Random", 1: "Spatial", 2: "Temporal"}
    dist_density = defaultdict(list)
    for row in results:
        dist_density[int(row['failure_distribution'])].append(row['density'])
    for dist_id in sorted(dist_density.keys()):
        data = dist_density[dist_id]
        ax.bar(dist_mapping[dist_id], sum(data) / len(data), alpha=0.7)
    ax.set_ylabel('Mean Density')
    ax.set_title('Failure Distribution Impact on Density')
    ax.set_ylim([0, 1.0])
    ax.grid(True, alpha=0.3, axis='y')
    
    # Panel 6: Formation stability by policy (violin-like via box)
    ax = axes[1, 2]
    stab_pairs = [(policies[p], policy_data[p]['formation_stability']) for p in sorted(policies.keys()) 
                 if policy_data[p]['formation_stability']]
    if stab_pairs:
        labels, stab_data = zip(*stab_pairs)
        ax.boxplot(stab_data, tick_labels=labels)
    ax.set_ylabel('Formation Stability')
    ax.set_title('Formation Stability by Policy')
    ax.set_ylim([0, 1.0])
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Plots saved to {output_file}")


def generate_json_export(results, output_file='results.json'):
    """Export analysis as JSON for R/MATLAB/Jupyter."""
    stats_by_policy = analyze_by_policy(results)
    stats_by_dist = analyze_by_distribution(results)
    
    export = {
        'by_policy': stats_by_policy,
        'by_distribution': stats_by_dist,
        'raw_results': results,
    }
    
    with open(output_file, 'w') as f:
        json.dump(export, f, indent=2)
    print(f"JSON export saved to {output_file}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_results.py <results_csv> [--plot] [--json]", file=sys.stderr)
        print("Examples:", file=sys.stderr)
        print("  python3 analyze_results.py results.csv              # Text summary", file=sys.stderr)
        print("  python3 analyze_results.py results.csv --plot       # Text + plots", file=sys.stderr)
        print("  python3 analyze_results.py results.csv --json       # Text + JSON", file=sys.stderr)
        sys.exit(1)
    
    results_file = sys.argv[1]
    
    try:
        results = read_results_csv(results_file)
    except FileNotFoundError:
        print(f"Error: File not found: {results_file}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Generate text summary (always)
    generate_text_summary(results)
    
    # Check for optional flags
    if '--plot' in sys.argv:
        generate_plots(results)
    
    if '--json' in sys.argv:
        generate_json_export(results)


if __name__ == '__main__':
    main()
