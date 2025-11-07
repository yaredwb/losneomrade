# Losneomrade — Technical Analysis and Implementation Review (Aug 29, 2025)

This report provides a thorough analysis of the repository, explains the current implementation and procedures, highlights critical weaknesses, and proposes concrete improvements with a prioritized roadmap.

## Executive summary

- Purpose: Compute potential landslide release areas in quick clay (kvikkleire) terrain using two approaches:
  - Terrain-criteria (pixel-based slope threshold vs source points).
  - Iterative retrogression (step-wise propagation constrained by slope, min height, and length).
- Maturity: Functional core algorithms with example usage and unit tests. Heavy reliance on live external services and some performance, robustness, and packaging gaps.
- Top risks: Memory/performance (O(N·M) slope computation), flaky network dependence (timeouts/retries), API fragility, and limited observability (logging/metrics). 
- Quick wins: Add timeouts and robust retries to network calls, chunk slope calculations, export top-level API in `__init__.py`, and improve packaging/extras.

---

## Repository overview

- Python package layout (src layout):
  - `src/losneomrade/terrain_criteria.py`: Terrain criteria workflow and helpers.
  - `src/losneomrade/retrogression.py`: Iterative retrogression algorithm and visualization helpers.
  - `src/losneomrade/utils.py`: External data access (DEM and MSML), core geometric/raster utilities.
  - `src/losneomrade/__init__.py`: Currently empty.
- Tests: `tests/` with unit tests for synthetic DEMs and live-data paths (Høydedata and NVE’s MarinGrense).
- Docs: `readme.md` with overview, installation, and a usage snippet.
- Packaging: `pyproject.toml` with runtime dependencies (geospatial stack, plotting, tqdm, requests, etc.).

---

## Public API surface (observed)

- Terrain criteria (pixel-based):
  - `terrain_criteria.run_terrain_criteria(bounds, source[, ...]) -> GeoDataFrame`
  - `terrain_criteria.terrain_criteria(bounds, points, out_filename[, ...]) -> GeoDataFrame`
  - `terrain_criteria.generate_source_points(polylines[, distance_chainage]) -> np.ndarray`
  - `terrain_criteria.polygonize_terrain_criteria(result_raster, transform[, crs]) -> GeoDataFrame`
  - `terrain_criteria.clip_results_to_msml(results_gpd, bounds) -> GeoDataFrame`
  - `terrain_criteria.reclass(matrix) -> np.ndarray`

- Retrogression (iterative propagation):
  - `retrogression.run_retrogression(bounds, rel_shape[, ...]) -> GeoDataFrame | (GeoDataFrame, list)`
  - `retrogression.landslide_retrogression(dem, initial_release, transform[, ...]) -> (np.ndarray, list)`
  - Visualization helpers: `animate_landslide_retrogresion`, `hillshade_img`, `plot_hillshade_overlay`, `gen_animation`, `save_frames`

- Utilities (data access and geometry/raster helpers):
  - DEM: `utils.get_hoydedata(bounds[, layer, res, nodata, max_retries]) -> dict`
  - Raster windows: `utils.generate_windows(custom_raster) -> dict`
  - Geometry/raster conversions: `utils.dem_coordinates`, `utils.polygonize_results`, `utils.rasterize_shape`, `utils.set_z_from_raster`
  - Slope core: `utils.compute_slope(coords, points[, h_min, nodata]) -> np.ndarray`
  - MSML: `utils.get_msml_mask(bounds[, results_offset]) -> GeoDataFrame`, `utils.get_maringrense(bounds, layer[, results_offset]) -> GeoDataFrame`
  - Profiles: `utils.profile`, `utils.generate_plotly_profile`, `utils.generate_terraincriteria_line`
  - Misc: `utils.modify_release_mask`, `utils.convert_lines_to_gpd`, `utils.generate_fake_slope`

