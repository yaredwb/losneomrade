"""
Benchmark script to compare KD-Tree based slope computation vs original methods.

This script tests:
1. Original compute_slope (full distance matrix)
2. Chunked compute_slope_chunked
3. New KD-Tree based compute_slope_kdtree
4. Batch KD-Tree compute_slope_kdtree_batch

Usage:
    python scripts/benchmark_kdtree.py
"""

import time
import numpy as np
import geopandas as gpd
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from losneomrade import utils


def generate_test_data(n_coords: int, n_points: int, seed: int = 42):
    """Generate synthetic test data for benchmarking."""
    np.random.seed(seed)
    
    # Generate DEM coordinates (simulate a raster grid)
    grid_size = int(np.sqrt(n_coords))
    x = np.linspace(0, 5000, grid_size)
    y = np.linspace(0, 5000, grid_size)
    xx, yy = np.meshgrid(x, y)
    
    # Simulate terrain with a slope
    zz = 100 + xx * 0.05 + yy * 0.03 + np.random.randn(grid_size, grid_size) * 2
    
    coords = np.c_[xx.flatten(), yy.flatten(), zz.flatten()]
    
    # Generate source points (e.g., stream locations at lower elevations)
    points_x = np.random.uniform(0, 5000, n_points)
    points_y = np.random.uniform(0, 5000, n_points)
    # Source points at lower elevation
    points_z = 50 + points_x * 0.02 + np.random.randn(n_points) * 1
    
    points = np.c_[points_x, points_y, points_z]
    
    return coords, points


def benchmark_method(func, coords, points, name, **kwargs):
    """Run benchmark for a single method."""
    # Warmup
    _ = func(coords[:100], points[:min(100, len(points))], **kwargs)
    
    # Timed run
    start = time.perf_counter()
    result = func(coords, points, **kwargs)
    elapsed = time.perf_counter() - start
    
    # Compute statistics
    valid_count = np.sum(result > -9999)
    
    return {
        "name": name,
        "time_s": elapsed,
        "valid_pixels": valid_count,
        "result": result
    }


def compare_results(results: dict, baseline_name: str = "original"):
    """Compare results between methods for accuracy."""
    baseline = results[baseline_name]["result"]
    
    print("\n=== Accuracy Comparison (vs baseline) ===")
    for name, data in results.items():
        if name == baseline_name:
            continue
        
        result = data["result"]
        
        # Compare where both have valid values
        both_valid = (baseline > -9999) & (result > -9999)
        
        if np.sum(both_valid) > 0:
            diff = np.abs(baseline[both_valid] - result[both_valid])
            max_diff = np.max(diff)
            mean_diff = np.mean(diff)
            
            # Check for matching valid pixels
            baseline_valid = baseline > -9999
            result_valid = result > -9999
            matching = np.sum(baseline_valid == result_valid) / len(baseline)
            
            print(f"\n{name}:")
            print(f"  Max absolute difference: {max_diff:.8f}")
            print(f"  Mean absolute difference: {mean_diff:.8f}")
            print(f"  Valid pixel match: {matching*100:.2f}%")
        else:
            print(f"\n{name}: No overlapping valid pixels to compare")


