"""
Alternative Algorithms for Landslide Release Area Estimation

This module implements fundamentally different algorithmic approaches to solve
the same problem as terrain_criteria.py and retrogression.py.

Methods implemented:
1. Raster Cone Method - Vectorized raster operations for terrain criteria
2. Fast Marching Method - Eikonal equation solver for retrogression
3. Cost Distance Method - Scipy-based cost accumulation

These are experimental alternatives that may offer better performance
or different trade-offs compared to the original implementations.
"""

import numpy as np
import rasterio
import geopandas as gpd
from scipy import ndimage
from scipy.ndimage import distance_transform_edt
from typing import Tuple, Optional
import warnings

warnings.simplefilter(action='ignore', category=UserWarning)


# ============================================================================
# METHOD 1: RASTER CONE (Alternative to Terrain Criteria)
# ============================================================================

def terrain_criteria_raster_cone(dem: np.ndarray,
                                  source_points: np.ndarray,
                                  dem_transform: rasterio.transform.Affine,
                                  h_min: float = 5.0,
                                  min_slope: float = 1/15,
                                  nodata: float = -9999) -> np.ndarray:
    """
    Compute terrain criteria using raster-based "cone of influence" method.
    
    Instead of computing point-to-point distances (O(N*M)), this method:
    1. Creates a source raster from points
    2. Computes distance transform from sources (O(N))
    3. Computes elevation difference from sources
    4. Derives slope as Δz / distance
    
    This is fundamentally different from the original which computes:
    - For each pixel: max(slope to all source points)
    
    This method computes:
    - For each pixel: slope to NEAREST source point
    
    For many landslide scenarios, the nearest source dominates anyway.
    
    Args:
        dem: Digital Elevation Model as numpy array
        source_points: Nx2 or Nx3 array of source point coordinates (x, y, [z])
        dem_transform: Affine transform of the DEM
        h_min: Minimum height difference for slope calculation
        min_slope: Minimum slope threshold (default 1:15)
        nodata: NoData value
        
    Returns:
        slope_raster: Raster of slope values (Δz/distance to nearest source)
    """
    resolution = abs(dem_transform[0])
    height, width = dem.shape
    
    # Create source elevation raster (z values at source locations)
    source_raster = np.full((height, width), np.nan, dtype=np.float64)
    
    for i, point in enumerate(source_points):
        # Convert coordinates to pixel indices
        col, row = ~dem_transform * (point[0], point[1])
        row, col = int(round(row)), int(round(col))
        
        if 0 <= row < height and 0 <= col < width:
            z_source = point[2] if len(point) > 2 else dem[row, col]
            source_raster[row, col] = z_source
    
    # Create binary mask of source locations
    source_mask = ~np.isnan(source_raster)
    
    if not np.any(source_mask):
        return np.full_like(dem, nodata)
    
    # Compute Euclidean distance to nearest source (in pixels)
    distance_pixels = distance_transform_edt(~source_mask)
    distance_meters = distance_pixels * resolution
    
    # Get the index of nearest source for each pixel
    # This uses scipy's distance_transform_edt with return_indices
    _, nearest_indices = ndimage.distance_transform_edt(
        ~source_mask, return_indices=True
    )
    
    # Get elevation of nearest source for each pixel
    nearest_z = source_raster[nearest_indices[0], nearest_indices[1]]
    
    # For pixels that are sources themselves, use their own z value
    # (nearest_z will be nan for non-source pixels without valid nearest)
    
    # Compute height difference (DEM - source elevation)
    # Positive means DEM is higher than source (upslope from source)
    height_diff = dem - nearest_z
    
    # Compute slope (rise/run)
    with np.errstate(divide='ignore', invalid='ignore'):
        slope = height_diff / distance_meters
    
    # Apply h_min filter
    slope[height_diff < h_min] = nodata
    
    # Handle edge cases
    slope[distance_meters == 0] = nodata  # Source pixels
    slope[np.isnan(slope)] = nodata
    slope[np.isinf(slope)] = nodata
    
    return slope


