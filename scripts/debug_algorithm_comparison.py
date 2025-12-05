"""
Debug script to understand the differences between BFS original and morphological methods.
"""
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from losneomrade import retrogression, utils, alternative_algorithms as alt, terrain_criteria
from scipy.spatial import cKDTree
from scipy.ndimage import binary_dilation, generate_binary_structure
import rasterio

# Parameters
MIN_SLOPE = 1/15
MIN_HEIGHT = 5
MIN_LENGTH = 75
MAX_LENGTH = 2000
SOURCE_DEPTH = 0
INITIAL_BUFFER = 3
POINTS_PER_METER = 0.04  # 1 point per 25 meters


def run_morphological_detailed(dem, initial_release, dem_transform, min_slope, min_height,
                                min_length, max_length, initial_release_depth, mask, k_sources):
    """Run morphological with detailed logging."""
    
    resolution = abs(dem_transform[0])
    height, width = dem.shape
    
    i_rel, j_rel = np.where(initial_release == 1)
    if len(i_rel) == 0:
        return initial_release.copy(), []
    
    # Build source coordinates
    x_rel, y_rel = rasterio.transform.xy(dem_transform, i_rel, j_rel)
    z_rel = np.array([dem[ii, jj] - initial_release_depth for ii, jj in zip(i_rel, j_rel)])
    source_coords = np.c_[x_rel, y_rel, z_rel]
    
    # Build KD-tree
    tree = cKDTree(source_coords[:, :2])
    
    n_sources = len(source_coords)
    k = n_sources if k_sources is None else min(k_sources, n_sources)
    
    # IMPORTANT: Use 4-connectivity (default) to match original BFS
    struct = None  # Use default (4-connectivity)
    
    # Phase 1: Unconditional expansion
    min_iter = int(min_length // resolution)
    release = initial_release.copy().astype(bool)
    
    print(f"  Phase 1: {min_iter} unconditional iterations")
    for _ in range(min_iter):
        dilated = binary_dilation(release, structure=struct)
        rim = dilated & ~release
        if mask is not None:
            rim = rim & (mask > 0)
        if not np.any(rim):
            break
        release = release | rim
    
    print(f"  After Phase 1: {np.sum(release)} pixels")
    
    # Phase 2: Conditional expansion
    max_iter = int((max_length - min_length) // resolution)
    checked = release.copy()
    
    # Initial candidates
    current_release = release.copy()
    dilated = binary_dilation(current_release, structure=struct)
    candidates_mask = dilated & ~current_release & ~checked
    if mask is not None:
        candidates_mask = candidates_mask & (mask > 0)
    
    n_iter = 0
    last_print = 0
    
    while n_iter < max_iter:
        if not np.any(candidates_mask):
            print(f"  Iteration {n_iter}: No more candidates, stopping")
            break
        
        n_candidates = np.sum(candidates_mask)
        
        # Get candidate coordinates
        i_cand, j_cand = np.where(candidates_mask)
        x_cand, y_cand = rasterio.transform.xy(dem_transform, i_cand, j_cand)
        z_cand = dem[i_cand, j_cand]
        xy_cand = np.c_[x_cand, y_cand]
        
        # Query k nearest sources
        distances, indices = tree.query(xy_cand, k=k, workers=-1)
        if k == 1:
            distances = distances.reshape(-1, 1)
            indices = indices.reshape(-1, 1)
        
        # Get source Z values
        source_z_neighbors = source_coords[indices, 2]
        
        # Compute height differences and slopes
        height_diff = z_cand[:, np.newaxis] - source_z_neighbors
        with np.errstate(divide='ignore', invalid='ignore'):
            slopes = height_diff / np.maximum(distances, 1e-10)
        
        # Check criteria
        valid = (height_diff >= min_height) & (slopes > min_slope)
        any_valid = np.any(valid, axis=1)
        n_passing = np.sum(any_valid)
        
        if n_iter - last_print >= 50:
            print(f"  Iteration {n_iter}: {n_candidates} candidates, {n_passing} passing, area={np.sum(release)}")
            last_print = n_iter
        
        if not np.any(any_valid):
            checked[i_cand, j_cand] = True
            print(f"  Iteration {n_iter}: No candidates passing, stopping")
            break
        
        # Find successful candidates
        success_indices = np.where(any_valid)[0]
        i_success = i_cand[success_indices]
        j_success = j_cand[success_indices]
        
        # Create mask of newly added pixels
        new_release_pixels = np.zeros_like(release, dtype=bool)
        new_release_pixels[i_success, j_success] = True
        
        # Update release
        release = release | new_release_pixels
        checked[i_cand, j_cand] = True
        
        # Generate NEXT candidates from ONLY the newly added pixels
        new_candidates = binary_dilation(new_release_pixels, structure=struct)
        new_candidates = new_candidates & ~checked
        if mask is not None:
            new_candidates = new_candidates & (mask > 0)
        
        candidates_mask = new_candidates
        n_iter += 1
    
    print(f"  Phase 2 ended after {n_iter} iterations, final area: {np.sum(release)}")
    return release.astype(np.int32), []


def debug_comparison():
    # Load data
    dem_file = "data/dem_byneset_5m.tif"
    streams_file = "data/streams_subset_1.geojson"
    
    streams = gpd.read_file(streams_file)
    source_points_2d = terrain_criteria.generate_source_points(
        streams, distance_chainage=1 / POINTS_PER_METER
    )
    print(f"Source points: {len(source_points_2d)}")
    
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
    print(f"Initial release pixels: {np.sum(rel)}")
    
    # Run original BFS
    print("\n=== Running Original BFS ===")
    release_bfs, anim_bfs = retrogression.landslide_retrogression_optimized(
        dem=dem_array,
        initial_release=rel,
        dem_transform=dem_transform,
        min_slope=MIN_SLOPE,
        min_height=MIN_HEIGHT,
        min_length=MIN_LENGTH,
        max_length=MAX_LENGTH,
        initial_release_depth=SOURCE_DEPTH,
        mask=None,
        verbose=True,
        slope_chunk_size=1000
    )
    print(f"BFS final area: {np.sum(release_bfs)}")
    
    # Run morphological with detailed tracing
    print("\n=== Running Morphological (k=ALL) ===")
    release_morph, _ = run_morphological_detailed(
        dem=dem_array,
        initial_release=rel,
        dem_transform=dem_transform,
        min_slope=MIN_SLOPE,
        min_height=MIN_HEIGHT,
        min_length=MIN_LENGTH,
        max_length=MAX_LENGTH,
        initial_release_depth=SOURCE_DEPTH,
        mask=None,
        k_sources=None
    )
    print(f"Morph final area: {np.sum(release_morph)}")
    
    # Compare
    bfs_only = release_bfs & ~release_morph
    morph_only = release_morph & ~release_bfs
    both = release_bfs & release_morph
    
    print(f"\n=== COMPARISON ===")
    print(f"BFS only: {np.sum(bfs_only)}")
    print(f"Morph only: {np.sum(morph_only)}")
    print(f"Both: {np.sum(both)}")
    print(f"IoU: {np.sum(both) / np.sum(release_bfs | release_morph):.4f}")
    

if __name__ == "__main__":
    debug_comparison()

    debug_comparison()
