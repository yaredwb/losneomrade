"""
Benchmark KD-Tree Optimization on Real Retrogression Cases

This script tests the new KD-Tree based slope computation methods in actual
retrogression workflows, comparing end-to-end performance.

It compares:
1. Current optimized retrogression (using compute_slope_chunked)
2. New KD-Tree vectorized retrogression (using compute_slope_kdtree_vectorized)

Usage:
    python scripts/benchmark_kdtree_real_cases.py
    python scripts/benchmark_kdtree_real_cases.py --subsets 5 10 25
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
import rasterio
from tqdm.auto import tqdm

# Add the src directory to the path
sys.path.append(os.path.abspath("src"))

try:
    from losneomrade import terrain_criteria, retrogression, utils
except ImportError:
    print("Could not import losneomrade. Make sure the 'src' directory is correctly structured.")
    sys.exit(1)

from scipy.ndimage import binary_dilation


def create_buffer(image: np.ndarray, buffer_size: int = 1):
    """Create a buffer around an image by performing binary dilation."""
    dilated_image = binary_dilation(image, iterations=buffer_size)
    buffer = dilated_image & (~image.astype(bool))
    return buffer


def apply_mask(array: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Apply a binary mask to a numpy array."""
    if mask is None:
        return array
    masked_array = array.copy()
    masked_array[mask == 0] = 0
    return masked_array


