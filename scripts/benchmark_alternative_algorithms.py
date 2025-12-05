"""
Benchmark Alternative Algorithms vs Original Methods

This script compares the fundamentally different algorithmic approaches:

TERRAIN CRITERIA:
- Original: Point-to-point distance matrix (O(N*M))
- Single Cone: Distance transform + nearest source slope (O(N))
- Multi Cone: KD-Tree k-nearest + max slope (O(N*k))

RETROGRESSION:
- Original/Optimized: Iterative BFS expansion
- Fast Marching: Eikonal equation solver (O(N log N))
- Cost Distance: Scipy-based accumulated cost
- Graph-based: Dijkstra shortest path

Usage:
    python scripts/benchmark_alternative_algorithms.py
    python scripts/benchmark_alternative_algorithms.py --subsets 5 10 25
"""
import sys
import os
import argparse
import time
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Point
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from matplotlib.patches import Patch

# Add the src directory to the path
sys.path.append(os.path.abspath("src"))

try:
    from losneomrade import terrain_criteria, retrogression, utils
    from losneomrade import alternative_algorithms as alt
except ImportError as e:
    print(f"Could not import losneomrade: {e}")
    sys.exit(1)


def run_benchmark(subsets, dem_file, output_dir):
    print("\n" + "="*80)
    print("BENCHMARKING ALTERNATIVE ALGORITHMS")
    print("="*80)
    
    # Parameters
    SOURCE_DEPTH = 0.0
    MIN_HEIGHT = 5.0
    MIN_SLOPE = 1 / 15
    MIN_LENGTH = 75.0
    MAX_LENGTH = 2000.0
    POINTS_PER_METER = 1 / 10
    INITIAL_BUFFER = 10
    BUFFER_DISTANCE = 300
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    summary_data = []

    for subset in subsets:
        stream_file = f"data/streams_subset_{subset}.geojson"
        if not os.path.exists(stream_file):
            print(f"\n[SKIP] Stream file not found: {stream_file}")
            continue
            
        print(f"\n" + "="*60)
        print(f"Processing Subset: {subset} streams")
        print("="*60)
        
        # Load data
        streams = gpd.read_file(stream_file)
        print(f"Loaded {len(streams)} stream features")

        bounds_array = streams.total_bounds
        bounds = (
            bounds_array[0] - BUFFER_DISTANCE,
            bounds_array[2] + BUFFER_DISTANCE,
            bounds_array[1] - BUFFER_DISTANCE,
            bounds_array[3] + BUFFER_DISTANCE,
        )

        # Generate source points
        source_points_2d = terrain_criteria.generate_source_points(
            streams, distance_chainage=1 / POINTS_PER_METER
        )
        print(f"Generated {len(source_points_2d)} source points")

        # Create initial release
        point_geometries = [Point(x, y) for x, y in source_points_2d[:, :2]]
        points_gdf = gpd.GeoDataFrame(geometry=point_geometries, crs=streams.crs)
        buffered = points_gdf.buffer(INITIAL_BUFFER)
        buffered_gdf = gpd.GeoDataFrame(geometry=buffered, crs=streams.crs)
        initial_release_gdf = buffered_gdf.dissolve()

        # Load DEM
        dem_data = utils.generate_windows(dem_file)
        dem_array = dem_data["full_array"]
        dem_profile = dem_data["profile"]
        dem_transform = dem_profile["transform"]
        
        # Rasterize release
        rel = utils.rasterize_shape(initial_release_gdf, dem_profile)
        n_release_pixels = np.sum(rel)
        print(f"Initial release: {n_release_pixels} pixels")
        
        # Add Z values to source points
        source_points_3d = utils.set_z_from_raster(source_points_2d, dem_data)
        print(f"Source points with Z: {len(source_points_3d)}")
        
        results = {}
        
        # ================================================================
        # RETROGRESSION BENCHMARKS
        # ================================================================
        print("\n--- RETROGRESSION METHODS ---")
        
        # 1. Original Optimized (BFS)
        print("\n[1] Original Optimized (BFS)...")
        start = time.time()
        try:
            release_bfs, _ = retrogression.landslide_retrogression_optimized(
                dem=dem_array,
                initial_release=rel,
                dem_transform=dem_transform,
                min_slope=MIN_SLOPE,
                min_height=MIN_HEIGHT,
                min_length=MIN_LENGTH,
                max_length=MAX_LENGTH,
                initial_release_depth=SOURCE_DEPTH,
                mask=None,
                verbose=False,
                slope_chunk_size=1000
            )
            time_bfs = time.time() - start
            area_bfs = np.sum(release_bfs)
            print(f"    Time: {time_bfs:.2f}s | Area: {area_bfs} pixels")
            results['bfs'] = {'time': time_bfs, 'area': area_bfs, 'release': release_bfs}
        except Exception as e:
            print(f"    [ERROR]: {e}")
            results['bfs'] = None
        
        # 2. Morphological Accurate (k=ALL sources)
        print("\n[2] Morphological Accurate (k=ALL)...")
        start = time.time()
        try:
            release_morph_all, _ = alt.retrogression_morphological_accurate(
                dem=dem_array,
                initial_release=rel,
                dem_transform=dem_transform,
                min_slope=MIN_SLOPE,
                min_height=MIN_HEIGHT,
                min_length=MIN_LENGTH,
                max_length=MAX_LENGTH,
                initial_release_depth=SOURCE_DEPTH,
                mask=None,
                k_sources=None  # Check ALL sources
            )
            time_morph_all = time.time() - start
            area_morph_all = np.sum(release_morph_all)
            print(f"    Time: {time_morph_all:.2f}s | Area: {area_morph_all} pixels")
            results['morph_all'] = {'time': time_morph_all, 'area': area_morph_all, 'release': release_morph_all}
        except Exception as e:
            print(f"    [ERROR]: {e}")
            import traceback
            traceback.print_exc()
            results['morph_all'] = None
        
        # 3. Morphological Accurate (k=50 nearest)
        print("\n[3] Morphological Accurate (k=50)...")
        start = time.time()
        try:
            release_morph_50, _ = alt.retrogression_morphological_accurate(
                dem=dem_array,
                initial_release=rel,
                dem_transform=dem_transform,
                min_slope=MIN_SLOPE,
                min_height=MIN_HEIGHT,
                min_length=MIN_LENGTH,
                max_length=MAX_LENGTH,
                initial_release_depth=SOURCE_DEPTH,
                mask=None,
                k_sources=50  # Check 50 nearest sources
            )
            time_morph_50 = time.time() - start
            area_morph_50 = np.sum(release_morph_50)
            print(f"    Time: {time_morph_50:.2f}s | Area: {area_morph_50} pixels")
            results['morph_k50'] = {'time': time_morph_50, 'area': area_morph_50, 'release': release_morph_50}
        except Exception as e:
            print(f"    [ERROR]: {e}")
            import traceback
            traceback.print_exc()
            results['morph_k50'] = None
        
        # 4. Fast Marching (if available)
        print("\n[4] Fast Marching Method...")
        start = time.time()
        try:
            release_fm, _ = alt.retrogression_fast_marching(
                dem=dem_array,
                initial_release=rel,
                dem_transform=dem_transform,
                min_slope=MIN_SLOPE,
                min_height=MIN_HEIGHT,
                min_length=MIN_LENGTH,
                max_length=MAX_LENGTH,
                initial_release_depth=SOURCE_DEPTH,
                mask=None
            )
            time_fm = time.time() - start
            area_fm = np.sum(release_fm)
            print(f"    Time: {time_fm:.2f}s | Area: {area_fm} pixels")
            results['fast_marching'] = {'time': time_fm, 'area': area_fm, 'release': release_fm}
        except Exception as e:
            print(f"    [ERROR]: {e}")
            results['fast_marching'] = None
        
        # 4. Graph-based (Dijkstra) - skip for large datasets
        if n_release_pixels < 5000:  # Only for small cases
            print("\n[4] Graph-based (Dijkstra)...")
            start = time.time()
            try:
                release_graph, _ = alt.retrogression_graph_based(
                    dem=dem_array,
                    initial_release=rel,
                    dem_transform=dem_transform,
                    min_slope=MIN_SLOPE,
                    min_height=MIN_HEIGHT,
                    min_length=MIN_LENGTH,
                    max_length=MAX_LENGTH,
                    initial_release_depth=SOURCE_DEPTH,
                    mask=None
                )
                time_graph = time.time() - start
                area_graph = np.sum(release_graph)
                print(f"    Time: {time_graph:.2f}s | Area: {area_graph} pixels")
                results['graph'] = {'time': time_graph, 'area': area_graph, 'release': release_graph}
            except Exception as e:
                print(f"    [ERROR]: {e}")
                results['graph'] = None
        else:
            print("\n[4] Graph-based (Dijkstra) - SKIPPED (too large)")
            results['graph'] = None
        
        # ================================================================
        # TERRAIN CRITERIA BENCHMARKS
        # ================================================================
        print("\n--- TERRAIN CRITERIA METHODS ---")
        
        # 5. Single Cone (nearest source)
        print("\n[5] Single Cone (nearest source)...")
        start = time.time()
        try:
            slope_single = alt.terrain_criteria_raster_cone(
                dem=dem_array,
                source_points=source_points_3d,
                dem_transform=dem_transform,
                h_min=MIN_HEIGHT,
                min_slope=MIN_SLOPE
            )
            time_single = time.time() - start
            valid_pixels = np.sum(slope_single > -9999)
            print(f"    Time: {time_single:.2f}s | Valid pixels: {valid_pixels}")
            results['single_cone'] = {'time': time_single, 'valid': valid_pixels, 'slope': slope_single}
        except Exception as e:
            print(f"    [ERROR]: {e}")
            import traceback
            traceback.print_exc()
            results['single_cone'] = None
        
        # 6. Multi Cone (k-nearest sources)
        print("\n[6] Multi Cone (k=5 nearest)...")
        start = time.time()
        try:
            slope_multi = alt.terrain_criteria_multi_cone(
                dem=dem_array,
                source_points=source_points_3d,
                dem_transform=dem_transform,
                h_min=MIN_HEIGHT,
                n_nearest=5
            )
            time_multi = time.time() - start
            valid_pixels_multi = np.sum(slope_multi > -9999)
            print(f"    Time: {time_multi:.2f}s | Valid pixels: {valid_pixels_multi}")
            results['multi_cone'] = {'time': time_multi, 'valid': valid_pixels_multi, 'slope': slope_multi}
        except Exception as e:
            print(f"    [ERROR]: {e}")
            import traceback
            traceback.print_exc()
            results['multi_cone'] = None
        
        # ================================================================
        # COMPARISON METRICS
        # ================================================================
        print("\n--- COMPARISON ---")
        
        if results.get('bfs') and results.get('morph_all'):
            iou_morph_all = compute_iou(results['bfs']['release'], results['morph_all']['release'])
            speedup_morph_all = results['bfs']['time'] / results['morph_all']['time']
            print(f"Morph ALL vs BFS: IoU={iou_morph_all:.4f}, Speedup={speedup_morph_all:.2f}x")
        else:
            iou_morph_all, speedup_morph_all = None, None
            
        if results.get('bfs') and results.get('morph_k50'):
            iou_morph_k50 = compute_iou(results['bfs']['release'], results['morph_k50']['release'])
            speedup_morph_k50 = results['bfs']['time'] / results['morph_k50']['time']
            print(f"Morph k=50 vs BFS: IoU={iou_morph_k50:.4f}, Speedup={speedup_morph_k50:.2f}x")
        else:
            iou_morph_k50, speedup_morph_k50 = None, None
            
        if results.get('bfs') and results.get('fast_marching'):
            iou_fm = compute_iou(results['bfs']['release'], results['fast_marching']['release'])
            speedup_fm = results['bfs']['time'] / results['fast_marching']['time']
            print(f"Fast Marching vs BFS: IoU={iou_fm:.4f}, Speedup={speedup_fm:.2f}x")
        else:
            iou_fm, speedup_fm = None, None
        
        # Store summary
        summary_data.append({
            'subset': subset,
            'n_source_points': len(source_points_3d),
            'n_release_pixels': n_release_pixels,
            'time_bfs': results.get('bfs', {}).get('time'),
            'time_morph_all': results.get('morph_all', {}).get('time') if results.get('morph_all') else None,
            'time_morph_k50': results.get('morph_k50', {}).get('time') if results.get('morph_k50') else None,
            'time_fast_marching': results.get('fast_marching', {}).get('time') if results.get('fast_marching') else None,
            'time_graph': results.get('graph', {}).get('time') if results.get('graph') else None,
            'time_single_cone': results.get('single_cone', {}).get('time') if results.get('single_cone') else None,
            'time_multi_cone': results.get('multi_cone', {}).get('time') if results.get('multi_cone') else None,
            'iou_morph_all': iou_morph_all,
            'iou_morph_k50': iou_morph_k50,
            'iou_fast_marching': iou_fm,
            'speedup_morph_all': speedup_morph_all,
            'speedup_morph_k50': speedup_morph_k50,
            'speedup_fast_marching': speedup_fm,
        })
        
        # Save incremental results
        df = pd.DataFrame(summary_data)
        df.to_csv(os.path.join(output_dir, "alternative_benchmark_results.csv"), index=False)
        
        # Generate comparison plot
        if results.get('bfs'):
            try:
                generate_comparison_plot(
                    dem_array, dem_transform, results, subset, 
                    os.path.join(output_dir, f"comparison_subset_{subset}.png")
                )
            except Exception as e:
                print(f"[WARN] Plot generation failed: {e}")

    # Final summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    if summary_data:
        df = pd.DataFrame(summary_data)
        print(df.to_string(index=False))
        print(f"\nResults saved to {os.path.join(output_dir, 'alternative_benchmark_results.csv')}")