def terrain_criteria_multi_cone(dem: np.ndarray,
                                 source_points: np.ndarray,
                                 dem_transform: rasterio.transform.Affine,
                                 h_min: float = 5.0,
                                 n_nearest: int = 5,
                                 nodata: float = -9999) -> np.ndarray:
    """
    Enhanced raster cone method that considers multiple nearest sources.
    
    Uses Voronoi-like decomposition to find N nearest sources for each pixel,
    then computes max slope across those sources.
    
    This is a hybrid between full brute-force and single-nearest approaches.
    
    Args:
        dem: Digital Elevation Model
        source_points: Source point coordinates
        dem_transform: Affine transform
        h_min: Minimum height difference
        n_nearest: Number of nearest sources to consider (default 5)
        nodata: NoData value
        
    Returns:
        slope_raster: Maximum slope to any of the N nearest sources
    """
    from scipy.spatial import cKDTree
    
    resolution = abs(dem_transform[0])
    height, width = dem.shape
    
    # Generate coordinates for all DEM pixels
    rows, cols = np.mgrid[0:height, 0:width]
    xs, ys = rasterio.transform.xy(dem_transform, rows.flatten(), cols.flatten())
    pixel_coords = np.c_[np.array(xs), np.array(ys)]
    pixel_z = dem.flatten()
    
    # Build KD-tree on source points
    source_xy = source_points[:, :2]
    source_z = source_points[:, 2] if source_points.shape[1] > 2 else None
    
    if source_z is None:
        # Sample z from DEM
        source_z = np.array([
            dem[int(round((~dem_transform * (p[0], p[1]))[1])),
                int(round((~dem_transform * (p[0], p[1]))[0]))]
            for p in source_points
        ])
    
    tree = cKDTree(source_xy)
    
    # Find n_nearest sources for each pixel
    k = min(n_nearest, len(source_points))
    distances, indices = tree.query(pixel_coords, k=k, workers=-1)
    
    if k == 1:
        distances = distances.reshape(-1, 1)
        indices = indices.reshape(-1, 1)
    
    # Compute slopes to all k nearest sources
    source_z_neighbors = source_z[indices]  # Shape: (n_pixels, k)
    height_diff = pixel_z[:, np.newaxis] - source_z_neighbors
    
    with np.errstate(divide='ignore', invalid='ignore'):
        slopes = height_diff / distances
    
    # Apply h_min filter
    slopes[height_diff < h_min] = nodata
    slopes[distances == 0] = nodata
    
    # Take maximum slope across k neighbors
    max_slope = np.nanmax(slopes, axis=1)
    max_slope[np.isnan(max_slope)] = nodata
    
    return max_slope.reshape(height, width)


# ============================================================================
# METHOD 2: FAST MARCHING (Alternative to Retrogression)
# ============================================================================

def retrogression_fast_marching(dem: np.ndarray,
                                 initial_release: np.ndarray,
                                 dem_transform: rasterio.transform.Affine,
                                 min_slope: float = 1/15,
                                 min_height: float = 5.0,
                                 min_length: float = 75.0,
                                 max_length: float = 2000.0,
                                 initial_release_depth: float = 0.0,
                                 mask: np.ndarray = None) -> Tuple[np.ndarray, list]:
    """
    Landslide retrogression using Fast Marching Method (FMM).
    
    NOTE: This method uses a different propagation model than the original.
    The original checks if SLOPE TO ANY SOURCE > min_slope.
    FMM computes travel time based on local speed function.
    
    For better accuracy matching the original, use retrogression_morphological_accurate.
    """
    try:
        import skfmm
    except ImportError:
        print("Warning: scikit-fmm not installed. Using morphological fallback.")
        return retrogression_morphological_accurate(
            dem, initial_release, dem_transform, min_slope, min_height,
            min_length, max_length, initial_release_depth, mask
        )
    
    resolution = abs(dem_transform[0])
    height, width = dem.shape
    
    i_rel, j_rel = np.where(initial_release == 1)
    if len(i_rel) == 0:
        return initial_release.copy(), [initial_release]
    
    # Build source coordinates
    x_rel, y_rel = rasterio.transform.xy(dem_transform, i_rel, j_rel)
    z_rel = np.array([dem[ii, jj] - initial_release_depth for ii, jj in zip(i_rel, j_rel)])
    source_coords = np.c_[x_rel, y_rel, z_rel]
    
    # Create speed function that matches original semantics better:
    # For each pixel, check if ANY source satisfies slope criterion
    from scipy.spatial import cKDTree
    
    # Generate all pixel coordinates
    rows, cols = np.mgrid[0:height, 0:width]
    xs, ys = rasterio.transform.xy(dem_transform, rows.flatten(), cols.flatten())
    pixel_xy = np.c_[np.array(xs), np.array(ys)]
    pixel_z = dem.flatten()
    
    # Build KD-tree on sources
    tree = cKDTree(source_coords[:, :2])
    
    # For speed, use k-nearest sources (not all)
    k = min(20, len(source_coords))
    distances, indices = tree.query(pixel_xy, k=k, workers=-1)
    
    if k == 1:
        distances = distances.reshape(-1, 1)
        indices = indices.reshape(-1, 1)
    
    # Compute slope to k nearest sources
    source_z_neighbors = source_coords[indices, 2]
    height_diff = pixel_z[:, np.newaxis] - source_z_neighbors
    
    with np.errstate(divide='ignore', invalid='ignore'):
        slopes = height_diff / np.maximum(distances, 1e-10)
    
    # Check if ANY of the k sources satisfies criterion
    valid = (height_diff >= min_height) & (slopes > min_slope)
    any_valid = np.any(valid, axis=1)
    
    # Also mark pixels within min_length as always valid
    min_dist = np.min(distances, axis=1)
    within_min_length = min_dist <= min_length
    
    # Speed function
    speed = np.ones(height * width, dtype=np.float64) * 0.001
    speed[any_valid | within_min_length] = 1.0
    speed = speed.reshape(height, width)
    
    if mask is not None:
        speed[mask == 0] = 0.001
    
    # Create level set (phi)
    phi = np.ones((height, width), dtype=np.float64)
    phi[initial_release == 1] = -1
    
    # Run FMM
    try:
        travel_time = skfmm.travel_time(phi, speed, dx=resolution)
    except Exception as e:
        print(f"FMM failed: {e}")
        return retrogression_morphological_accurate(
            dem, initial_release, dem_transform, min_slope, min_height,
            min_length, max_length, initial_release_depth, mask
        )
    
    # Threshold
    release = (travel_time <= max_length).astype(np.int32)
    release[initial_release == 1] = 1
    
    if mask is not None:
        release[mask == 0] = 0
    
    animation = [initial_release.copy(), release.copy()]
    return release, animation


