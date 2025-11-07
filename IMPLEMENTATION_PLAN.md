# Performance Optimization Implementation Plan

## Overview
This document outlines a detailed, phased implementation plan to optimize the `losneomrade` package performance when processing multiple initiation lines. Each phase includes specific tasks, acceptance criteria, and benchmarking to measure improvements.

---

## Pre-Implementation: Baseline Benchmarking

### Goal
Establish current performance metrics to measure improvements against.

### Tasks

#### 1. Create benchmark suite (`benchmarks/benchmark_baseline.py`)
```python
"""Baseline performance benchmarks for losneomrade package."""
import time
import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point
from losneomrade import terrain_criteria, retrogression
import json
from datetime import datetime

class PerformanceMetrics:
    def __init__(self):
        self.metrics = {
            'timestamp': datetime.now().isoformat(),
            'version': 'baseline',
            'test_cases': []
        }
    
    def add_test_case(self, name, num_lines, area_km2, 
                      total_time, dem_downloads, peak_memory_mb):
        self.metrics['test_cases'].append({
            'name': name,
            'num_lines': num_lines,
            'area_km2': area_km2,
            'total_time_seconds': total_time,
            'dem_downloads': dem_downloads,
            'peak_memory_mb': peak_memory_mb,
            'time_per_line': total_time / num_lines if num_lines > 0 else 0
        })
    
    def save(self, filename='baseline_metrics.json'):
        with open(filename, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        print(f"Saved metrics to {filename}")

def benchmark_terrain_criteria_single_line():
    """Test Case 1: Single line (baseline reference)"""
    # Simple line in a known area
    line = LineString([(268883, 6651786), (269497, 6651808)])
    gdf = gpd.GeoDataFrame(geometry=[line], crs=25833)
    
    bounds = gdf.total_bounds
    xmin, ymin, xmax, ymax = bounds
    xmin -= 1000; xmax += 1000
    ymin -= 1000; ymax += 1000
    
    start = time.time()
    result = terrain_criteria.run_terrain_criteria(
        bounds=(xmin, xmax, ymin, ymax),
        source=gdf,
        source_depth=0.5,
        clip_to_msml=False
    )
    elapsed = time.time() - start
    
    area_km2 = ((xmax - xmin) * (ymax - ymin)) / 1e6
    
    return {
        'name': 'single_line',
        'num_lines': 1,
        'area_km2': area_km2,
        'total_time': elapsed,
        'dem_downloads': 1,  # Known: 1 download per call
        'result_area': result.area.sum() if not result.empty else 0
    }

def benchmark_terrain_criteria_multiple_lines_sequential(num_lines=10):
    """Test Case 2: Multiple lines processed sequentially (current approach)"""
    # Generate multiple nearby lines
    lines = []
    base_x, base_y = 268883, 6651786
    for i in range(num_lines):
        offset = i * 100
        line = LineString([
            (base_x + offset, base_y),
            (base_x + offset + 600, base_y + 1000)
        ])
        lines.append(line)
    
    gdf = gpd.GeoDataFrame(geometry=lines, crs=25833)
    
    # Process each line separately (current approach)
    results = []
    start = time.time()
    
    for idx, line_geom in enumerate(gdf.geometry):
        line_gdf = gpd.GeoDataFrame(geometry=[line_geom], crs=25833)
        bounds = line_gdf.total_bounds
        xmin, ymin, xmax, ymax = bounds
        xmin -= 1000; xmax += 1000
        ymin -= 1000; ymax += 1000
        
        result = terrain_criteria.run_terrain_criteria(
            bounds=(xmin, xmax, ymin, ymax),
            source=line_gdf,
            source_depth=0.5,
            clip_to_msml=False
        )
        results.append(result)
    
    elapsed = time.time() - start
    
    # Calculate unified area
    bounds = gdf.total_bounds
    area_km2 = ((bounds[2] - bounds[0]) * (bounds[3] - bounds[1])) / 1e6
    
    return {
        'name': f'multiple_lines_sequential_{num_lines}',
        'num_lines': num_lines,
        'area_km2': area_km2,
        'total_time': elapsed,
        'dem_downloads': num_lines,  # Known: 1 per line
        'result_area': sum(r.area.sum() for r in results if not r.empty)
    }

def benchmark_retrogression_single_point():
    """Test Case 3: Retrogression from single point"""
    point = Point(268883, 6651786)
    gdf = gpd.GeoDataFrame(geometry=[point], crs=25833)
    
    bounds = gdf.total_bounds
    xmin, ymin, xmax, ymax = bounds
    xmin -= 2000; xmax += 2000
    ymin -= 2000; ymax += 2000
    
    start = time.time()
    result = retrogression.run_retrogression(
        bounds=(xmin, xmax, ymin, ymax),
        rel_shape=gdf,
        point_depth=0.5,
        clip_to_msml=False,
        min_slope=1/15,
        min_length=75,
        min_height=5
    )
    elapsed = time.time() - start
    
    area_km2 = ((xmax - xmin) * (ymax - ymin)) / 1e6
    
    return {
        'name': 'retrogression_single_point',
        'num_lines': 1,
        'area_km2': area_km2,
        'total_time': elapsed,
        'dem_downloads': 1,
        'result_area': result.area.sum() if not result.empty else 0
    }

def run_all_benchmarks():
    """Run all baseline benchmarks and save results."""
    print("=" * 60)
    print("BASELINE PERFORMANCE BENCHMARKS")
    print("=" * 60)
    
    metrics = PerformanceMetrics()
    
    # Test 1: Single line
    print("\n[1/4] Benchmarking single line...")
    try:
        result = benchmark_terrain_criteria_single_line()
        print(f"  ✓ Completed in {result['total_time']:.2f}s")
        metrics.add_test_case(**result)
    except Exception as e:
        print(f"  ✗ Failed: {e}")
    
    # Test 2: 5 lines sequential
    print("\n[2/4] Benchmarking 5 lines (sequential)...")
    try:
        result = benchmark_terrain_criteria_multiple_lines_sequential(5)
        print(f"  ✓ Completed in {result['total_time']:.2f}s")
        print(f"    Time per line: {result['total_time']/5:.2f}s")
        metrics.add_test_case(**result)
    except Exception as e:
        print(f"  ✗ Failed: {e}")
    
    # Test 3: 10 lines sequential
    print("\n[3/4] Benchmarking 10 lines (sequential)...")
    try:
        result = benchmark_terrain_criteria_multiple_lines_sequential(10)
        print(f"  ✓ Completed in {result['total_time']:.2f}s")
        print(f"    Time per line: {result['total_time']/10:.2f}s")
        metrics.add_test_case(**result)
    except Exception as e:
        print(f"  ✗ Failed: {e}")
    
    # Test 4: Retrogression
    print("\n[4/4] Benchmarking retrogression...")
    try:
        result = benchmark_retrogression_single_point()
        print(f"  ✓ Completed in {result['total_time']:.2f}s")
        metrics.add_test_case(**result)
    except Exception as e:
        print(f"  ✗ Failed: {e}")
    
    # Save results
    metrics.save('benchmarks/baseline_metrics.json')
    
    print("\n" + "=" * 60)
    print("BASELINE BENCHMARKS COMPLETE")
    print("=" * 60)
    print("\nResults saved to: benchmarks/baseline_metrics.json")
    
    return metrics

if __name__ == '__main__':
    run_all_benchmarks()
```