def main():
    print("=" * 60)
    print("KD-Tree Slope Computation Benchmark")
    print("=" * 60)
    
    # Test configurations
    test_configs = [
        # (n_coords, n_points, description)
        (10000, 100, "Small: 10K coords, 100 points"),
        (10000, 1000, "Medium: 10K coords, 1K points"),
        (100000, 1000, "Large: 100K coords, 1K points"),
        (100000, 5000, "XLarge: 100K coords, 5K points"),
    ]
    
    for n_coords, n_points, description in test_configs:
        print(f"\n{'='*60}")
        print(f"Test: {description}")
        print(f"{'='*60}")
        
        coords, points = generate_test_data(n_coords, n_points)
        results = {}
        
        # 1. Original method (skip for very large tests)
        if n_coords * n_points < 500_000_000:  # Skip if would need >4GB RAM
            print("\nRunning: Original (full distance matrix)...")
            results["original"] = benchmark_method(
                utils.compute_slope, coords, points, "original"
            )
            print(f"  Time: {results['original']['time_s']:.3f}s")
        else:
            print("\nSkipping original method (too large for memory)")
        
        # 2. Chunked method
        print("\nRunning: Chunked...")
        results["chunked"] = benchmark_method(
            utils.compute_slope_chunked, coords, points, "chunked",
            chunk_size=500
        )
        print(f"  Time: {results['chunked']['time_s']:.3f}s")
        
        # 3. KD-Tree with radius search
        print("\nRunning: KD-Tree (radius=2000m)...")
        results["kdtree_r2000"] = benchmark_method(
            utils.compute_slope_kdtree, coords, points, "kdtree_r2000",
            max_search_radius=2000
        )
        print(f"  Time: {results['kdtree_r2000']['time_s']:.3f}s")
        
        # 4. KD-Tree with smaller radius
        print("\nRunning: KD-Tree (radius=500m)...")
        results["kdtree_r500"] = benchmark_method(
            utils.compute_slope_kdtree, coords, points, "kdtree_r500",
            max_search_radius=500
        )
        print(f"  Time: {results['kdtree_r500']['time_s']:.3f}s")
        
        # 5. KD-Tree batch
        print("\nRunning: KD-Tree Batch (radius=2000m)...")
        results["kdtree_batch"] = benchmark_method(
            utils.compute_slope_kdtree_batch, coords, points, "kdtree_batch",
            max_search_radius=2000, batch_size=5000
        )
        print(f"  Time: {results['kdtree_batch']['time_s']:.3f}s")
        
        # 6. KD-Tree with k-nearest
        print("\nRunning: KD-Tree (k=50 nearest)...")
        results["kdtree_k50"] = benchmark_method(
            utils.compute_slope_kdtree, coords, points, "kdtree_k50",
            k_neighbors=50
        )
        print(f"  Time: {results['kdtree_k50']['time_s']:.3f}s")
        
        # 7. NEW: Vectorized KD-Tree (fastest)
        print("\nRunning: KD-Tree Vectorized (k=50)...")
        results["kdtree_vec50"] = benchmark_method(
            utils.compute_slope_kdtree_vectorized, coords, points, "kdtree_vec50",
            k_neighbors=50
        )
        print(f"  Time: {results['kdtree_vec50']['time_s']:.3f}s")
        
        # 8. Vectorized with more neighbors for accuracy
        print("\nRunning: KD-Tree Vectorized (k=100)...")
        results["kdtree_vec100"] = benchmark_method(
            utils.compute_slope_kdtree_vectorized, coords, points, "kdtree_vec100",
            k_neighbors=100
        )
        print(f"  Time: {results['kdtree_vec100']['time_s']:.3f}s")
        
        # 9. Hybrid method
        print("\nRunning: KD-Tree Hybrid...")
        results["kdtree_hybrid"] = benchmark_method(
            utils.compute_slope_hybrid, coords, points, "kdtree_hybrid",
            k_initial=20
        )
        print(f"  Time: {results['kdtree_hybrid']['time_s']:.3f}s")
        
        # Summary
        print("\n--- Timing Summary ---")
        baseline_time = results.get("original", results.get("chunked"))["time_s"]
        for name, data in sorted(results.items(), key=lambda x: x[1]["time_s"]):
            speedup = baseline_time / data["time_s"] if data["time_s"] > 0 else float('inf')
            print(f"  {name:20s}: {data['time_s']:8.3f}s ({speedup:5.2f}x speedup)")
        
        # Accuracy comparison
        if "original" in results:
            compare_results(results, "original")
        elif "chunked" in results:
            compare_results(results, "chunked")