Note: `__init__.py` exports nothing; importing submodules via `from losneomrade import terrain_criteria` works in many environments due to import semantics, but explicit exports are recommended.

---

## How it works (procedures)

### Data sources and coordinate systems
- DEM from Høydedata ImageServer layers (default `NHM_DTM_25833` or `NHM_DTM_25832`). Requests return a GeoTIFF in desired bounding box and pixel size.
- Optionally, a custom local raster can be used in lieu of remote DEM.
- MSML/MarinGrense constraints fetched from NVE MapServer, clipped to bounds, reprojected to EPSG:25833.

### Terrain-criteria workflow (pixel-based)
1. Fetch DEM windows for `bounds` (or read custom raster) via `utils.get_hoydedata`/`utils.generate_windows`.
2. Prepare source points:
   - If inputs are lines, densify to points along the line (`generate_source_points`).
   - Look up elevations (Z) for points from DEM (`set_z_from_raster`) and subtract source depth.
3. For each DEM window:
   - Build per-pixel coordinates (`dem_coordinates`).
   - Compute slope score per pixel vs source points (`utils.compute_slope`), output is max(z1−z2)/distance over all source points subject to `h_min`.
   - Optionally reclassify slope classes with thresholds: `[0.05, 0.067, 0.2, 0.33, 1.7, 1000]` → bins for e.g., 1:20, 1:15, 1:5, 1:3, 60°.
   - Write window results into an output raster and assemble full-array results.
4. Polygonize the raster (`polygonize_terrain_criteria`), filter out flat (class < 1), set CRS to 25833.
5. Optional: clip polygons to MSML mask (`clip_results_to_msml`).
6. Return the result GeoDataFrame.

### Retrogression workflow (iterative)
1. Fetch DEM (remote or custom) and optionally derive MSML mask as raster.
2. Rasterize the initial release geometry (`utils.rasterize_shape`).
3. Iterate outward using binary dilation as a one-pixel ring buffer:
   - Convert both the current release and the ring-buffer pixels to coordinate arrays.
   - Compute slopes from buffered ring pixels to current release pixels (`utils.compute_slope`).
   - Before minimum length (pixels equivalent of `min_length`), accept ring without slope filtering. After that, keep only buffered pixels whose slope exceeds `min_slope` and where height difference ≥ `min_height`.
   - Apply optional mask to exclude areas (MSML outside).
   - Stop when the set stabilizes or max iterations (derived from `max_length`) is reached.
4. Convert final boolean raster to polygons (`utils.polygonize_results` with threshold 1), return GeoDataFrame; optionally, also return intermediate rasters (animation list) and provide helpers to animate/export frames.

---

## External dependencies and services

- Heavy geospatial and scientific stack: numpy, pandas, geopandas, shapely, rasterio, scipy, matplotlib, plotly, tqdm, Pillow.
- Remote services:
  - Høydedata ImageServer: REST exportImage endpoint to fetch raster DEM.
  - NVE MarinGrense MapServer: layer 7 (MSML) and 8 (Area under MG) GeoJSON query with pagination via `resultOffset`.

Implications:
- Network reliability and API schema changes can break runs/tests.
- Large responses can be slow; paging and client-side filtering are crucial.

---

## Implementation status (observations)

- Core algorithms implemented and tested (unit tests cover synthetic DEM and live scenarios for both workflows).
- Windowed processing is present to limit memory for terrain-criteria; retrogression iterates on ring buffers to limit per-step work.
- Packaging works for direct installs; README includes a usage example and installation instructions.
- Visualization utilities (matplotlib and plotly) are included for analysis and reporting.

Gaps:
- No command-line interface; API-only usage.
- `__init__.py` exposes no top-level symbols or version metadata.
- Network code has partial retry and no explicit timeouts in several places.
- Performance can degrade with many source points or large windows due to dense pairwise computations.

---

## Critical weaknesses and risks

