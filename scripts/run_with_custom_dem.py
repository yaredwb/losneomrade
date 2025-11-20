"""
Release Area Analysis with Custom DEM
======================================
This script uses your local DEM file (dem_byneset_5m.tif) instead of fetching
from Høydedata.no. This is faster and works offline!

Usage:
    python scripts/run_with_custom_dem.py
"""

import sys
from pathlib import Path
import geopandas as gpd

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from losneomrade import terrain_criteria, retrogression


def main():
    print("\n" + "="*70)
    print("RELEASE AREA ANALYSIS WITH CUSTOM DEM")
    print("="*70)
    
    # =========================================================================
    # CONFIGURATION
    # =========================================================================
    
    # Input files
    STREAM_FILE = "data/streams_as_source.geojson"
    CUSTOM_DEM = "data/dem_byneset_5m.tif"  # Your DEM file!
    
    # Analysis parameters (NVE standard)
    SOURCE_DEPTH = 0.0      # Depth of source (meters)
    MIN_HEIGHT = 5.0        # Minimum height (meters)
    MIN_SLOPE = 1/15        # Slope criterion (1:15 ratio)
    MIN_LENGTH = 75.0       # Minimum length (meters)
    CLIP_TO_MSML = False    # Clip to marine clay areas
    
    # Buffer around streams (meters)
    BUFFER_DISTANCE = 300  # Reduced from 500 to avoid memory issues
    
    # Source point generation (points per meter along stream lines)
    # Higher = more detailed but uses more memory. Lower = faster, less memory
    POINTS_PER_METER = 1/10  # One point every 10 meters (default is 1/5)
    
    # Output directory
    OUTPUT_DIR = "output"
    
    print(f"\nConfiguration:")
    print(f"  - Stream file: {STREAM_FILE}")
    print(f"  - DEM file: {CUSTOM_DEM}")
    print(f"  - Source depth: {SOURCE_DEPTH}m")
    print(f"  - Min height: {MIN_HEIGHT}m")
    print(f"  - Min slope: 1:{int(1/MIN_SLOPE)}")
    print(f"  - Min length: {MIN_LENGTH}m")
    print(f"  - Buffer: {BUFFER_DISTANCE}m")
    
    # =========================================================================
    # LOAD DATA
    # =========================================================================
    
    print("\n" + "-"*70)
    print("STEP 1: LOADING DATA")
    print("-"*70)
    
    # Load streams
    print(f"\nLoading streams from: {STREAM_FILE}")
    streams = gpd.read_file(STREAM_FILE)
    print(f"✓ Loaded {len(streams)} stream features")
    print(f"  - CRS: {streams.crs}")
    print(f"  - Geometry types: {streams.geom_type.unique().tolist()}")
    
    # Verify DEM file exists
    dem_path = Path(CUSTOM_DEM)
    if not dem_path.exists():
        print(f"\n✗ ERROR: DEM file not found: {CUSTOM_DEM}")
        print("  Please check the file path and try again.")
        sys.exit(1)
    
    print(f"\n✓ DEM file found: {CUSTOM_DEM}")
    print(f"  - File size: {dem_path.stat().st_size / (1024*1024):.2f} MB")
    
    # Calculate bounds
    bounds_array = streams.total_bounds  # [minx, miny, maxx, maxy]
    bounds = (
        bounds_array[0] - BUFFER_DISTANCE,  # xmin
        bounds_array[2] + BUFFER_DISTANCE,  # xmax
        bounds_array[1] - BUFFER_DISTANCE,  # ymin
        bounds_array[3] + BUFFER_DISTANCE   # ymax
    )
    
    print(f"\nAnalysis bounds (with {BUFFER_DISTANCE}m buffer):")
    print(f"  - X: {bounds[0]:.2f} to {bounds[1]:.2f} ({bounds[1]-bounds[0]:.2f}m)")
    print(f"  - Y: {bounds[2]:.2f} to {bounds[3]:.2f} ({bounds[3]-bounds[2]:.2f}m)")
    
    # =========================================================================
    # TERRAIN CRITERIA ANALYSIS
    # =========================================================================
    
    print("\n" + "-"*70)
    print("STEP 2: TERRAIN CRITERIA ANALYSIS")
    print("-"*70)
    print("\nGenerating source points from streams...")
    print(f"  - Point spacing: {1/POINTS_PER_METER:.1f}m")
    
    # Generate source points with controlled density
    from losneomrade.terrain_criteria import generate_source_points
    source_points = generate_source_points(streams, distance_chainage=1/POINTS_PER_METER)
    print(f"  - Generated {len(source_points):,} source points")
    
    print("\nAnalyzing terrain criteria (slope > 1:15)...")
    print("Using local DEM file - no internet connection needed!")
    
    try:
        tc_result = terrain_criteria.run_terrain_criteria(
            bounds=bounds,
            source=source_points,  # Using pre-generated points with controlled density
            source_depth=SOURCE_DEPTH,
            clip_to_msml=CLIP_TO_MSML,
            h_min=MIN_HEIGHT,
            reclassify_results=True,
            custom_raster=CUSTOM_DEM  # Using your DEM!
        )
        
        print(f"\n✓ Terrain criteria analysis completed!")
        print(f"  - Polygons generated: {len(tc_result)}")
        print(f"  - Total area: {tc_result.geometry.area.sum():.2f} m²")
        print(f"  - Total area: {tc_result.geometry.area.sum()/10000:.2f} hectares")
        
    except Exception as e:
        print(f"\n✗ ERROR in terrain criteria analysis:")
        print(f"  {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Save terrain criteria result
    Path(OUTPUT_DIR).mkdir(exist_ok=True)
    tc_output = f"{OUTPUT_DIR}/terrain_criteria_custom_dem.geojson"
    tc_result.to_file(tc_output, driver='GeoJSON')
    print(f"\n✓ Saved to: {tc_output}")
    
    # =========================================================================
    # RETROGRESSION ANALYSIS
    # =========================================================================
    
    print("\n" + "-"*70)
    print("STEP 3: RETROGRESSION ANALYSIS")
    print("-"*70)
    print("\nRunning retrogression analysis...")
    print("This step-wise propagation may take a few minutes...")
    
    try:
        retro_result = retrogression.run_retrogression(
            bounds=bounds,
            rel_shape=tc_result,
            point_depth=SOURCE_DEPTH,
            clip_to_msml=CLIP_TO_MSML,
            min_slope=MIN_SLOPE,
            min_height=MIN_HEIGHT,
            min_length=MIN_LENGTH,
            custom_raster=CUSTOM_DEM,  # Using your DEM!
            return_animation=False,
            verbose=True
        )
        
        print(f"\n✓ Retrogression analysis completed!")
        print(f"  - Polygons generated: {len(retro_result)}")
        print(f"  - Total area: {retro_result.geometry.area.sum():.2f} m²")
        print(f"  - Total area: {retro_result.geometry.area.sum()/10000:.2f} hectares")
        
    except Exception as e:
        print(f"\n✗ ERROR in retrogression analysis:")
        print(f"  {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Save retrogression result
    retro_output = f"{OUTPUT_DIR}/retrogression_custom_dem.geojson"
    retro_result.to_file(retro_output, driver='GeoJSON')
    print(f"\n✓ Saved to: {retro_output}")
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    
    print("\n" + "="*70)
    print("ANALYSIS COMPLETE!")
    print("="*70)
    
    print("\n📊 RESULTS SUMMARY:")
    print(f"\nTerrain Criteria:")
    print(f"  - Polygons: {len(tc_result)}")
    print(f"  - Area: {tc_result.geometry.area.sum()/10000:.2f} hectares")
    
    print(f"\nRetrogression:")
    print(f"  - Polygons: {len(retro_result)}")
    print(f"  - Area: {retro_result.geometry.area.sum()/10000:.2f} hectares")
    
    print(f"\n📁 OUTPUT FILES:")
    print(f"  - {tc_output}")
    print(f"  - {retro_output}")
    
    print(f"\n💡 NEXT STEPS:")
    print(f"  1. Open results in QGIS/ArcGIS")
    print(f"  2. Load {STREAM_FILE} for reference")
    print(f"  3. Compare terrain criteria vs retrogression")
    print(f"  4. Run: python scripts/visualize_results_custom_dem.py")
    
    # Save summary file
    summary_file = f"{OUTPUT_DIR}/analysis_summary_custom_dem.txt"
    with open(summary_file, 'w') as f:
        f.write("RELEASE AREA ANALYSIS - CUSTOM DEM\n")
        f.write("="*60 + "\n\n")
        
        from datetime import datetime
        f.write(f"Analysis date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        f.write("INPUT DATA:\n")
        f.write(f"  - Streams: {STREAM_FILE}\n")
        f.write(f"  - DEM: {CUSTOM_DEM}\n")
        f.write(f"  - Stream features: {len(streams)}\n\n")
        
        f.write("PARAMETERS:\n")
        f.write(f"  - Source depth: {SOURCE_DEPTH} m\n")
        f.write(f"  - Minimum height: {MIN_HEIGHT} m\n")
        f.write(f"  - Minimum slope: 1:{int(1/MIN_SLOPE)} ({MIN_SLOPE:.4f})\n")
        f.write(f"  - Minimum length: {MIN_LENGTH} m\n")
        f.write(f"  - Buffer distance: {BUFFER_DISTANCE} m\n")
        f.write(f"  - MSML clipping: {CLIP_TO_MSML}\n\n")
        
        f.write("RESULTS:\n")
        f.write(f"\nTerrain Criteria:\n")
        f.write(f"  - Polygons: {len(tc_result)}\n")
        f.write(f"  - Total area: {tc_result.geometry.area.sum():.2f} m²\n")
        f.write(f"  - Total area: {tc_result.geometry.area.sum()/10000:.2f} hectares\n")
        
        f.write(f"\nRetrogression:\n")
        f.write(f"  - Polygons: {len(retro_result)}\n")
        f.write(f"  - Total area: {retro_result.geometry.area.sum():.2f} m²\n")
        f.write(f"  - Total area: {retro_result.geometry.area.sum()/10000:.2f} hectares\n")
        
        f.write(f"\nOUTPUT FILES:\n")
        f.write(f"  - {tc_output}\n")
        f.write(f"  - {retro_output}\n")
    
    print(f"\n✓ Summary saved to: {summary_file}")
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()