def retrogression_morphological_accurate(dem: np.ndarray,
                                          initial_release: np.ndarray,
                                          dem_transform: rasterio.transform.Affine,
                                          min_slope: float = 1/15,
                                          min_height: float = 5.0,
                                          min_length: float = 75.0,
                                          max_length: float = 2000.0,
                                          initial_release_depth: float = 0.0,
                                          mask: np.ndarray = None,
                                          k_sources: int = None) -> Tuple[np.ndarray, list]:
    """
    Accurate retrogression using morphological operations + vectorized slope checking.
    
    This method preserves the original BFS algorithm's semantics exactly:
    - Propagate wave-like from newly added pixels only
    - Check if slope to ANY source > min_slope
    
    But uses vectorized operations for efficiency:
    - KD-tree for spatial indexing
    - Batch slope computation
    
    Args:
        k_sources: Number of nearest sources to check (None = all sources).
                   Using k < total sources is faster but may miss some valid expansions.
    """
    from scipy.spatial import cKDTree
    from scipy.ndimage import binary_dilation, generate_binary_structure
    
    resolution = abs(dem_transform[0])
    height, width = dem.shape
    
    i_rel, j_rel = np.where(initial_release == 1)
    if len(i_rel) == 0:
        return initial_release.copy(), [initial_release]
    
    # Build source coordinates
    x_rel, y_rel = rasterio.transform.xy(dem_transform, i_rel, j_rel)
    z_rel = np.array([dem[ii, jj] - initial_release_depth for ii, jj in zip(i_rel, j_rel)])
    source_coords = np.c_[x_rel, y_rel, z_rel]
    
    # Build KD-tree
    tree = cKDTree(source_coords[:, :2])
    
    # Determine k (number of sources to check)
    n_sources = len(source_coords)
    if k_sources is None:
        k = n_sources  # Check ALL sources (most accurate, but slower)
    else:
        k = min(k_sources, n_sources)
    
    # IMPORTANT: Use 4-connectivity (default) to match original BFS
    # The original uses binary_dilation without structure argument, which defaults to 4-connectivity
    # DO NOT use generate_binary_structure(2, 2) which gives 8-connectivity
    struct = None  # Use default (4-connectivity)
    
    # Phase 1: Unconditional expansion (same as original)
    min_iter = int(min_length // resolution)
    release = initial_release.copy().astype(bool)
    
    for _ in range(min_iter):
        # Get the rim (boundary pixels)
        dilated = binary_dilation(release, structure=struct)
        rim = dilated & ~release
        if mask is not None:
            rim = rim & (mask > 0)
        if not np.any(rim):
            break
        release = release | rim
    
    # Phase 2: Conditional expansion (BFS-style wave propagation)
    max_iter = int((max_length - min_length) // resolution)
    
    # Checked mask: pixels we've evaluated
    checked = release.copy()
    
    # Initial candidates: neighbors of current release that haven't been checked
    current_release = release.copy()
    dilated = binary_dilation(current_release, structure=struct)
    candidates_mask = dilated & ~current_release & ~checked
    if mask is not None:
        candidates_mask = candidates_mask & (mask > 0)
    
    n_iter = 0
    
    while n_iter < max_iter:
        if not np.any(candidates_mask):
            break
        
        # Get candidate coordinates
        i_cand, j_cand = np.where(candidates_mask)
        x_cand, y_cand = rasterio.transform.xy(dem_transform, i_cand, j_cand)
        z_cand = dem[i_cand, j_cand]
        
        xy_cand = np.c_[x_cand, y_cand]
        
        # Query k nearest sources for all candidates at once
        distances, indices = tree.query(xy_cand, k=k, workers=-1)
        
        if k == 1:
            distances = distances.reshape(-1, 1)
            indices = indices.reshape(-1, 1)
        
        # Get source Z values
        source_z_neighbors = source_coords[indices, 2]  # Shape: (n_cand, k)
        
        # Compute height differences
        height_diff = z_cand[:, np.newaxis] - source_z_neighbors
        
        # Compute slopes
        with np.errstate(divide='ignore', invalid='ignore'):
            slopes = height_diff / np.maximum(distances, 1e-10)
        
        # Check criteria: height >= min_height AND slope > min_slope
        valid = (height_diff >= min_height) & (slopes > min_slope)
        
        # A candidate passes if ANY of its k sources satisfies the criterion
        any_valid = np.any(valid, axis=1)
        
        # If no candidates pass, stop propagation
        if not np.any(any_valid):
            checked[i_cand, j_cand] = True
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
        
        # Mark ALL current candidates as checked
        checked[i_cand, j_cand] = True
        
        # CRITICAL: Generate NEXT candidates from ONLY the newly added pixels
        # This matches the BFS behavior exactly
        new_candidates = binary_dilation(new_release_pixels, structure=struct)
        new_candidates = new_candidates & ~checked
        if mask is not None:
            new_candidates = new_candidates & (mask > 0)
        
        candidates_mask = new_candidates
        n_iter += 1
    
    animation = [initial_release.copy(), release.astype(np.int32)]
    return release.astype(np.int32), animation


# ============================================================================
# METHOD 3: COST DISTANCE (Fallback / Alternative)
# ============================================================================

def _retrogression_cost_distance(dem: np.ndarray,
                                  initial_release: np.ndarray,
                                  dem_transform: rasterio.transform.Affine,
                                  min_slope: float = 1/15,
                                  min_height: float = 5.0,
                                  min_length: float = 75.0,
                                  max_length: float = 2000.0,
                                  initial_release_depth: float = 0.0,
                                  mask: np.ndarray = None) -> Tuple[np.ndarray, list]:
    """
    Retrogression using iterative morphological expansion with slope checking.
    
    This is a simplified but much faster approach that:
    1. Expands unconditionally up to min_length
    2. Then expands conditionally, checking if ANY source satisfies slope criterion
    
    Key insight: Instead of checking ALL sources for each pixel (expensive),
    we use distance-based filtering to check only nearby sources.
    """
    from scipy.spatial import cKDTree
    
    resolution = abs(dem_transform[0])
    height, width = dem.shape
    
    # Get source info
    i_rel, j_rel = np.where(initial_release == 1)
    if len(i_rel) == 0:
        return initial_release.copy(), [initial_release]
    
    # Build source coordinates with Z values
    x_rel, y_rel = rasterio.transform.xy(dem_transform, i_rel, j_rel)
    z_rel = np.array([dem[ii, jj] - initial_release_depth for ii, jj in zip(i_rel, j_rel)])
    source_coords = np.c_[x_rel, y_rel, z_rel]
    
    # Build KD-tree on source XY
    tree = cKDTree(source_coords[:, :2])
    
    # Phase 1: Unconditional expansion within min_length
    from scipy.ndimage import binary_dilation, generate_binary_structure
    
    struct = generate_binary_structure(2, 2)  # 8-connectivity
    min_iter = int(min_length // resolution)
    
    release = initial_release.copy().astype(bool)
    for _ in range(min_iter):
        release = binary_dilation(release, structure=struct)
        if mask is not None:
            release = release & (mask > 0)
    
    # Phase 2: Conditional expansion
    # We check slope criterion efficiently using vectorized operations
    
    max_iter = int((max_length - min_length) // resolution)
    
    for iteration in range(max_iter):
        # Get boundary pixels (candidates for expansion)
        dilated = binary_dilation(release, structure=struct)
        boundary = dilated & ~release
        
        if mask is not None:
            boundary = boundary & (mask > 0)
        
        if not np.any(boundary):
            break
        
        # Get coordinates of boundary pixels
        i_bound, j_bound = np.where(boundary)
        x_bound, y_bound = rasterio.transform.xy(dem_transform, i_bound, j_bound)
        z_bound = dem[i_bound, j_bound]
        
        # For each boundary pixel, check if ANY source satisfies slope criterion
        # Use KD-tree to find sources within max_length
        xy_bound = np.c_[x_bound, y_bound]
        
        # Query sources within reasonable distance
        search_radius = max_length
        indices_list = tree.query_ball_point(xy_bound, r=search_radius)
        
        # Check slope for each boundary pixel
        valid_expansion = np.zeros(len(i_bound), dtype=bool)
        
        for idx, (x, y, z, source_indices) in enumerate(zip(x_bound, y_bound, z_bound, indices_list)):
            if len(source_indices) == 0:
                continue
            
            # Get source coordinates
            src_xy = source_coords[source_indices, :2]
            src_z = source_coords[source_indices, 2]
            
            # Compute distances
            distances = np.sqrt(np.sum((src_xy - np.array([x, y]))**2, axis=1))
            
            # Compute height differences
            height_diff = z - src_z
            
            # Check slope criterion
            valid = (height_diff >= min_height) & (distances > 0)
            if np.any(valid):
                slopes = height_diff[valid] / distances[valid]
                if np.any(slopes > min_slope):
                    valid_expansion[idx] = True
        
        # Expand only valid pixels
        if not np.any(valid_expansion):
            break
        
        release[i_bound[valid_expansion], j_bound[valid_expansion]] = True
    
    animation = [initial_release.copy(), release.astype(np.int32)]
    
    return release.astype(np.int32), animation


# ============================================================================
# METHOD 4: GRAPH-BASED PROPAGATION
# ============================================================================

def retrogression_graph_based(dem: np.ndarray,
                               initial_release: np.ndarray,
                               dem_transform: rasterio.transform.Affine,
                               min_slope: float = 1/15,
                               min_height: float = 5.0,
                               min_length: float = 75.0,
                               max_length: float = 2000.0,
                               initial_release_depth: float = 0.0,
                               mask: np.ndarray = None) -> Tuple[np.ndarray, list]:
    """
    Landslide retrogression using graph-based shortest path.
    
    Models the DEM as a graph where:
    - Nodes = pixels
    - Edges = connections to 8-neighbors
    - Edge weights = based on slope criterion satisfaction
    
    Uses Dijkstra's algorithm to find all reachable pixels from sources
    within the max_length constraint.
    
    This is conceptually similar to BFS but uses proper shortest-path
    which handles the slope criterion more elegantly.
    """
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    
    resolution = abs(dem_transform[0])
    height, width = dem.shape
    n_pixels = height * width
    
    # Get source coordinates and create source elevation map
    i_rel, j_rel = np.where(initial_release == 1)
    source_z = {(i, j): dem[i, j] - initial_release_depth for i, j in zip(i_rel, j_rel)}
    
    if len(source_z) == 0:
        return initial_release.copy(), [initial_release]
    
    # Helper to convert 2D index to 1D
    def idx_2d_to_1d(i, j):
        return i * width + j
    
    def idx_1d_to_2d(idx):
        return idx // width, idx % width
    
    # Build sparse adjacency matrix
    # Edge weight = distance if slope criterion met, else infinity
    rows, cols, weights = [], [], []
    
    # 8-connectivity offsets
    neighbors = [(-1, -1), (-1, 0), (-1, 1),
                 (0, -1),          (0, 1),
                 (1, -1),  (1, 0), (1, 1)]
    
    diag_dist = resolution * np.sqrt(2)
    card_dist = resolution
    
    # Pre-compute distance from each pixel to nearest source
    dist_to_source = distance_transform_edt(initial_release == 0) * resolution
    
    # Get nearest source for each pixel
    _, nearest_idx = ndimage.distance_transform_edt(
        initial_release == 0, return_indices=True
    )
    
    for i in range(height):
        for j in range(width):
            if mask is not None and mask[i, j] == 0:
                continue
                
            current_idx = idx_2d_to_1d(i, j)
            current_z = dem[i, j]
            
            # Get nearest source elevation
            src_i, src_j = nearest_idx[0, i, j], nearest_idx[1, i, j]
            if (src_i, src_j) in source_z:
                nearest_source_z = source_z[(src_i, src_j)]
            else:
                nearest_source_z = current_z  # Fallback
            
            dist = dist_to_source[i, j]
            height_diff = current_z - nearest_source_z
            
            # Determine if this pixel satisfies propagation criteria
            if dist <= min_length:
                can_propagate = True
            else:
                slope = height_diff / max(dist, 1e-10)
                can_propagate = (slope > min_slope) and (height_diff >= min_height)
            
            if not can_propagate:
                continue
            
            # Add edges to neighbors
            for di, dj in neighbors:
                ni, nj = i + di, j + dj
                
                if 0 <= ni < height and 0 <= nj < width:
                    if mask is not None and mask[ni, nj] == 0:
                        continue
                    
                    neighbor_idx = idx_2d_to_1d(ni, nj)
                    edge_dist = diag_dist if (di != 0 and dj != 0) else card_dist
                    
                    rows.append(current_idx)
                    cols.append(neighbor_idx)
                    weights.append(edge_dist)
    
    # Create sparse matrix
    graph = csr_matrix((weights, (rows, cols)), shape=(n_pixels, n_pixels))
    
    # Find source pixel indices
    source_indices = [idx_2d_to_1d(i, j) for i, j in zip(i_rel, j_rel)]
    
    # Run Dijkstra from all sources
    dist_matrix = dijkstra(graph, indices=source_indices, limit=max_length)
    
    # Minimum distance from any source
    min_dist = np.min(dist_matrix, axis=0)
    
    # Create release mask
    release = (min_dist <= max_length).astype(np.int32).reshape(height, width)
    
    # Ensure initial release is included
    release[initial_release == 1] = 1
    
    if mask is not None:
        release[mask == 0] = 0
    
    animation = [initial_release.copy(), release.copy()]
    
    return release, animation


# ============================================================================
# WRAPPER FUNCTIONS FOR EASY COMPARISON
# ============================================================================

def run_terrain_criteria_alternative(dem_data: dict,
                                      source_points: np.ndarray,
                                      method: str = 'multi_cone',
                                      **kwargs) -> np.ndarray:
    """
    Run alternative terrain criteria methods.
    
    Args:
        dem_data: Dictionary with 'full_array' and 'profile' keys
        source_points: Source point coordinates
        method: 'single_cone' or 'multi_cone'
        **kwargs: Additional arguments for the method
        
    Returns:
        Slope raster
    """
    dem = dem_data["full_array"]
    transform = dem_data["profile"]["transform"]
    
    if method == 'single_cone':
        return terrain_criteria_raster_cone(dem, source_points, transform, **kwargs)
    elif method == 'multi_cone':
        return terrain_criteria_multi_cone(dem, source_points, transform, **kwargs)
    else:
        raise ValueError(f"Unknown method: {method}")


def run_retrogression_alternative(dem_data: dict,
                                   initial_release: np.ndarray,
                                   method: str = 'fast_marching',
                                   mask: np.ndarray = None,
                                   **kwargs) -> Tuple[np.ndarray, list]:
    """
    Run alternative retrogression methods.
    
    Args:
        dem_data: Dictionary with 'full_array' and 'profile' keys
        initial_release: Binary mask of initial release
        method: 'fast_marching', 'cost_distance', or 'graph'
        mask: Optional mask
        **kwargs: Additional arguments
        
    Returns:
        (release_mask, animation)
    """
    dem = dem_data["full_array"]
    transform = dem_data["profile"]["transform"]
    
    if method == 'fast_marching':
        return retrogression_fast_marching(dem, initial_release, transform, mask=mask, **kwargs)
    elif method == 'cost_distance':
        return _retrogression_cost_distance(dem, initial_release, transform, mask=mask, **kwargs)
    elif method == 'graph':
        return retrogression_graph_based(dem, initial_release, transform, mask=mask, **kwargs)
    else:
        raise ValueError(f"Unknown method: {method}")