1) Performance and memory scaling (core)
- `utils.compute_slope` uses `scipy.spatial.distance_matrix` to build a full pairwise matrix between all DEM pixels in a window and all source points. This is O(N·M) in time and O(N·M) in memory for the intermediate arrays (distance and height), which can be prohibitive for large windows or many source points.
- Retrogression recomputes pairwise slopes for each ring; although rings are thinner than full windows, release sets grow with iterations and computations can still balloon.

Mitigations:
- Chunked computation over rows/tiles: compute distances in blocks and reduce (max) per block to avoid full matrices in memory.
- Use `scipy.spatial.cKDTree` for spatial queries to reduce candidate source points per pixel (spatial pruning by radius implied by `h_min`).
- Apply radius pruning: for vertical threshold `h_min`, skip source points beyond distance D where (z1−z2)/D < class max; derive D bounds per pixel using a conservative terrain assumption.
- Consider Numba/Cython for the hot loop and on-the-fly reduction for max slope without storing full matrices.

2) Network reliability and API fragility
- `requests.get` without `timeout` in `get_maringrense` and `profile` risks hanging. `urlopen` without timeout in `get_hoydedata` has only a fixed-interval retry with no backoff.
- No jitter/exponential backoff; no structured error handling for non-2xx responses; JSON parsing errors can bubble up.
- `exceededTransferLimit` handled, but no explicit `resultRecordCount` control; large result sets may still cause flakiness.

Mitigations:
- Set explicit timeouts (connect/read), adopt exponential backoff with jitter, and use a `requests.Session` with a `HTTPAdapter` retry policy (idempotent GETs).
- Validate `response.status_code` and schema before `.json()`; handle non-JSON and partial results robustly.
- Add telemetry/logging for request URLs, timings, and retries, with PII-aware redaction when needed.

3) CRS and bounds consistency
- Bounds are handled as `(xmin, xmax, ymin, ymax)` in some places and `(xmin, ymin, xmax, ymax)` in others; ad-hoc reordering appears (e.g., retrogression uses `(bounds[0], bounds[2], bounds[1], bounds[3])` when fetching MSML), increasing risk of subtle bugs.

Mitigations:
- Normalize to a single `Bounds` dataclass with named fields and strict validation; provide helpers to convert to API-specific orders.
- Add assertions and unit tests for bounds ordering.

4) Edge cases in slope computation
- Division by zero at identical coordinates is masked by numpy error settings; however, `inf` can appear if not guarded; nodata handling sets invalid pairs to `-9999` and takes `max()` which works, but it’s brittle.

Mitigations:
- Explicitly mask zero-distance pairs before division, and ensure that the reduction over candidates handles all-invalid rows (return nodata consistently).
- Unit tests for zero-distance, all-invalid, and mixed-invalid scenarios.

5) Test fragility (live services)
- Several tests require live external services and assert absolute areas tied to April 2024 mapping state; data updates will (and already may) break these tests.

Mitigations:
- Use request recording/mocking (e.g., `pytest-vcr`) for remote services; keep a small golden dataset under `tests/testdata/`.
- Loosen assertions to ranges or feature-count-based checks and document update cadence.

6) Packaging and dependency hygiene
- Runtime includes heavy tools (`matplotlib`, `plotly`, `ipykernel`) that are not required headless; increases install time and footprint.
- Numpy pinned `<=2.0.1` may cause dependency resolution conflicts.
- `Shapely` capitalized (pip is case-insensitive but style is `shapely`).

Mitigations:
- Move optional tools to extras: `plot` and `notebook` groups; keep core minimal (numpy, rasterio, shapely, geopandas, scipy, requests, tqdm).
- Revisit numpy pin; align with the geospatial stack’s supported versions.

7) Logging/observability
- Use of `print` and muted warnings; no structured logging or togglable verbosity beyond some parameters.

Mitigations:
- Introduce `logging` with module-level loggers; add debug statements around major steps, sizes, timings.