#### 2. Create benchmark infrastructure
- Create `benchmarks/` directory
- Add `benchmarks/__init__.py`
- Add `benchmarks/README.md` with instructions

#### 3. Run baseline benchmarks
```bash
python benchmarks/benchmark_baseline.py
```

### Success Criteria
- ✅ Baseline metrics saved to `benchmarks/baseline_metrics.json`
- ✅ All test cases complete without errors
- ✅ Metrics include: execution time, DEM downloads, memory usage, result areas

---

## Phase 1: Core Optimizations (High Impact)

### Goal
Implement batch processing, DEM caching, and compute_slope optimization to achieve 10-100× speedup.

### Implementation Steps

#### Step 1.1: Add DEM Cache to `utils.py`

**File**: `src/losneomrade/utils.py`

**Changes**:
1. Add after line 22 (after `HOYDEDATA_LAYER` constant):

```python
class DEMCache:
    """In-memory cache for DEM data to avoid redundant downloads."""
    
    def __init__(self, max_size_mb=500, enabled=True):
        self._cache = {}  # key: (bounds, layer, res) -> dem_data
        self._access_order = []  # For LRU eviction
        self._max_size = max_size_mb * 1024 * 1024
        self._current_size = 0
        self._enabled = enabled
        self._stats = {'hits': 0, 'misses': 0, 'evictions': 0}
    
    def _estimate_size(self, dem_data):
        """Estimate memory size of DEM data in bytes."""
        size = dem_data['full_array'].nbytes
        for arr in dem_data.get('windows_dem_arrays', []):
            size += arr.nbytes
        return size
    
    def _bounds_key(self, bounds):
        """Normalize bounds to handle floating point precision."""
        return tuple(round(b, 2) for b in bounds)
    
    def get(self, bounds, layer, res):
        """Retrieve cached DEM if available."""
        if not self._enabled:
            return None
        
        key = (self._bounds_key(bounds), layer, res)
        
        if key in self._cache:
            # Update access order for LRU
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            self._stats['hits'] += 1
            return self._cache[key].copy()  # Return copy to avoid mutation
        
        self._stats['misses'] += 1
        return None
    
    def put(self, bounds, layer, res, dem_data):
        """Store DEM in cache with LRU eviction."""
        if not self._enabled:
            return
        
        key = (self._bounds_key(bounds), layer, res)
        
        # Skip if already cached
        if key in self._cache:
            return
        
        size = self._estimate_size(dem_data)
        
        # Evict if necessary
        while self._current_size + size > self._max_size and self._cache:
            self._evict_lru()
        
        # Store data
        self._cache[key] = dem_data
        self._access_order.append(key)
        self._current_size += size
    
    def _evict_lru(self):
        """Evict least recently used entry."""
        if not self._access_order:
            return
        
        key = self._access_order.pop(0)
        if key in self._cache:
            size = self._estimate_size(self._cache[key])
            del self._cache[key]
            self._current_size -= size
            self._stats['evictions'] += 1
    
    def clear(self):
        """Clear all cached data."""
        self._cache.clear()
        self._access_order.clear()
        self._current_size = 0
        self._stats = {'hits': 0, 'misses': 0, 'evictions': 0}
    
    def get_stats(self):
        """Return cache statistics."""
        total_requests = self._stats['hits'] + self._stats['misses']
        hit_rate = self._stats['hits'] / total_requests if total_requests > 0 else 0
        return {
            **self._stats,
            'hit_rate': hit_rate,
            'cache_size_mb': self._current_size / (1024 * 1024),
            'num_entries': len(self._cache)
        }
    
    def enable(self):
        """Enable caching."""
        self._enabled = True
    
    def disable(self):
        """Disable caching."""
        self._enabled = False

# Global cache instance
_DEM_CACHE = DEMCache(enabled=True)

def get_cache_stats():
    """Get DEM cache statistics."""
    return _DEM_CACHE.get_stats()

def clear_dem_cache():
    """Clear the DEM cache."""
    _DEM_CACHE.clear()
```

