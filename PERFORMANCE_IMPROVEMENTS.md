# Performance Improvement Work Plan

## Session Summary (November 20, 2025)

### Critical Performance Issues Identified

#### 1. Terrain Criteria - Memory Explosion
**Problem:**
- RAM requirement explodes as number of source points grows
- Creates massive distance matrices: `(num_DEM_pixels × num_source_points)`
- Example: 409,600 pixels × 11,764 points = 36 GB memory requirement
- Current implementation: `utils.compute_slope()` creates full distance matrix in memory

**Root Cause:**
```python
# In utils.py line ~142
distance_mtx = distance_matrix(xy_1, xy_2)  # (N_pixels × M_points) matrix
height_mtx = z1[:, np.newaxis] - z2
hl_ratio = height_mtx / distance_mtx
```

**Impact:**
- Fails on consumer-grade hardware (8-16 GB RAM)
- Forces users to drastically reduce point density (losing spatial detail)
- Current workaround: Reduce from 1 point/5m to 1 point/50m (10x reduction)

---

#### 2. Retrogression Analysis - Excessive Runtime
**Problem:**
- Takes extremely long to complete (249 minutes = 4+ hours on test PC)
- Step-wise propagation with iterative buffer operations
- Progress bar requires `ipywidgets` (dependency issue)

**Root Cause:**
- Iterative buffering and slope calculations at each step
- No spatial indexing or optimization
- Full DEM processing at each iteration

**Impact:**
- Impractical for production use
- Makes iterative parameter testing impossible
- User experience severely degraded

---

## Proposed Solutions

### Priority 1: Fix Terrain Criteria Memory Issue

#### Option A: Chunked Processing (Recommended)
**Approach:** Process source points in batches to avoid full matrix
```python
def compute_slope_chunked(coords, points, h_min=5, nodata=-9999, chunk_size=1000):
    """
    Process source points in chunks to reduce memory footprint.
    Instead of (N × M) matrix, process (N × chunk_size) repeatedly.
    """
    max_slope = np.full(len(coords), nodata, dtype=np.float64)
    
    for i in range(0, len(points), chunk_size):
        chunk_points = points[i:i+chunk_size]
        distance_mtx = distance_matrix(coords[:, :2], chunk_points[:, :2])
        height_mtx = coords[:, 2][:, np.newaxis] - chunk_points[:, 2]
        hl_ratio = height_mtx / distance_mtx
        hl_ratio[height_mtx < h_min] = nodata
        chunk_max = np.max(hl_ratio, axis=1)
        max_slope = np.maximum(max_slope, chunk_max)
    
    return max_slope
```

**Benefits:**
- Memory scales with chunk size, not total points
- No algorithm changes required
- Backward compatible

**Estimated Improvement:**
- Memory: 36 GB → ~500 MB (with chunk_size=1000)
- Speed: Slight overhead (~10-20% slower) but acceptable

---

#### Option B: Spatial Indexing with KDTree
**Approach:** Only compute slopes for nearby points using spatial search
```python
from scipy.spatial import cKDTree

def compute_slope_spatial(coords, points, h_min=5, nodata=-9999, search_radius=500):
    """
    Use spatial indexing to only consider nearby source points.
    Most pixels are only affected by nearby sources anyway.
    """
    tree = cKDTree(points[:, :2])
    max_slope = np.full(len(coords), nodata, dtype=np.float64)
    
    for i, coord in enumerate(coords):
        # Find points within search radius
        indices = tree.query_ball_point(coord[:2], r=search_radius)
        if not indices:
            continue
        
        nearby_points = points[indices]
        distances = np.linalg.norm(coord[:2] - nearby_points[:, :2], axis=1)
        heights = coord[2] - nearby_points[:, 2]
        slopes = heights / distances
        
        valid = heights >= h_min
        if np.any(valid):
            max_slope[i] = np.max(slopes[valid])
    
    return max_slope
```

