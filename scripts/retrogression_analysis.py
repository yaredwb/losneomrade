import sys
import os
import argparse
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Point
import time

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

try:
    from losneomrade import terrain_criteria, retrogression
except ImportError:
    print("Could not import losneomrade. Make sure the 'src' directory is correctly structured.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Run Independent Retrogression Analysis")
    parser.add_argument("--stream-file", default="data/streams_as_source.geojson", help="Path to stream input file")
    parser.add_argument("--output-dir", default="output", help="Directory to save results")
    args = parser.parse_args()

    print("\n" + "="*70)
    print("INDEPENDENT RETROGRESSION ANALYSIS")
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
    INITIAL_BUFFER = 10  # Buffer radius for initial release zones

    print(f"\nConfiguration:")
    print(f"  - Stream file: {STREAM_FILE}")
    print(f"  - DEM file: {CUSTOM_DEM}")

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

    # 2. Generate Source Points (Required for Independent Method)
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

    # 3. Create Initial Release Zones (Independent Method Logic)
    print("\nCreating initial release zones from source points...")
    try:
        # Create point geometries
        # source_points is a numpy array [x, y, z, ...]
        point_geometries = [Point(x, y) for x, y in source_points[:, :2]]
        points_gdf = gpd.GeoDataFrame(geometry=point_geometries, crs=streams.crs)

        # Buffer points to create initial release zones
        initial_release = points_gdf.buffer(INITIAL_BUFFER)
        initial_release_gdf = gpd.GeoDataFrame(geometry=initial_release, crs=streams.crs)

        # Dissolve overlapping buffers
        initial_release_dissolved = initial_release_gdf.dissolve()
        
        print(f"✓ Created {len(initial_release_dissolved)} initial release zones")
        print(f"  - Buffer radius: {INITIAL_BUFFER}m")
        
    except Exception as e:
        print(f"\n✗ ERROR creating initial release zones: {e}")
        sys.exit(1)

    # 4. Run Retrogression Analysis
    print("\nRunning retrogression analysis (Independent Method)...")
    try:
        retro_result = retrogression.run_retrogression(
            bounds=bounds,
            rel_shape=initial_release_dissolved,  # Use the buffered source points
            point_depth=SOURCE_DEPTH,
            clip_to_msml=CLIP_TO_MSML,
            min_slope=MIN_SLOPE,
            min_height=MIN_HEIGHT,
            min_length=MIN_LENGTH,
            custom_raster=CUSTOM_DEM,
            return_animation=False,
            verbose=False  # Disable verbose to avoid tqdm notebook error in terminal
        )
        
        print(f"\n✓ Analysis completed!")
        print(f"  - Polygons: {len(retro_result)}")
        print(f"  - Area: {retro_result.geometry.area.sum()/10000:.2f} hectares")
        
    except Exception as e:
        print(f"\n✗ ERROR in analysis: {e}")
        sys.exit(1)

    # 5. Save Results
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    output_file = os.path.join(args.output_dir, "retrogression_analysis.geojson")
    retro_result.to_file(output_file, driver='GeoJSON')
    print(f"\n✓ Saved to: {output_file}")

if __name__ == "__main__":
    main()