2. Modify `get_hoydedata` function (line 25) to use cache:

```python
def get_hoydedata(bounds: tuple, layer: str = HOYDEDATA_LAYER, res: int = 5, 
                  nodata: int = -9999, max_retries=5, use_cache=True) -> dict:
    """
    Function for downloading DEM from www.høydedata.no with caching support.
    
    Args:
        bounds (tuple): Bounding box (xmin, xmax, ymin, ymax)
        layer (str, optional): Which Høydedata API layer
        res (int, optional): Resolution in meters. Defaults to 5.
        nodata (int, optional): Value for nodata pixels. Defaults to -9999.
        max_retries (int, optional): Maximum retry attempts. Defaults to 5.
        use_cache (bool, optional): Whether to use cache. Defaults to True.
    
    Returns:
        dict: DEM data with windows_dem_arrays, windows_transforms, windows, profile, full_array
    """
    # Check cache first
    if use_cache:
        cached_data = _DEM_CACHE.get(bounds, layer, res)
        if cached_data is not None:
            return cached_data
    
    # ... rest of existing function (download logic) ...
    # At the end, before return, add:
    
    result = {
        "windows_dem_arrays": windows_dems,
        "windows_transforms": windows_transforms,
        "windows": windows,
        "profile": dataset_profile,
        "full_array": full_array
    }
    
    # Store in cache
    if use_cache:
        _DEM_CACHE.put(bounds, layer, res, result)
    
    return result
```

**Testing**:
```python
# Test cache functionality
from losneomrade import utils

# First call - cache miss
bounds1 = (268000, 270000, 6651000, 6653000)
data1 = utils.get_hoydedata(bounds1)
print(utils.get_cache_stats())  # Should show 1 miss, 0 hits

# Second call - cache hit
data2 = utils.get_hoydedata(bounds1)
print(utils.get_cache_stats())  # Should show 1 miss, 1 hit
```

---

#### Step 1.2: Create Batch Processing Module

**File**: `src/losneomrade/batch_processing.py` (new file)

