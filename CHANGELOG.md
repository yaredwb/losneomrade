# Changelog - 2025-11-21

## Overview
- Documenting today’s investigation into retrogression performance/correctness, the parallelization attempts, and supporting tooling/data added for debugging and visualization.

## Core code changes
- `src/losneomrade/retrogression.py`: kept the baseline algorithm intact but made slope checking cheaper by introducing `slope_chunk_size` (default 1000) that routes to the chunked slope computation. The option is threaded through all entry points (`run_retrogression`, `run_retrogression_parallel*`, and `run_retrogression_with_initial_landslide`). Behaviour is unchanged; only memory/CPU use improves.
- `src/losneomrade/utils.py`: added `compute_slope_chunked` to process slope distances in batches to avoid the huge distance matrix blow-up.

## Parallelization issue (root cause, attempts, status)
- Problem: The first parallel implementation split the rasterized release into connected components, ran each in isolation, then merged outputs. Because components cannot “see” each other during propagation, nearby zones never merge, yielding many small polygons (e.g., 11 polys / 236 ha) versus the baseline (5 polys / 1675 ha).
- Attempt 1 (component-wise parallel): Fast but incorrect for interacting zones.
- Attempt 2 (distance-based grouping): Grouped components whose buffered bounding boxes overlap (max_length-derived). In the test case it grouped everything, effectively reverting to the baseline and losing the speedup.
- Current status: To preserve correctness, all interacting components must be solved together. The feasible optimization is to accelerate the inner slope computation (now chunked) and, if needed later, parallelize *inside* that computation rather than splitting the spatial problem. Component-wise parallel remains available but will intentionally diverge whenever cross-zone interaction matters.

## Tooling and scripts added
- `scripts/benchmark_performance.py`: compares baseline vs chunked slope and sequential vs parallel retrogression runtime/memory.
- Analysis runners: `scripts/retrogression_analysis.py` (baseline), `scripts/retrogression_analysis_optimized.py` (component parallel), `scripts/retrogression_analysis_grouped.py` (grouped parallel).
- Terrain criteria runners: `scripts/terrain_criteria_analysis.py` (baseline) and `scripts/terrain_criteria_analysis_optimized.py` (chunked slope via monkeypatch).
- Debugging: `scripts/debug_retrogression.py` for inspecting connected components after rasterizing the dissolved release.
- Data prep and visuals: `scripts/create_subset.py` (sample streams), `scripts/visualize_results.py`, `scripts/visualize_comparison.py`.

## Data and outputs created
- Stream subsets: `data/streams_subset.geojson` (3 features), `data/streams_subset_15.geojson`, `data/streams_subset_50.geojson`.
- GeoJSON results: `output/retrogression_analysis.geojson`, `retrogression_analysis_grouped.geojson`, `retrogression_analysis_optimized.geojson`, `terrain_criteria_analysis.geojson`, `terrain_criteria_analysis_optimized.geojson`.
- Visuals: `output/analysis_visualization.png`, `output/comparison_baseline_vs_optimized.png`.

## Notes / follow-ups
- Several new scripts print status lines with stray `�` characters; clean these for tidy CLI output.
- If more speed is needed without losing correctness, next step is to parallelize the chunked slope calculation itself (shared memory-safe) or explore tiled processing with overlap/halo to allow cross-tile interaction.