def compute_iou(release1, release2):
    """Compute Intersection over Union between two binary masks."""
    intersection = np.sum(release1 & release2)
    union = np.sum(release1 | release2)
    return intersection / union if union > 0 else 1.0


def generate_comparison_plot(dem, transform, results, subset, output_path):
    """Generate comparison plot of different methods."""
    n_methods = sum(1 for k in ['bfs', 'morph_all', 'morph_k50', 'fast_marching'] if results.get(k))
    
    if n_methods == 0:
        return
    
    fig, axes = plt.subplots(1, min(n_methods, 4), figsize=(5*min(n_methods, 4), 5))
    if n_methods == 1:
        axes = [axes]
    
    ls = LightSource(azdeg=315, altdeg=45)
    hs = ls.hillshade(dem)
    
    methods = ['bfs', 'morph_all', 'morph_k50', 'fast_marching']
    method_names = ['Original BFS', 'Morph (all)', 'Morph (k=50)', 'Fast Marching']
    
    ax_idx = 0
    for method, name in zip(methods, method_names):
        if results.get(method) and ax_idx < len(axes):
            ax = axes[ax_idx]
            ax.imshow(hs, cmap='gray', alpha=0.7)
            
            release = results[method]['release']
            masked = np.ma.masked_where(release == 0, release)
            ax.imshow(masked, cmap='Reds', alpha=0.5)
            
            time_s = results[method]['time']
            area = results[method]['area']
            ax.set_title(f"{name}\nTime: {time_s:.2f}s | Area: {area}")
            ax.axis('off')
            ax_idx += 1
    
    fig.suptitle(f"Retrogression Methods Comparison - Subset {subset}", fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved plot to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark Alternative Algorithms")
    parser.add_argument("--subsets", nargs="+", type=int, default=[1, 5, 10], 
                        help="List of subsets to process")
    parser.add_argument("--dem-file", default="data/dem_byneset_5m.tif", help="Path to DEM file")
    parser.add_argument("--output-dir", default="output/benchmark_alternative_algorithms", 
                        help="Directory to save results")
    args = parser.parse_args()
    
    run_benchmark(args.subsets, args.dem_file, args.output_dir)


if __name__ == "__main__":
    main()