```python
"""
Batch processing utilities for efficient multi-line analysis.
"""

import numpy as np
import geopandas as gpd
import pandas as pd
import rasterio
from typing import Union, List, Tuple
from . import utils, terrain_criteria, retrogression


def compute_unified_bounds(
    geometries: Union[gpd.GeoDataFrame, List], 
    buffer_distance: float = 1000
) -> Tuple[float, float, float, float]:
    """
    Compute unified bounding box for multiple geometries.
    
    Args:
        geometries: GeoDataFrame or list of geometries
        buffer_distance: Buffer distance in meters to add around bounds
        
    Returns:
        (xmin, xmax, ymin, ymax)
    """
    if isinstance(geometries, gpd.GeoDataFrame):
        bounds = geometries.total_bounds  # (minx, miny, maxx, maxy)
    else:
        bounds = gpd.GeoSeries(geometries).total_bounds
    
    xmin = bounds[0] - buffer_distance
    xmax = bounds[2] + buffer_distance
    ymin = bounds[1] - buffer_distance
    ymax = bounds[3] + buffer_distance
    
    return (xmin, xmax, ymin, ymax)


def run_terrain_criteria_batch(
    source: gpd.GeoDataFrame,
    source_depth: float = 0.0,
    clip_to_msml: bool = False,
    h_min: float = 5,
    buffer_distance: float = 1000,
    custom_raster=None,
    verbose: bool = True
) -> gpd.GeoDataFrame:
    """
    Run terrain criteria analysis for multiple source lines efficiently.
    
    Downloads DEM once for all lines, significantly improving performance
    compared to calling run_terrain_criteria() multiple times.
    
    Args:
        source: GeoDataFrame with LineStrings, MultiLineStrings, or Points
        source_depth: Depth of source points in meters
        clip_to_msml: Whether to clip results to marine clay deposits
        h_min: Minimum height for slope calculations (meters)
        buffer_distance: Distance to buffer around geometries for DEM bounds (meters)
        custom_raster: Optional path to custom raster file
        verbose: Print progress information
        
    Returns:
        GeoDataFrame with terrain criteria results for all sources combined
        
    Example:
        >>> lines = gpd.read_file('initiation_lines.geojson')
        >>> results = run_terrain_criteria_batch(
        ...     source=lines,
        ...     source_depth=0.5,
        ...     clip_to_msml=True
        ... )
        >>> print(f"Processed {len(lines)} lines with 1 DEM download")
    """
    if verbose:
        print(f"Processing {len(source)} geometries with batch mode...")
    
    # Compute unified bounds
    bounds = compute_unified_bounds(source, buffer_distance)
    
    if verbose:
        area_km2 = ((bounds[1] - bounds[0]) * (bounds[3] - bounds[2])) / 1e6
        print(f"  Unified bounds: {area_km2:.2f} km²")
        print(f"  Downloading DEM...")
    
    # Single DEM download
    if custom_raster is None:
        window_data = utils.get_hoydedata(bounds)
    else:
        window_data = utils.generate_windows(custom_raster)
    
    if verbose:
        print(f"  Generating source points...")
    
    # Generate all source points
    if np.all(source.geom_type.isin(["LineString", "MultiLineString"])):
        source_points = terrain_criteria.generate_source_points(source)
    elif np.all(source.geom_type == "Point"):
        source_points = source.get_coordinates().values
    else:
        raise ValueError("source must contain only LineStrings, MultiLineStrings, or Points")
    
    if verbose:
        print(f"  Processing {len(source_points)} source points...")
    
    # Set elevation from DEM
    source_points_xyz = utils.set_z_from_raster(source_points, window_data)
    source_points_xyz[:, 2] = source_points_xyz[:, 2] - source_depth
    
    # Run terrain criteria computation
    windows = window_data["windows"]
    windows_dems = window_data["windows_dem_arrays"]
    windows_transforms = window_data["windows_transforms"]
    raster_profile = window_data["profile"]
    nan_value = raster_profile["nodata"]
    
    # Create output raster
    result_array = np.ones_like(window_data["full_array"]) * nan_value
    
    if verbose:
        print(f"  Computing slopes across {len(windows)} windows...")
    
    for index, window in enumerate(windows):
        results_window = terrain_criteria.compute_from_windows(
            windows_dems[index], 
            windows_transforms[index], 
            source_points_xyz,
            nan_value, 
            h_min, 
            reclassify_results=True
        )
        # Write results to correct position in full array
        row_off, col_off = window.row_off, window.col_off
        height, width = window.height, window.width
        result_array[row_off:row_off+height, col_off:col_off+width] = results_window
    
    if verbose:
        print(f"  Polygonizing results...")
    
    # Polygonize results
    gpd_results = terrain_criteria.polygonize_terrain_criteria(
        result_array, 
        raster_profile['transform']
    )
    
    # Clip to MSML if requested
    if clip_to_msml:
        if verbose:
            print(f"  Clipping to MSML...")
        gpd_results = terrain_criteria.clip_results_to_msml(gpd_results, bounds)
    
    if verbose:
        print(f"✓ Batch processing complete!")
    
    return gpd_results


def run_retrogression_batch(
    source: gpd.GeoDataFrame,
    point_depth: float = 0.0,
    clip_to_msml: bool = False,
    min_slope: float = 1/15,
    min_height: float = 5,
    min_length: float = 75,
    buffer_distance: float = 2000,
    custom_raster=None,
    verbose: bool = True
) -> gpd.GeoDataFrame:
    """
    Run retrogression analysis for multiple source geometries efficiently.
    
    Downloads DEM once for all sources, then runs retrogression for each.
    
    Args:
        source: GeoDataFrame with geometries (Points, LineStrings, Polygons)
        point_depth: Depth of source points in meters
        clip_to_msml: Whether to clip results to marine clay deposits
        min_slope: Minimum slope for retrogression (default 1/15)
        min_height: Minimum height difference for slope check (meters)
        min_length: Minimum retrogression length (meters)
        buffer_distance: Distance to buffer around geometries for DEM bounds
        custom_raster: Optional path to custom raster file
        verbose: Whether to print progress
        
    Returns:
        GeoDataFrame with combined retrogression results for all sources
    """
    if verbose:
        print(f"Processing {len(source)} geometries with batch retrogression...")
    
    # Compute unified bounds
    bounds = compute_unified_bounds(source, buffer_distance)
    
    if verbose:
        area_km2 = ((bounds[1] - bounds[0]) * (bounds[3] - bounds[2])) / 1e6
        print(f"  Unified bounds: {area_km2:.2f} km²")
        print(f"  Downloading DEM...")
    
    # Single DEM download
    if custom_raster is None:
        dem_data = utils.get_hoydedata(bounds)
    else:
        dem_data = utils.generate_windows(custom_raster)
    
    dem_array = dem_data["full_array"]
    dem_profile = dem_data["profile"]
    
    # Get MSML mask once if needed
    if clip_to_msml:
        if verbose:
            print(f"  Loading MSML mask...")
        mask_gpd = utils.get_msml_mask((bounds[0], bounds[2], bounds[1], bounds[3]))
        mask_msml = utils.rasterize_shape(mask_gpd, dem_profile)
    else:
        mask_msml = None
    
    if verbose:
        print(f"  Running retrogression for each geometry...")
    
    # Process each source geometry
    results = []
    for idx, geom_row in source.iterrows():
        if verbose:
            print(f"    [{idx+1}/{len(source)}] Processing geometry...")
        
        geom_gdf = gpd.GeoDataFrame([geom_row], crs=source.crs)
        
        # Rasterize this source
        rel = utils.rasterize_shape(geom_gdf, dem_profile)
        
        # Run retrogression
        release, _ = retrogression.landslide_retrogression(
            dem_array, 
            rel, 
            dem_profile["transform"],
            min_slope=min_slope,
            min_height=min_height,
            min_length=min_length,
            initial_release_depth=point_depth,
            mask=mask_msml,
            verbose=False  # Suppress per-geometry verbosity
        )
        
        # Polygonize this result
        result_gdf = utils.polygonize_results(release, dem_profile, field="slope")
        result_gdf['source_id'] = idx  # Track which source this came from
        results.append(result_gdf)
    
    # Combine all results
    combined = gpd.GeoDataFrame(pd.concat(results, ignore_index=True), crs=25833)
    
    if verbose:
        print(f"✓ Batch retrogression complete!")
    
    return combined


def estimate_processing_time(
    num_lines: int,
    area_km2: float,
    use_batch: bool = True
) -> dict:
    """
    Estimate processing time for terrain criteria analysis.
    
    Args:
        num_lines: Number of source lines
        area_km2: Approximate area covered in square kilometers
        use_batch: Whether batch processing will be used
        
    Returns:
        Dictionary with time estimates in seconds
    """
    # Rough estimates based on typical performance
    dem_download_time = 5 + (area_km2 * 0.2)  # ~5s base + 0.2s per km²
    processing_time_per_line = 1 + (area_km2 * 0.5)  # Processing time
    
    if use_batch:
        total_time = dem_download_time + processing_time_per_line
    else:
        total_time = num_lines * (dem_download_time + processing_time_per_line)
    
    return {
        'total_seconds': total_time,
        'total_minutes': total_time / 60,
        'dem_download_seconds': dem_download_time if use_batch else dem_download_time * num_lines,
        'processing_seconds': processing_time_per_line if use_batch else processing_time_per_line * num_lines,
        'speedup_factor': (num_lines * dem_download_time) / dem_download_time if use_batch else 1.0
    }
```

