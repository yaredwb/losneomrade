import sys
import os
import argparse
from pathlib import Path
import geopandas as gpd
import time

# Add the src directory to the path
# Assumes script is in 'scripts/' and 'src' is in root
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

try:
    from losneomrade import terrain_criteria
except ImportError:
    print("Could not import losneomrade. Make sure the 'src' directory is correctly structured.")
    sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Run Terrain Criteria Analysis")
    parser.add_argument("--stream-file", default="data/streams_as_source.geojson", help="Path to stream input file")
    parser.add_argument("--output-dir", default="output", help="Directory to save results")
    args = parser.parse_args()

    print("\n" + "="*70)
    print("TERRAIN CRITERIA ANALYSIS")
    print("="*70)

    # Configuration
    STREAM_FILE = args.stream_file
    CUSTOM_DEM = "data/dem_byneset_5m.tif"  # Default from run_with_custom_dem.py
    
    # Parameters (matching run_with_custom_dem.py)
    SOURCE_DEPTH = 0.0
    MIN_HEIGHT = 5.0
    MIN_SLOPE = 1/15
    MIN_LENGTH = 75.0
    CLIP_TO_MSML = False
    BUFFER_DISTANCE = 300
    POINTS_PER_METER = 1/10

    print(f"\nConfiguration:")
    print(f"  - Stream file: {STREAM_FILE}")
    print(f"  - DEM file: {CUSTOM_DEM}")
    print(f"  - Output dir: {args.output_dir}")

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

    # 3. Run Analysis
    print("\nRunning terrain criteria analysis...")
    try:
        tc_result = terrain_criteria.run_terrain_criteria(
            bounds=bounds,
            source=source_points,
            source_depth=SOURCE_DEPTH,
            clip_to_msml=CLIP_TO_MSML,
            h_min=MIN_HEIGHT,
            reclassify_results=True,
            custom_raster=CUSTOM_DEM
        )
        
        # Post-processing: Clip to buffer
        # When using custom_raster, the bounds are ignored by the module, 
        # so we must manually clip the results to the area of interest.
        print(f"  - Raw polygons: {len(tc_result)}")
        print(f"  - Clipping results to {BUFFER_DISTANCE}m buffer around streams...")
        
        stream_buffer = streams.buffer(BUFFER_DISTANCE)
        # Create a single geometry for clipping
        mask_geom = stream_buffer.unary_union
        
        # Clip
        tc_result = gpd.clip(tc_result, gpd.GeoSeries([mask_geom], crs=streams.crs))
        
        print(f"\n✓ Analysis completed!")
        print(f"  - Polygons: {len(tc_result)}")
        print(f"  - Area: {tc_result.geometry.area.sum()/10000:.2f} hectares")
        
    except Exception as e:
        print(f"\n✗ ERROR in analysis: {e}")
        sys.exit(1)

    # 4. Save Results
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    output_file = os.path.join(args.output_dir, "terrain_criteria_analysis.geojson")
    tc_result.to_file(output_file, driver='GeoJSON')
    print(f"\n✓ Saved to: {output_file}")

if __name__ == "__main__":
    main()