8) Cross-platform paths and side-effects
- `save_frames` uses hardcoded Windows path separators (`'\\'`).
- Matplotlib backend switching in functions can create global side effects.

Mitigations:
- Use `os.path.join` for all paths; contain backend switching via context managers or user-configurable options.

9) API ergonomics and consistency
- `__init__.py` does not expose a stable, documented top-level API or a `__version__`.
- Mixed naming styles (e.g., `generate_terraincriteria_line`) and minimal type hints.

Mitigations:
- Export a curated API surface in `__init__.py`; add `__version__` from package metadata.
- Standardize naming (PEP 8), add or tighten type hints, and docstrings with parameter shapes/CRS expectations.

---

## Suggested improvements (prioritized roadmap)

Short-term (days)
- Add `timeout`, robust retries with backoff/jitter, and status checks to all HTTP calls.
- Replace hardcoded path separators with `os.path.join`.
- Normalize bounds via a small `Bounds` helper and centralize conversions.
- Switch to `tqdm.auto` and guard notebook/plot dependencies under extras.
- Expose top-level API and `__version__` in `__init__.py`.
- Add basic logging and a `verbose` flag that configures log level.

Mid-term (weeks)
- Rework `compute_slope` to avoid full pairwise matrices:
  - Chunked processing over DEM pixels.
  - KDTree-based pruning by spatial radius derived from `h_min`.
  - Optional Numba-accelerated reduction for max slope.
- Add a CLI (`python -m losneomrade ...`) and simple config file support.
- Strengthen tests by mocking remote services; add property-based tests for edge cases (zero distance, all nodata, mixed windows).
- Document CRS expectations, bounds ordering, and common pitfalls in README.

Long-term (months)
- Caching layer for DEM/MapServer queries (local file cache keyed by URL params + ETag/Expires where available).
- Parallelization: process windows in parallel (careful with GDAL/Rasterio threading and memory limits).
- Richer outputs: include raster outputs as optional artifacts, and add provenance metadata (layers, timestamps, parameters) into GeoJSON properties.
- Performance profiling and refactoring hotspots to Cython/Numba as needed.

---

## Implementation notes and edge cases

- Nodata handling: Reclassification treats nodata as class 0; downstream polygonization filters `< 1`, effectively masking nodata.
- DEM resolution assumptions: Some helpers use fixed `dx=dy=5` in hillshade; for arbitrary res, consider reading from profile.
- Retrogression min vs max length: `min_length` gates acceptance without slope filtering for the first iterations (pixels), while `max_length` caps iterations.
- MSML clipping: Combines two layers (`msml` and `area_under_mg`) and dissolves; empty results should be gracefully handled (currently returns empty GeoDataFrame).

---

## Suggested API refinements (examples)

- `__init__.py` export surface:
  - `from .terrain_criteria import run_terrain_criteria, terrain_criteria`
  - `from .retrogression import run_retrogression`
  - `from . import utils as utils`
  - `__all__ = ["run_terrain_criteria", "terrain_criteria", "run_retrogression", "utils"]`

- Introduce a `Bounds` helper:
  - Dataclass with `.to_xyxy()` and `.to_xmin_ymin_xmax_ymax()` to match API requirements.

- Network robustness:
  - `Session` with retry/backoff adapters and `timeout=(5, 30)` for connect/read; structured error messages.

- Compute slope (sketch):
  - Replace `distance_matrix` with cKDTree radius queries plus chunked reductions to avoid O(N·M) memory.

---

## Packaging and distribution

- Move optional plotting/notebook dependencies into extras:
  - `extras = {"plot": ["matplotlib", "plotly", "Pillow"], "notebook": ["ipykernel"]}`
- Add classifiers, license classifiers, and minimal Python version consistent with dependencies (likely `>=3.9`).
- Consider wheels publishing (GitHub Actions) and a small CHANGELOG.

---

## Quality gates snapshot