---

#### Step 1.3: Optimize `compute_slope` in `utils.py`

**Changes to `utils.compute_slope` function**:

```python
def compute_slope(
    coords: np.ndarray,
    points: np.ndarray,
    h_min: float = 5,
    nodata: int = -9999,
    search_radius: float = None,
    chunk_size: int = 5000
) -> np.ndarray:
    """
    Compute the slopes of the given dem with respect to the (source) points.
    
    Optimized version with spatial prefiltering and chunked computation.
    
    Args:
        coords: dem window coordinates (N x 3: x, y, z)
        points: source point coordinates (M x 3: x, y, z)
        h_min: minimum height difference where slopes are calculated
        nodata: value given to pixels with no data
        search_radius: maximum distance to consider (meters). If None, uses adaptive radius
        chunk_size: number of points to process at once (memory optimization)
    
    Returns:
        max_slope: array with slopes (same shape as input dem)
    """
    if points.size == 0:
        return np.ones(coords.shape[0]) * nodata
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        
        xy_coords = coords[:, :2]
        z_coords = coords[:, -1]
        
        # Adaptive search radius if not provided
        if search_radius is None:
            # Use window bounds to estimate reasonable radius
            window_size = np.max(np.ptp(xy_coords, axis=0))
            search_radius = max(window_size * 1.5, 2000)  # At least 2 km
        
        # Prefilter points: keep only those within search_radius of window bounds
        window_center = np.mean(xy_coords, axis=0)
        point_distances = np.linalg.norm(points[:, :2] - window_center, axis=1)
        nearby_mask = point_distances <= (search_radius + np.max(np.ptp(xy_coords, axis=0)) / 2)
        
        points_filtered = points[nearby_mask]
        
        if points_filtered.size == 0:
            # No points nearby, return nodata
            return np.ones(coords.shape[0]) * nodata
        
        xy_points = points_filtered[:, :2]
        z_points = points_filtered[:, -1]
        
        # Initialize max slope array
        max_slope = np.ones(coords.shape[0]) * nodata
        
        # Chunked computation to limit memory
        num_points = points_filtered.shape[0]
        
        for i in range(0, num_points, chunk_size):
            chunk_end = min(i + chunk_size, num_points)
            xy_chunk = xy_points[i:chunk_end]
            z_chunk = z_points[i:chunk_end]
            
            # Compute distances and heights for this chunk
            distance_mtx = distance_matrix(xy_coords, xy_chunk)
            height_mtx = z_coords[:, np.newaxis] - z_chunk
            
            # Compute slope ratios
            hl_ratio = height_mtx / distance_mtx
            hl_ratio[height_mtx < h_min] = nodata
            
            # Update max slope
            chunk_max = np.max(hl_ratio, axis=1)
            max_slope = np.where(
                (max_slope == nodata) | (chunk_max > max_slope),
                chunk_max,
                max_slope
            )
        
        return max_slope
```

