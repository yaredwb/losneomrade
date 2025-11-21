import sys
import os
import argparse
from pathlib import Path
import geopandas as gpd
import time

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

try:
    from losneomrade import terrain_criteria, retrogression
except ImportError:
    print("Could not import losneomrade. Make sure the 'src' directory is correctly structured.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Run Retrogression Analysis (Optimized)")
    parser.add_argument("--stream-file", default="data/streams_as_source.geojson", help="Path to stream input file")
    parser.add_argument("--output-dir", default="output", help="Directory to save results")
    parser.add_argument("--n-processes", type=int, default=None, help="Number of parallel processes (default: auto)")
    args = parser.parse_args()

    print("\n" + "="*70)
    print("RETROGRESSION ANALYSIS (OPTIMIZED - PARALLEL)")
    print("="*70)

    # Configuration
    STREAM_FILE = args.stream_file
    CUSTOM_DEM = "data/dem_byneset_5m.tif"
    
    # Parameters
    SOURCE_DEPTH = 0.0
    MIN_HEIGHT = 5.0
    MIN_SLOPE = 1/15
    MIN_LENGTH = 75.0
    CLIP_TO_MSML = False
    BUFFER_DISTANCE = 300
    POINTS_PER_METER = 1/10
    INITIAL_BUFFER = 10  # meters

    print(f"\nConfiguration:")
    print(f"  - Stream file: {STREAM_FILE}")
    print(f"  - DEM file: {CUSTOM_DEM}")
    print(f"  - Output dir: {args.output_dir}")
    print(f"  - Parallel processes: {args.n_processes or 'auto'}")

    # 1. Load Data
    if not os.path.exists(STREAM_FILE):
        print(f"\n✗ ERROR: Stream file not found: {STREAM_FILE}")
        sys.exit(1)
        
    dem_path = Path(CUSTOM_DEM)
    if not dem_path.exists():
        print(f"\n✗ ERROR: DEM file not found: {CUSTOM_DEM}")
        sys.exit(1)

    print(f"\nLoading streams...")
    streams = gpd.read_file(STREAM_FILE)
    print(f"✓ Loaded {len(streams)} stream features")

    # Calculate bounds
    bounds_array = streams.total_bounds
    bounds = (
        bounds_array[0] - BUFFER_DISTANCE,
        bounds_array[2] + BUFFER_DISTANCE,
        bounds_array[1] - BUFFER_DISTANCE,
        bounds_array[3] + BUFFER_DISTANCE
    )

    # 2. Generate Source Points
    print("\nGenerating source points...")
    try:
        source_points = terrain_criteria.generate_source_points(
            streams, 
            distance_chainage=1/POINTS_PER_METER
        )
        print(f"✓ Generated {len(source_points):,} source points")
    except Exception as e:
        print(f"\n✗ ERROR generating source points: {e}")
        sys.exit(1)

    # 3. Create Initial Release Zones
    print(f"\nCreating initial release zones (buffer={INITIAL_BUFFER}m)...")
    try:
        from shapely.geometry import Point
        
        point_geometries = [Point(x, y) for x, y in source_points[:, :2]]
        points_gdf = gpd.GeoDataFrame(geometry=point_geometries, crs='EPSG:25833')
        
        initial_release = points_gdf.buffer(INITIAL_BUFFER)
        initial_release_gdf = gpd.GeoDataFrame(geometry=initial_release, crs='EPSG:25833')
        initial_release_dissolved = initial_release_gdf.dissolve()
        
        print(f"✓ Created {len(initial_release_dissolved)} initial release zones")
    except Exception as e:
        print(f"\n✗ ERROR creating release zones: {e}")
        sys.exit(1)

    # 4. Run Retrogression Analysis (OPTIMIZED - PARALLEL)
    print(f"\nRunning retrogression analysis (Parallel)...")
    start_time = time.time()
    
    try:
        retro_result = retrogression.run_retrogression_parallel(
            bounds=bounds,
            rel_shape=initial_release_dissolved,
            point_depth=SOURCE_DEPTH,
            clip_to_msml=CLIP_TO_MSML,
            min_slope=MIN_SLOPE,
            min_height=MIN_HEIGHT,
            min_length=MIN_LENGTH,
            custom_raster=CUSTOM_DEM,
            n_processes=args.n_processes
        )
        
        duration = time.time() - start_time
        
        print(f"\n✓ Analysis completed in {duration:.1f}s!")
        print(f"  - Polygons: {len(retro_result)}")
        print(f"  - Area: {retro_result.geometry.area.sum()/10000:.2f} hectares")
        
    except Exception as e:
        print(f"\n✗ ERROR in analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 5. Save Results
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    output_file = os.path.join(args.output_dir, "retrogression_analysis_optimized.geojson")
    retro_result.to_file(output_file, driver='GeoJSON')
    print(f"\n✓ Saved to: {output_file}")

if __name__ == "__main__":
    main()