- Build/Lint: Not assessed here (recommend adding Black/Ruff + pre-commit).
- Unit tests: Not executed in this analysis; tests exist for both synthetic and live data but are network-dependent.
- Smoke test: Example code in README should run with live services enabled.

---

## Requirements coverage

- Analyze repository and explain what it does: done (overview, procedures, API surface).
- Describe current implementation status and procedure: done (status, workflows).
- Identify critical weaknesses: done (performance, network, CRS, testing, packaging, etc.).
- Provide suggestions for improvements: done (prioritized roadmap with concrete steps).
- Deliver as a markdown file: this document.

---

## Appendix: Typical usage patterns

- Terrain criteria (pixel-based):
  - Input: bounds in EPSG:25833, source points/lines (EPSG:25833), optional depth and clipping to MSML.
  - Output: GeoDataFrame of slope-classes polygons (class ≥ 1).

- Retrogression (iterative):
  - Input: bounds or custom raster, initial release geometry (GeoDataFrame), min slope, min/ max length, min height.
  - Output: GeoDataFrame of propagated release area; optional animation frames for visualization.

---

## Client-requested enhancements: scope, approach, and hour estimates

Below are the five requested improvements, with proposed technical approach, major tasks, assumptions, risks, and a single-developer time estimate. Estimates include design, implementation, light docs, and basic tests. Integration and iteration buffer is included per item.

1) Performance optimization for large/batch areas (highest priority)
- Goals: Faster runtime and reduced memory for large areas and batch processing.
- Approach (incremental):
  - Replace full pairwise `distance_matrix` in `utils.compute_slope` with chunked computation and/or KDTree-based pruning; avoid O(N·M) memory.
  - Add tiling/chunking for windows and optional multiprocessing across windows (configurable concurrency to respect GDAL limits).
  - Optional: Numba-accelerated hot loops for max-reduction without materializing large matrices.
  - Robust network layer: HTTP timeouts + retries with backoff; simple on-disk cache for DEM requests keyed by URL params.
  - Add lightweight benchmarking harness on synthetic and sample real areas; log timings.
- Tasks:
  - Refactor `compute_slope` (chunked + KDTree) and integrate into terrain-criteria and retrogression paths.
  - Add window-parallel execution option and concurrency controls.
  - Implement robust HTTP client and optional local cache.
  - Benchmarks and tuning; documentation of performance flags.
- Estimate: 35–55 hours.
- Risks: Numerical parity vs current method; care with memory usage; platform-specific issues with GDAL threading.

2) Process each side of the initiation area separately
- Goal: Compute retrogression independently per “side” of the initiation line/area to capture directionality.
- Approach:
  - For LineString releases, compute local normals and split the buffered ring into two half-planes (left/right relative to line direction) or split the domain once using a medial axis or signed distance field.
  - Run propagation independently per side and union results as needed, while keeping per-side outputs if desired.
- Tasks:
  - Define “sides” for typical geometries (LineString, MultiLineString, polygon boundary).
  - Modify retrogression loop to constrain candidate ring pixels to the chosen half-space.
  - Expose API to run per-side and to combine results; add tests on synthetic slope with asymmetric outcomes.
- Estimate: 18–28 hours.
- Risks: Complex geometry cases (multi-lines, sharp turns); defining side for polygonal releases; edge pixels near the line.

3) Mask out non-marine clay areas during computation (not only in final clipping)
- Goal: Treat MSML complement as excluded during slope computation and retrogression steps.
- Approach:
  - Generate a raster mask from MSML/AUMG union and its complement, aligned to DEM profile.
  - In terrain-criteria: ignore pixels outside mask early (set to nodata before slope computation); in retrogression: forbid propagation into masked-out pixels.
- Tasks:
  - Extend `utils.get_msml_mask` + `utils.rasterize_shape` usage to build a computation mask; add consistent bounds/CRS handling.
  - Wire mask into both algorithms; tests to show difference vs post-clip only.