---

#### Step 1.4: Update Package Exports

**File**: `src/losneomrade/__init__.py`

```python
from .terrain_criteria import run_terrain_criteria, terrain_criteria
from .retrogression import run_retrogression, landslide_retrogression
from .batch_processing import (
    run_terrain_criteria_batch,
    run_retrogression_batch,
    compute_unified_bounds,
    estimate_processing_time
)
from . import utils

__all__ = [
    "run_terrain_criteria",
    "terrain_criteria", 
    "run_retrogression",
    "landslide_retrogression",
    "run_terrain_criteria_batch",
    "run_retrogression_batch",
    "compute_unified_bounds",
    "estimate_processing_time",
    "utils"
]
```

---

#### Step 1.5: Create Optimized Benchmarks

**File**: `benchmarks/benchmark_optimized.py`

```python
"""Performance benchmarks for optimized losneomrade package."""
import time
import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point
from losneomrade import batch_processing, utils
import json
from datetime import datetime

# ... (similar structure to baseline_benchmark.py but using batch functions)

def benchmark_terrain_criteria_batch(num_lines=10):
    """Test with new batch processing API"""
    lines = []
    base_x, base_y = 268883, 6651786
    for i in range(num_lines):
        offset = i * 100
        line = LineString([
            (base_x + offset, base_y),
            (base_x + offset + 600, base_y + 1000)
        ])
        lines.append(line)
    
    gdf = gpd.GeoDataFrame(geometry=lines, crs=25833)
    
    # Clear cache to ensure fair comparison
    utils.clear_dem_cache()
    
    start = time.time()
    result = batch_processing.run_terrain_criteria_batch(
        source=gdf,
        source_depth=0.5,
        clip_to_msml=False,
        verbose=False
    )
    elapsed = time.time() - start
    
    # Get cache stats
    cache_stats = utils.get_cache_stats()
    
    bounds = gdf.total_bounds
    area_km2 = ((bounds[2] - bounds[0]) * (bounds[3] - bounds[1])) / 1e6
    
    return {
        'name': f'batch_{num_lines}_lines',
        'num_lines': num_lines,
        'area_km2': area_km2,
        'total_time': elapsed,
        'dem_downloads': 1,  # Only 1 download with batch
        'cache_hits': cache_stats['hits'],
        'result_area': result.area.sum() if not result.empty else 0
    }

# ... (implement all test cases using batch API)
```