def test_real_data():
    """Test with real data from the project if available."""
    print("\n" + "=" * 60)
    print("Testing with Real Project Data")
    print("=" * 60)
    
    data_dir = Path(__file__).parent.parent / "data"
    
    # Check for test data
    streams_file = data_dir / "streams_subset_100.geojson"
    dem_file = data_dir / "dem_byneset_5m.tif.aux.xml"
    
    if not streams_file.exists():
        print(f"No test data found at {streams_file}")
        return
    
    print(f"\nLoading streams from {streams_file}...")
    streams = gpd.read_file(streams_file)
    print(f"  Loaded {len(streams)} stream features")
    
    # Generate source points from streams
    from losneomrade import terrain_criteria
    source_points = terrain_criteria.generate_source_points(streams)
    print(f"  Generated {len(source_points)} source points")
    
    # Create synthetic DEM coords for testing
    bounds = streams.total_bounds
    grid_size = 500
    x = np.linspace(bounds[0], bounds[2], grid_size)
    y = np.linspace(bounds[1], bounds[3], grid_size)
    xx, yy = np.meshgrid(x, y)
    zz = np.random.uniform(50, 150, (grid_size, grid_size))
    
    coords = np.c_[xx.flatten(), yy.flatten(), zz.flatten()]
    
    # Add z values to source points
    points = np.c_[source_points, np.random.uniform(40, 60, len(source_points))]
    
    print(f"\nBenchmark: {len(coords)} coords, {len(points)} source points")
    
    # Run benchmarks
    results = {}
    
    print("\nRunning: Chunked...")
    results["chunked"] = benchmark_method(
        utils.compute_slope_chunked, coords, points, "chunked",
        chunk_size=500
    )
    print(f"  Time: {results['chunked']['time_s']:.3f}s")
    
    print("\nRunning: KD-Tree (radius=2000m)...")
    results["kdtree_r2000"] = benchmark_method(
        utils.compute_slope_kdtree, coords, points, "kdtree_r2000",
        max_search_radius=2000
    )
    print(f"  Time: {results['kdtree_r2000']['time_s']:.3f}s")
    
    print("\nRunning: KD-Tree Batch...")
    results["kdtree_batch"] = benchmark_method(
        utils.compute_slope_kdtree_batch, coords, points, "kdtree_batch",
        max_search_radius=2000
    )
    print(f"  Time: {results['kdtree_batch']['time_s']:.3f}s")
    
    print("\nRunning: KD-Tree Vectorized (k=50)...")
    results["kdtree_vec50"] = benchmark_method(
        utils.compute_slope_kdtree_vectorized, coords, points, "kdtree_vec50",
        k_neighbors=50
    )
    print(f"  Time: {results['kdtree_vec50']['time_s']:.3f}s")
    
    print("\nRunning: KD-Tree Vectorized (k=100)...")
    results["kdtree_vec100"] = benchmark_method(
        utils.compute_slope_kdtree_vectorized, coords, points, "kdtree_vec100",
        k_neighbors=100
    )
    print(f"  Time: {results['kdtree_vec100']['time_s']:.3f}s")
    
    print("\nRunning: KD-Tree Hybrid...")
    results["kdtree_hybrid"] = benchmark_method(
        utils.compute_slope_hybrid, coords, points, "kdtree_hybrid",
        k_initial=20
    )
    print(f"  Time: {results['kdtree_hybrid']['time_s']:.3f}s")
    
    # Summary
    print("\n--- Timing Summary ---")
    baseline_time = results["chunked"]["time_s"]
    for name, data in sorted(results.items(), key=lambda x: x[1]["time_s"]):
        speedup = baseline_time / data["time_s"] if data["time_s"] > 0 else float('inf')
        print(f"  {name:20s}: {data['time_s']:8.3f}s ({speedup:5.2f}x speedup)")


if __name__ == "__main__":
    main()
    test_real_data()