**Benefits:**
- Memory efficient (no large matrices)
- Physically realistic (distant sources don't matter)
- Potentially faster for sparse point distributions

**Trade-offs:**
- Need to define search radius
- More complex implementation

---

#### Option C: GPU Acceleration (Future)
**Approach:** Use CuPy/CUDA for parallel distance calculations
- Only viable if GPU available
- Significant development effort
- Consider for future optimization

---

### Priority 2: Optimize Retrogression Performance

#### Option A: Reduce Iteration Granularity
**Current:** 1-pixel buffer per iteration → many iterations
**Proposed:** Multi-pixel buffer steps where appropriate
```python
# Adaptive step size based on distance from source
def adaptive_buffer_size(n_iter, min_iter):
    if n_iter < min_iter:
        return 3  # Larger steps early on
    else:
        return 1  # Fine-grained near edges
```

**Estimated Improvement:** 2-3x speedup

---

#### Option B: Parallel Processing of Independent Regions
**Approach:** Identify disconnected release zones and process in parallel
```python
from multiprocessing import Pool
from scipy.ndimage import label

def parallel_retrogression(dem, initial_releases, ...):
    """
    Label connected components and process independently.
    """
    labeled, n_features = label(initial_releases)
    
    with Pool() as pool:
        results = pool.starmap(
            landslide_retrogression,
            [(dem, labeled == i, ...) for i in range(1, n_features+1)]
        )
    
    return merge_results(results)
```

**Benefits:**
- Near-linear speedup with CPU cores
- No algorithm changes to core logic

**Estimated Improvement:** 4-8x speedup (depending on CPU cores)

---

#### Option C: Precompute Slope Fields
**Approach:** Calculate slope rasters once, query during propagation
```python
def precompute_slope_field(dem, dem_profile):
    """
    Pre-calculate slopes from all pixels to reduce per-iteration cost.
    """
    # Use rasterio's slope calculation or custom implementation
    slope_field = calculate_dem_slopes(dem)
    return slope_field
```

**Benefits:**
- Reduces redundant calculations
- Faster iteration checks

**Trade-offs:**
- Higher upfront cost
- More memory usage

---

#### Option D: Remove/Simplify Progress Bar
**Quick Fix:** Already implemented (`verbose=False`)
**Better Solution:** Use simple print statements instead of tqdm
```python
if verbose and n_iter % 10 == 0:
    print(f"Iteration {n_iter}/{max_iter} ({n_iter/max_iter*100:.1f}%)")
```

---

## Implementation Plan

### Phase 1: Terrain Criteria Optimization (Week 1)
- [ ] Implement chunked processing (Option A)
- [ ] Add chunk_size parameter to configuration
- [ ] Test with original point density (1 point/5m)
- [ ] Benchmark memory usage and runtime
- [ ] Update notebook with new approach

**Success Criteria:**
- Run with 11,000+ points on 16GB RAM
- Memory usage < 4GB
- Runtime comparable to current implementation

---

### Phase 2: Retrogression Optimization (Week 2)
- [ ] Implement parallel processing (Option B)
- [ ] Test adaptive buffer sizing (Option A)
- [ ] Profile to identify bottlenecks
- [ ] Benchmark against current implementation
- [ ] Document performance improvements

**Success Criteria:**
- Reduce runtime from 249 minutes to < 60 minutes
- Maintain result accuracy
- Make method practical for production use

---

### Phase 3: Testing & Validation (Week 3)
- [ ] Compare results with original implementation
- [ ] Validate on multiple test cases
- [ ] Performance regression tests
- [ ] Update documentation
- [ ] User acceptance testing

---

### Phase 4: Optional Advanced Optimizations (Future)
- [ ] Investigate GPU acceleration (Option C for both)
- [ ] Explore Numba JIT compilation
- [ ] Consider C++/Cython extensions for critical paths
- [ ] Profile-guided optimization

---

## Testing Requirements

### Test Cases
1. **Small dataset** (~1,000 points, 1km²)
   - Baseline for algorithm correctness
   - Quick iteration testing

2. **Medium dataset** (~5,000 points, 10km²)
   - Representative of typical use cases
   - Balance between speed and realism

3. **Large dataset** (~20,000 points, 50km²)
   - Stress test for scalability
   - Production scenario

### Metrics to Track
- **Memory Usage:** Peak RAM consumption
- **Runtime:** Wall-clock time for analysis
- **Result Quality:** Area differences vs. baseline (should be < 1%)
- **Point Density:** Maximum achievable without memory errors

---

## Technical Debt to Address
- [ ] Add memory profiling decorators
- [ ] Implement comprehensive logging
- [ ] Add runtime benchmarking utilities
- [ ] Create performance regression test suite
- [ ] Document hardware requirements clearly

---

## Current Workarounds (Temporary)
1. **Terrain Criteria:**
   - Reduce `POINTS_PER_METER` from 1/10 to 1/50
   - Reduce `BUFFER_DISTANCE` from 300m to 200m
   - Manual downsampling in notebook (cell with `DOWNSAMPLE_FACTOR`)

2. **Retrogression:**
   - Set `verbose=False` to avoid ipywidgets issue
   - Run overnight or during off-hours
   - Consider reducing `max_length` parameter

---

## References & Resources
- scipy.spatial.distance_matrix: Current bottleneck
- scipy.spatial.cKDTree: For spatial indexing approach
- numpy.lib.stride_tricks: For potential memory optimization
- Python multiprocessing: For parallel retrogression
- Memory profilers: memory_profiler, tracemalloc

---

## Notes from Session
- **Test Environment:** Consumer PC, exact specs TBD
- **Test Dataset:** Byneset area, 1692 stream features, 5m DEM resolution
- **Current Performance:**
  - Terrain Criteria: Memory error with 11,809 points (36 GB required)
  - Retrogression: 249 minutes runtime (successful but impractical)

---

## Next Session Checklist
- [ ] Decide on optimization approach (chunked vs. spatial indexing)
- [ ] Set up performance benchmarking framework
- [ ] Implement Phase 1 (terrain criteria optimization)
- [ ] Test on original dataset with full point density
- [ ] Document improvements in notebook

---

**Document Version:** 1.0  
**Date:** November 20, 2025  
**Status:** Planning / Not Started  
**Priority:** Critical - Blocking production use