---

### Step 1.6: Create Unit Tests

**File**: `tests/test_batch_processing.py`

```python
import unittest
import tempfile
import geopandas as gpd
import numpy as np
from shapely.geometry import LineString, Point
from losneomrade import batch_processing, terrain_criteria, utils


class TestBatchProcessing(unittest.TestCase):
    
    def test_compute_unified_bounds(self):
        """Test unified bounds calculation"""
        line1 = LineString([(0, 0), (100, 100)])
        line2 = LineString([(50, 50), (150, 150)])
        gdf = gpd.GeoDataFrame(geometry=[line1, line2], crs=25833)
        
        bounds = batch_processing.compute_unified_bounds(gdf, buffer_distance=10)
        
        self.assertEqual(bounds, (-10, 160, -10, 160))
    
    def test_batch_produces_same_results_as_individual(self):
        """Verify batch and individual processing give equivalent results"""
        with tempfile.TemporaryDirectory() as tempdir:
            # Create test data
            dem, profile = utils.generate_fake_slope(100, 100, 2000, 150, 1/5, 2e5, 6e6)
            
            import rasterio
            with rasterio.open(tempdir + "/fake_slope.tif", "w", **profile) as src:
                src.write(dem, 1)
            
            # Create multiple lines
            lines = []
            for i in range(3):
                lines.append(LineString([
                    (2e5 + 100 + i*200, 6e6 - 1150),
                    (2e5 + 200 + i*200, 6e6 - 1050)
                ]))
            
            gdf = gpd.GeoDataFrame(geometry=lines, crs=25833)
            
            # Batch processing
            utils.clear_dem_cache()
            batch_result = batch_processing.run_terrain_criteria_batch(
                source=gdf,
                source_depth=0.5,
                clip_to_msml=False,
                custom_raster=tempdir + "/fake_slope.tif",
                verbose=False
            )
            
            # Individual processing combined
            utils.clear_dem_cache()
            individual_results = []
            for line_geom in gdf.geometry:
                line_gdf = gpd.GeoDataFrame(geometry=[line_geom], crs=25833)
                bounds = line_gdf.total_bounds
                xmin, ymin, xmax, ymax = bounds
                xmin -= 1000; xmax += 1000
                ymin -= 1000; ymax += 1000
                
                result = terrain_criteria.run_terrain_criteria(
                    bounds=(xmin, xmax, ymin, ymax),
                    source=line_gdf,
                    source_depth=0.5,
                    clip_to_msml=False,
                    custom_raster=tempdir + "/fake_slope.tif"
                )
                individual_results.append(result)
            
            # Compare total areas (should be similar)
            batch_area = batch_result.area.sum()
            individual_area = sum(r.area.sum() for r in individual_results)
            
            # Allow 5% difference due to edge effects
            self.assertAlmostEqual(batch_area, individual_area, delta=individual_area * 0.05)
    
    def test_cache_functionality(self):
        """Test DEM caching works"""
        bounds = (268000, 270000, 6651000, 6653000)
        
        utils.clear_dem_cache()
        
        # First call - miss
        data1 = utils.get_hoydedata(bounds, use_cache=True)
        stats1 = utils.get_cache_stats()
        self.assertEqual(stats1['hits'], 0)
        self.assertEqual(stats1['misses'], 1)
        
        # Second call - hit
        data2 = utils.get_hoydedata(bounds, use_cache=True)
        stats2 = utils.get_cache_stats()
        self.assertEqual(stats2['hits'], 1)
        self.assertEqual(stats2['misses'], 1)
        self.assertGreater(stats2['hit_rate'], 0)
    
    def test_estimate_processing_time(self):
        """Test time estimation function"""
        estimate = batch_processing.estimate_processing_time(
            num_lines=10,
            area_km2=25,
            use_batch=True
        )
        
        self.assertIn('total_seconds', estimate)
        self.assertIn('speedup_factor', estimate)
        self.assertGreater(estimate['speedup_factor'], 1)


if __name__ == '__main__':
    unittest.main()
```