def landslide_retrogression_kdtree(dem: np.ndarray,
                                    initial_release: np.ndarray,
                                    dem_transform: rasterio.transform.Affine,
                                    min_slope: float = 1 / 15,
                                    min_height: float = 5,
                                    min_length: float = 200,
                                    max_length: float = 2000,
                                    initial_release_depth: float = 0,
                                    mask: np.ndarray = None,
                                    verbose: bool = False,
                                    k_neighbors: int = 50):
    """
    Landslide retrogression using KD-Tree vectorized slope computation.
    
    This is a modified version of landslide_retrogression_optimized that uses
    the new compute_slope_kdtree_vectorized function for faster slope calculations.
    """
    if verbose:
        print("Running landslide propagation (KD-Tree Optimized)...")
    
    res = abs(dem_transform[0])
    min_iter = int(min_length // res)
    max_iter = int(max_length // res)

    np.seterr(divide='ignore', invalid='ignore')

    # 1. Setup Source Points (Constant)
    i_rel, j_rel = np.where(initial_release == 1)
    x_rel, y_rel = rasterio.transform.xy(dem_transform, i_rel, j_rel)
    z_rel = np.array([dem[ii, jj] - initial_release_depth for ii, jj in zip(i_rel, j_rel)])
    source_coords = np.c_[x_rel, y_rel, z_rel]

    animation = [initial_release]
    
    # 2. Phase 1: Unconditional Expansion (min_length)
    current_release = initial_release.copy()
    
    for i in range(min_iter):
        buffered = create_buffer(current_release, 1) 
        buffered = apply_mask(buffered, mask)
        
        if not np.any(buffered):
            break
            
        current_release = current_release | buffered
        animation.append(current_release.copy())
        
    release = current_release

    # 3. Phase 2: Conditional Expansion (BFS with KD-Tree)
    checked = release.copy()
    
    candidates_mask = create_buffer(release, 1)
    candidates_mask = apply_mask(candidates_mask, mask)
    candidates_mask = candidates_mask & (~checked)
    
    n_iter = min_iter
    
    with tqdm(total=max_iter, initial=n_iter, desc="iterations", disable=not verbose) as pbar:
        while n_iter < max_iter:
            if not np.any(candidates_mask):
                break
                
            # Extract candidate coordinates
            i_cand, j_cand = np.where(candidates_mask == 1)
            x_cand, y_cand = rasterio.transform.xy(dem_transform, i_cand, j_cand)
            z_cand = np.array([dem[ii, jj] for ii, jj in zip(i_cand, j_cand)])
            cand_coords = np.c_[x_cand, y_cand, z_cand]
            
            # Filter source points to relevant area (same as optimized version)
            search_buffer = max(max_length, 2000) 
            
            c_xmin, c_ymin = np.min(cand_coords[:, :2], axis=0)
            c_xmax, c_ymax = np.max(cand_coords[:, :2], axis=0)
            
            s_xmin, s_ymin = c_xmin - search_buffer, c_ymin - search_buffer
            s_xmax, s_ymax = c_xmax + search_buffer, c_ymax + search_buffer
            
            relevant_mask = (
                (source_coords[:, 0] >= s_xmin) & 
                (source_coords[:, 0] <= s_xmax) & 
                (source_coords[:, 1] >= s_ymin) & 
                (source_coords[:, 1] <= s_ymax)
            )
            
            relevant_sources = source_coords[relevant_mask]
            
            if len(relevant_sources) == 0:
                slopes = np.zeros(len(cand_coords))
            else:
                # USE NEW KD-TREE VECTORIZED METHOD
                slopes = utils.compute_slope_kdtree_vectorized(
                    cand_coords, relevant_sources, h_min=min_height, k_neighbors=k_neighbors
                )
                
            # Identify successful candidates
            success_mask_local = slopes > min_slope
            
            if not np.any(success_mask_local):
                checked[i_cand, j_cand] = 1
                break
                
            # Update release with successful candidates
            i_success = i_cand[success_mask_local]
            j_success = j_cand[success_mask_local]
            
            new_release_pixels = np.zeros_like(release, dtype=bool)
            new_release_pixels[i_success, j_success] = 1
            
            release = release | new_release_pixels
            checked[i_cand, j_cand] = 1
            
            animation.append(release.copy())
            
            # Generate NEXT candidates
            new_candidates = create_buffer(new_release_pixels, 1)
            new_candidates = apply_mask(new_candidates, mask)
            candidates_mask = new_candidates & (~checked)
            
            n_iter += 1
            pbar.update(1)

    return release, animation


def run_benchmark(subsets, dem_file, output_dir):
    print("\n" + "="*80)
    print("BENCHMARKING KD-TREE OPTIMIZATION ON REAL RETROGRESSION CASES")
    print("="*80)
    
    # Parameters
    SOURCE_DEPTH = 0.0
    MIN_HEIGHT = 5.0
    MIN_SLOPE = 1 / 15
    MIN_LENGTH = 75.0
    POINTS_PER_METER = 1 / 10
    INITIAL_BUFFER = 10
    BUFFER_DISTANCE = 300
    
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    summary_data = []

    for subset in subsets:
        stream_file = f"data/streams_subset_{subset}.geojson"
        if not os.path.exists(stream_file):
            print(f"\n[SKIP] Stream file not found: {stream_file}")
            continue
            
        print(f"\n" + "-"*60)
        print(f"Processing Subset: {subset} streams")
        print("-"*60)
        
        # Load streams
        streams = gpd.read_file(stream_file)
        print(f"Loaded {len(streams)} stream features")

        # Calculate bounds
        bounds_array = streams.total_bounds
        bounds = (
            bounds_array[0] - BUFFER_DISTANCE,
            bounds_array[2] + BUFFER_DISTANCE,
            bounds_array[1] - BUFFER_DISTANCE,
            bounds_array[3] + BUFFER_DISTANCE,
        )

        # Generate source points
        try:
            source_points = terrain_criteria.generate_source_points(
                streams,
                distance_chainage=1 / POINTS_PER_METER,
            )
            print(f"Generated {len(source_points)} source points")
        except Exception as e:
            print(f"[ERROR] generating source points: {e}")
            continue

        # Create initial release zones
        try:
            point_geometries = [Point(x, y) for x, y in source_points[:, :2]]
            points_gdf = gpd.GeoDataFrame(geometry=point_geometries, crs=streams.crs)
            buffered = points_gdf.buffer(INITIAL_BUFFER)
            buffered_gdf = gpd.GeoDataFrame(geometry=buffered, crs=streams.crs)
            initial_release = buffered_gdf.dissolve()
        except Exception as e:
            print(f"[ERROR] creating initial release zones: {e}")
            continue

        # Prepare DEM
        dem_data = utils.generate_windows(dem_file)
        dem_array = dem_data["full_array"]
        dem_profile = dem_data["profile"]
        dem_transform = dem_profile["transform"]
        
        # Rasterize release
        rel = utils.rasterize_shape(initial_release, dem_profile)
        n_release_pixels = np.sum(rel)
        print(f"Initial release: {n_release_pixels} pixels")
        
        # Common arguments
        kwargs = {
            "dem": dem_array,
            "initial_release": rel,
            "dem_transform": dem_transform,
            "initial_release_depth": SOURCE_DEPTH,
            "min_slope": MIN_SLOPE,
            "min_height": MIN_HEIGHT,
            "min_length": MIN_LENGTH,
            "mask": None,
            "verbose": False
        }
        
        # 1. Run Current Optimized (chunked slope)
        print("\n[1] Running CURRENT OPTIMIZED (chunked slope)...")
        start_opt = time.time()
        try:
            release_opt, _ = retrogression.landslide_retrogression_optimized(
                **kwargs, slope_chunk_size=1000
            )
            time_opt = time.time() - start_opt
            area_opt = np.sum(release_opt)
            print(f"    Completed in {time_opt:.2f}s | Final area: {area_opt} pixels")
        except Exception as e:
            print(f"    [ERROR]: {e}")
            import traceback
            traceback.print_exc()
            time_opt = None
            release_opt = None
            area_opt = 0

        # 2. Run KD-Tree Vectorized (k=50)
        print("\n[2] Running KD-TREE VECTORIZED (k=50)...")
        start_kd50 = time.time()
        try:
            release_kd50, _ = landslide_retrogression_kdtree(
                **kwargs, k_neighbors=50
            )
            time_kd50 = time.time() - start_kd50
            area_kd50 = np.sum(release_kd50)
            print(f"    Completed in {time_kd50:.2f}s | Final area: {area_kd50} pixels")
        except Exception as e:
            print(f"    [ERROR]: {e}")
            import traceback
            traceback.print_exc()
            time_kd50 = None
            release_kd50 = None
            area_kd50 = 0

        # 3. Run KD-Tree Vectorized (k=100)
        print("\n[3] Running KD-TREE VECTORIZED (k=100)...")
        start_kd100 = time.time()
        try:
            release_kd100, _ = landslide_retrogression_kdtree(
                **kwargs, k_neighbors=100
            )
            time_kd100 = time.time() - start_kd100
            area_kd100 = np.sum(release_kd100)
            print(f"    Completed in {time_kd100:.2f}s | Final area: {area_kd100} pixels")
        except Exception as e:
            print(f"    [ERROR]: {e}")
            import traceback
            traceback.print_exc()
            time_kd100 = None
            release_kd100 = None
            area_kd100 = 0

        # 4. Run KD-Tree Vectorized (k=ALL - use all source points)
        n_sources = len(source_points)
        print(f"\n[4] Running KD-TREE VECTORIZED (k=ALL={n_sources})...")
        start_kdall = time.time()
        try:
            release_kdall, _ = landslide_retrogression_kdtree(
                **kwargs, k_neighbors=n_sources  # Use all source points
            )
            time_kdall = time.time() - start_kdall
            area_kdall = np.sum(release_kdall)
            print(f"    Completed in {time_kdall:.2f}s | Final area: {area_kdall} pixels")
        except Exception as e:
            print(f"    [ERROR]: {e}")
            import traceback
            traceback.print_exc()
            time_kdall = None
            release_kdall = None
            area_kdall = 0

        # Calculate metrics
        if release_opt is not None and release_kd50 is not None:
            # IoU between optimized and kd50
            intersection_50 = np.sum(release_opt & release_kd50)
            union_50 = np.sum(release_opt | release_kd50)
            iou_50 = intersection_50 / union_50 if union_50 > 0 else 1.0
            speedup_50 = time_opt / time_kd50 if time_kd50 > 0 else 0
        else:
            iou_50 = 0
            speedup_50 = 0

        if release_opt is not None and release_kd100 is not None:
            intersection_100 = np.sum(release_opt & release_kd100)
            union_100 = np.sum(release_opt | release_kd100)
            iou_100 = intersection_100 / union_100 if union_100 > 0 else 1.0
            speedup_100 = time_opt / time_kd100 if time_kd100 > 0 else 0
        else:
            iou_100 = 0
            speedup_100 = 0

        if release_opt is not None and release_kdall is not None:
            intersection_all = np.sum(release_opt & release_kdall)
            union_all = np.sum(release_opt | release_kdall)
            iou_all = intersection_all / union_all if union_all > 0 else 1.0
            speedup_all = time_opt / time_kdall if time_kdall > 0 else 0
        else:
            iou_all = 0
            speedup_all = 0

        print(f"\n--- Results for Subset {subset} ---")
        print(f"Current Optimized: {time_opt:.2f}s, {area_opt} pixels")
        if time_kd50:
            print(f"KD-Tree k=50:      {time_kd50:.2f}s, {area_kd50} pixels | Speedup: {speedup_50:.2f}x | IoU: {iou_50:.4f}")
        if time_kd100:
            print(f"KD-Tree k=100:     {time_kd100:.2f}s, {area_kd100} pixels | Speedup: {speedup_100:.2f}x | IoU: {iou_100:.4f}")
        if time_kdall:
            print(f"KD-Tree k=ALL:     {time_kdall:.2f}s, {area_kdall} pixels | Speedup: {speedup_all:.2f}x | IoU: {iou_all:.4f}")

        summary_data.append({
            "subset": subset,
            "n_source_points": len(source_points),
            "n_release_pixels": n_release_pixels,
            "time_optimized": time_opt,
            "time_kdtree_k50": time_kd50,
            "time_kdtree_k100": time_kd100,
            "speedup_k50": speedup_50,
            "speedup_k100": speedup_100,
            "area_optimized": area_opt,
            "area_kdtree_k50": area_kd50,
            "area_kdtree_k100": area_kd100,
            "iou_k50": iou_50,
            "iou_k100": iou_100
        })

        # Incremental save
        df = pd.DataFrame(summary_data)
        df.to_csv(os.path.join(output_dir, "kdtree_benchmark_results.csv"), index=False)

    # Final Summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    if summary_data:
        df = pd.DataFrame(summary_data)
        print(df.to_string(index=False))
        print(f"\nResults saved to {os.path.join(output_dir, 'kdtree_benchmark_results.csv')}")
        
        # Calculate averages
        avg_speedup_50 = df['speedup_k50'].mean()
        avg_speedup_100 = df['speedup_k100'].mean()
        avg_iou_50 = df['iou_k50'].mean()
        avg_iou_100 = df['iou_k100'].mean()
        
        print(f"\n--- Averages ---")
        print(f"KD-Tree k=50:  Avg Speedup: {avg_speedup_50:.2f}x | Avg IoU: {avg_iou_50:.4f}")
        print(f"KD-Tree k=100: Avg Speedup: {avg_speedup_100:.2f}x | Avg IoU: {avg_iou_100:.4f}")
    else:
        print("No successful benchmarks.")


def main():
    parser = argparse.ArgumentParser(description="Benchmark KD-Tree on Real Retrogression Cases")
    parser.add_argument("--subsets", nargs="+", type=int, default=[1, 5, 10, 15, 25, 50, 100], 
                        help="List of subsets to process")
    parser.add_argument("--dem-file", default="data/dem_byneset_5m.tif", help="Path to DEM file")
    parser.add_argument("--output-dir", default="output/benchmark_kdtree_real", 
                        help="Directory to save results")
    args = parser.parse_args()
    
    run_benchmark(args.subsets, args.dem_file, args.output_dir)


if __name__ == "__main__":
    main()
