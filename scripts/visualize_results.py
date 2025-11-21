import argparse
import os
import sys
import geopandas as gpd
import rasterio
from rasterio.plot import show
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
import numpy as np
from pathlib import Path

def normalize(array):
    """Normalize array to 0-1 range"""
    array_min, array_max = np.nanmin(array), np.nanmax(array)
    return (array - array_min) / (array_max - array_min)

def main():
    parser = argparse.ArgumentParser(description="Visualize Release Area Analysis Results")
    parser.add_argument("--dem-file", default="data/dem_byneset_5m.tif", help="Path to DEM file")
    parser.add_argument("--stream-file", default="data/streams_subset.geojson", help="Path to stream file")
    parser.add_argument("--tc-file", default="output/terrain_criteria_analysis.geojson", help="Path to terrain criteria results")
    parser.add_argument("--retro-file", default="output/retrogression_analysis.geojson", help="Path to retrogression results")
    parser.add_argument("--output-dir", default="output", help="Directory to save visualization")
    args = parser.parse_args()

    print("\n" + "="*70)
    print("VISUALIZING RESULTS")
    print("="*70)

    # Check inputs
    if not os.path.exists(args.dem_file):
        print(f"Error: DEM file not found: {args.dem_file}")
        sys.exit(1)
        
    # Create output directory
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    # Setup Plot
    fig, ax = plt.subplots(figsize=(15, 10))
    
    # 1. Plot DEM Hillshade
    print("Plotting DEM hillshade...")
    with rasterio.open(args.dem_file) as src:
        dem_data = src.read(1)
        dem_transform = src.transform
        extent = [
            src.bounds.left, src.bounds.right,
            src.bounds.bottom, src.bounds.top
        ]
        
        # Create hillshade
        ls = LightSource(azdeg=315, altdeg=45)
        hs = ls.hillshade(dem_data, vert_exag=1)
        
        ax.imshow(hs, cmap='gray', extent=extent, origin='upper', alpha=0.8)
        
        # Optional: Add elevation overlay
        # ax.imshow(dem_data, cmap='terrain', extent=extent, origin='upper', alpha=0.3)

    # 2. Plot Streams
    if os.path.exists(args.stream_file):
        print("Plotting streams...")
        streams = gpd.read_file(args.stream_file)
        streams.plot(ax=ax, color='blue', linewidth=1.5, label='Streams', zorder=2)

    # 3. Plot Terrain Criteria Results
    if os.path.exists(args.tc_file):
        print("Plotting terrain criteria results...")
        tc_gdf = gpd.read_file(args.tc_file)
        if not tc_gdf.empty:
            tc_gdf.plot(ax=ax, color='orange', alpha=0.5, edgecolor='darkorange', label='Terrain Criteria', zorder=3)
        else:
            print("Warning: Terrain criteria file is empty.")

    # 4. Plot Retrogression Results
    if os.path.exists(args.retro_file):
        print("Plotting retrogression results...")
        retro_gdf = gpd.read_file(args.retro_file)
        if not retro_gdf.empty:
            retro_gdf.plot(ax=ax, color='red', alpha=0.6, edgecolor='darkred', label='Retrogression', zorder=4)
        else:
            print("Warning: Retrogression file is empty.")

    # Formatting
    ax.set_title("Release Area Analysis Results", fontsize=16, fontweight='bold')
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    
    # Create custom legend
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    
    legend_elements = [
        Line2D([0], [0], color='blue', lw=2, label='Streams'),
        Patch(facecolor='orange', edgecolor='darkorange', alpha=0.5, label='Terrain Criteria'),
        Patch(facecolor='red', edgecolor='darkred', alpha=0.6, label='Retrogression (Independent)')
    ]
    ax.legend(handles=legend_elements, loc='upper right')
    
    # Add grid
    ax.grid(True, linestyle='--', alpha=0.3)

    # Save
    output_path = os.path.join(args.output_dir, "analysis_visualization.png")
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\n✓ Visualization saved to: {output_path}")
    
    # Close plot to free memory
    plt.close()

if __name__ == "__main__":
    main()