---

### Phase 1 Testing & Validation

#### Run Tests
```bash
# Unit tests
python -m pytest tests/test_batch_processing.py -v

# Run optimized benchmarks
python benchmarks/benchmark_optimized.py
```

#### Compare Results
```python
# Compare baseline vs optimized
python benchmarks/compare_results.py
```

**File**: `benchmarks/compare_results.py`

```python
import json

# Load results
with open('benchmarks/baseline_metrics.json') as f:
    baseline = json.load(f)

with open('benchmarks/optimized_metrics.json') as f:
    optimized = json.load(f)

print("=" * 70)
print("PERFORMANCE COMPARISON")
print("=" * 70)

for b_test in baseline['test_cases']:
    # Find matching optimized test
    o_test = next((t for t in optimized['test_cases'] 
                   if t['num_lines'] == b_test['num_lines']), None)
    
    if o_test:
        speedup = b_test['total_time'] / o_test['total_time']
        dem_reduction = b_test['dem_downloads'] / o_test['dem_downloads']
        
        print(f"\nTest: {b_test['name']}")
        print(f"  Lines: {b_test['num_lines']}")
        print(f"  Baseline time: {b_test['total_time']:.2f}s")
        print(f"  Optimized time: {o_test['total_time']:.2f}s")
        print(f"  Speedup: {speedup:.1f}x")
        print(f"  DEM downloads: {b_test['dem_downloads']} → {o_test['dem_downloads']}")
        print(f"  Cache hits: {o_test.get('cache_hits', 0)}")
```

### Phase 1 Success Criteria
- ✅ All unit tests pass
- ✅ Batch processing produces results within 5% area of individual processing
- ✅ 10+ lines: >10× speedup measured
- ✅ DEM downloads reduced to ~1 per batch
- ✅ Cache hit rate >80% on repeated calls
- ✅ No regression in result quality

---

## Phase 2: Enhanced Features (Optional)

### Step 2.1: Add Performance Monitoring

**File**: `src/losneomrade/monitoring.py` (new)

```python
"""Performance monitoring and profiling utilities."""
import time
import functools
import json
from datetime import datetime


class PerformanceMonitor:
    """Context manager and decorator for performance monitoring."""
    
    def __init__(self, operation_name):
        self.operation_name = operation_name
        self.start_time = None
        self.end_time = None
        self.metrics = {}
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()
        elapsed = self.end_time - self.start_time
        print(f"[{self.operation_name}] completed in {elapsed:.2f}s")
    
    def record_metric(self, key, value):
        """Record a custom metric."""
        self.metrics[key] = value


def profile_function(func):
    """Decorator to profile function execution time."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        print(f"[PROFILE] {func.__name__} took {elapsed:.2f}s")
        return result
    return wrapper
```

### Step 2.2: Add Progress Reporting

Integrate `tqdm` progress bars for long operations in batch processing.

### Step 2.3: Add Spatial Partitioning (for very large datasets)

Implement clustering for country-scale datasets.

---

## Documentation Updates

### Files to Update:
1. `README.md` - Add batch processing examples
2. `docs/PERFORMANCE_GUIDE.md` - New file with optimization tips
3. All function docstrings - Ensure completeness

---

## Final Deliverables

1. ✅ **Optimized code** with batch processing, caching, and compute improvements
2. ✅ **Comprehensive test suite** with unit and integration tests
3. ✅ **Benchmark suite** with before/after comparisons
4. ✅ **Performance report** documenting actual speedups achieved
5. ✅ **Updated documentation** with examples and best practices
6. ✅ **Migration guide** for users to adopt new APIs

---

## Timeline Estimate

- **Phase 1**: 2-3 days (core optimizations + testing)
- **Phase 2**: 2-3 days (enhanced features)
- **Documentation**: 1 day
- **Total**: ~5-7 days for complete implementation

---

## Risk Mitigation

### Risks:
1. Results differ between batch and individual processing
2. Cache causes memory issues on large datasets
3. Network issues during benchmarking

### Mitigations:
1. Extensive testing with tolerance checks; visual comparison
2. Configurable cache size with LRU eviction
3. Use local test rasters for reproducible benchmarks