- Estimate: 10–16 hours.
- Risks: Mask alignment with DEM; edge effects along boundaries.

4) Return additional parameters: maximum slope height and directions of local slope maxima
- Goal: Provide richer outputs for analysis and mapping.
- Approach:
  - During slope computation, track argmax source point per pixel to derive: (a) maximum vertical drop (height difference), (b) direction (azimuth) from pixel to argmax point.
  - Optionally compute local gradient direction from DEM (Sobel/horn) as a corroborating direction metric.
  - Include these as additional raster bands and/or attributes in polygon outputs (aggregates/means).
- Tasks:
  - Modify `compute_slope` to return both max value and index; compute height delta and azimuth per pixel.
  - Update polygonization to summarize additional fields (mean/max of height drop; circular mean for azimuth).
  - Documentation and tests on synthetic terrain.
- Estimate: 16–26 hours.
- Risks: Performance overhead; handling circular statistics for directions; storage size if rasters are exported.

5) Include brittle-layer depth in calculations (absolute or raster), with different pre-/post-layer slopes (e.g., 1:15 then 1:3)
- Goal: Support depth-aware slope criteria and variable threshold above/below the brittle layer per NVE 1/2019.
- Approach:
  - Input options: (a) single absolute depth value, (b) depth raster aligned to DEM.
  - For each pixel–source pair, compute whether the path crosses the brittle depth; apply two slope thresholds: shallow segment vs deeper segment, or implement an effective criterion that depends on z-difference relative to layer depth at source/pixel.
  - In retrogression: adapt min_slope check to account for two-regime criterion as propagation distance increases in elevation.
- Tasks:
  - Extend API to accept depth parameters/raster.
  - Extend `compute_slope` to evaluate two-regime thresholds; ensure vectorized/chunked implementation.
  - Add tests with synthetic DEM and depth raster to validate behavior.
- Estimate: 28–45 hours.
- Risks: Correct geotechnical interpretation of the two-regime model; performance impact; alignment of depth raster.

Summary of estimates (single developer):
- Item 1: 35–55 h
- Item 2: 18–28 h
- Item 3: 10–16 h
- Item 4: 16–26 h
- Item 5: 28–45 h
- Coordination/overhead buffer across all items: ~10–15 h

Total range (all items): ~117–185 hours.

At 2,855 NOK/hour, the cost range is approximately 334,000–528,000 NOK.

---

## Budget proposals

1) Full scope (all requested enhancements)
- Estimated effort: 117–185 hours.
- Budget (range): 334,000–528,000 NOK.
- Notes: This exceeds the 100,000 NOK threshold and would require a public bidding process under their rules. If phased, we can split into milestones (e.g., Item 1 + 3 first, then 2 + 4, then 5).

2) 100,000 NOK assistance scope (focus on performance)
- Budget cap: 100,000 NOK ≈ 35 hours at 2,855 NOK/hour.
- Proposed scope within cap (prioritized for impact vs risk):
  - Item 1 (partial):
    - Replace `distance_matrix` with chunked computation; opportunistic KDTree pruning where feasible.
    - Add HTTP timeouts/retries and simple local caching for DEM requests.
    - Add basic benchmarking and timing logs.
    - Time allocation: ~28–32 h.
  - Item 3 (mask during computation), minimal viable:
    - Integrate mask into both algorithms with aligned rasterization.
    - Time allocation: ~6–8 h.
- Stretch goals if time remains:
  - Return max height drop only (subset of Item 4), basic raster export: ~2–4 h.
  - Cross-platform path fixes and top-level API exports: ~1–2 h.

Deliverables for the 100k scope:
- Refactored core with improved performance, request robustness, and masking applied during computation.
- Short performance report (before/after on representative areas), updated README and minimal docs.

---

## Draft email to client (Norwegian)

Emne: Forslag til videreutvikling av losneomrade – omfang og kostnadsestimat

Hei,

Takk for en god prat og for oversikten over ønskede forbedringer. Jeg har gått grundig gjennom dagens løsning og ser at koden allerede leverer på kjernelogikk (terreng‑kriterier og retrogresjon), men at vi kan hente ut tydelige gevinster ved å forbedre ytelse, robusthet og funksjonalitet.

Nedenfor følger forslag til hvordan vi kan løse punktene, samt et overordnet kostnadsestimat i NOK.

1) Ytelsesoptimalisering (store områder/batcher)
   - Vi refaktorerer helningsberegningen slik at den deles opp i fliser (chunking/tiling), begrenser søket med romlige datastrukturer (f.eks. KDTree) og reduserer minnebruk. I tillegg innfører vi robuste nettverkskall med tidsavbrudd og retry, samt enkel lokal caching av høydedata for å gjøre batch‑kjøringer raskere og mer stabile.

2) Kjøre hver side av initieringsområdet for seg
   - Vi innfører en mulighet til å dele initieringslinjen i to halvplan (venstre/høyre relativt til linjeretningen) og kjøre retrogresjon separat per side, med mulighet til å slå sammen eller rapportere per‑side‑resultater. Dette gir bedre kontroll på retningseffekter.

3) Maskere områder uten marin leire i selve beregningen
   - Vi rasteriserer MSML/AUMG til en beregningsmaske som brukes underveis, slik at områder uten marin leire ekskluderes allerede i beregningstrinnene (ikke bare ved etterfølgende klipp). Resultatet blir mer konsistent og effektivt.

4) Ekstra parametere i resultatet
   - Vi utvider resultatene med maksimal høydeforskjell (fall) fra hver piksel til utløsende punkt og beregner retning (azimut) til punktet som gir maksimal helning. Disse kan leveres som rasterbånd og/eller aggregeres inn i polygonattributter.

5) Sprøbrudd‑lag (dybde) i beregningene
   - Vi legger inn støtte for enten en fast dybde eller et dybderaster for sprøbrudd‑laget, og ulike helningskrav over/under laget (for eksempel 1:15 – 1:3) i tråd med NVE 1/2019. Dette gir mer realistiske terskler i variabel geologi.

Kostnadsestimat – full leveranse (alle punkter)
For en full leveranse som omfatter alle forbedringene over, anslår jeg et budsjett i størrelsesorden 334 000–528 000 NOK. Dette inkluderer design, implementasjon, dokumentasjon og grunnleggende tester, samt noe iterasjon for innfasing.

Alternativ – bistand innenfor 100 000 NOK
Innenfor en ramme på 100 000 NOK vil jeg anbefale å prioritere ytelsesoptimalisering (punkt 1) og å bruke maskering i beregningen (punkt 3). Det innebærer å gjøre beregningene raskere og mer minneeffektive, innføre robuste nettverkskall og enkel caching, samt sikre at områder uten marin leire ekskluderes underveis. Hvis det gjenstår rom i budsjettet, kan vi også eksponere maksimal høydeforskjell i resultatet og gjøre noen mindre forbedringer (for eksempel API‑eksport og bedre håndtering av filstier).

I tillegg vil vi hjelpe til med å rydde og refaktorere koden i tråd med anbefalte praksiser for Python (struktur, logging, typer/dokstringer, testbarhet) for å gjøre videre vedlikehold enklere.

Jeg forstår at webapplikasjonen er implementert et annet sted. Det blir viktig å sikre at denne koden og webappen fortsatt er kompatible når vi innfører forbedringene. Vi vil derfor koordinere grensesnitt og endringer slik at integrasjonen opprettholdes.

Gi gjerne en tilbakemelding på hvilket alternativ som passer best, så kan vi konkretisere leveranser og fremdriftsplan. Jeg tar gjerne en kort gjennomgang på Teams for å avklare detaljer.

Vennlig hilsen

[Ditt navn]
[Firma]
[Telefon]
[E‑post]
