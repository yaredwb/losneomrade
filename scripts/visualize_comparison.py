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

def plot_results(ax, dem_file, stream_file, retro_file, title):
    """Plot results on a given axis"""
    
    # 1. Plot DEM Hillshade
    with rasterio.open(dem_file) as src:
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

    # 2. Plot Streams
    if os.path.exists(stream_file):
        streams = gpd.read_file(stream_file)
        streams.plot(ax=ax, color='blue', linewidth=1.5, label='Streams', zorder=2)

    # 3. Plot Retrogression Results
    if os.path.exists(retro_file):
        retro_gdf = gpd.read_file(retro_file)
        if not retro_gdf.empty:
            retro_gdf.plot(ax=ax, color='red', alpha=0.6, edgecolor='darkred', label='Retrogression', zorder=4)
            
            # Add statistics to title
            n_polygons = len(retro_gdf)
            area_ha = retro_gdf.geometry.area.sum() / 10000
            title = f"{title}\n{n_polygons} polygons, {area_ha:.2f} ha"
        else:
            title = f"{title}\nNo results"
    else:
        title = f"{title}\nFile not found"

    # Formatting
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    
    # Create custom legend
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    
    legend_elements = [
        Line2D([0], [0], color='blue', lw=2, label='Streams'),
        Patch(facecolor='red', edgecolor='darkred', alpha=0.6, label='Retrogression')
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=8)
    
    # Add grid
    ax.grid(True, linestyle='--', alpha=0.3)

def main():
    parser = argparse.ArgumentParser(description="Compare Baseline vs Optimized Results")
    parser.add_argument("--dem-file", default="data/dem_byneset_5m.tif", help="Path to DEM file")
    parser.add_argument("--stream-file", default="data/streams_subset_15.geojson", help="Path to stream file")
    parser.add_argument("--baseline-file", default="output/retrogression_analysis.geojson", help="Path to baseline results")
    parser.add_argument("--optimized-file", default="output/retrogression_analysis_optimized.geojson", help="Path to optimized results")
    parser.add_argument("--output-dir", default="output", help="Directory to save visualization")
    args = parser.parse_args()

    print("\n" + "="*70)
    print("COMPARING BASELINE VS OPTIMIZED RESULTS")
    print("="*70)

    # Check inputs
    if not os.path.exists(args.dem_file):
        print(f"Error: DEM file not found: {args.dem_file}")
        sys.exit(1)
        
    # Create output directory
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    # Setup Plot - side by side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))
    
    # Plot baseline
    print("\nPlotting baseline results...")
    plot_results(ax1, args.dem_file, args.stream_file, args.baseline_file, "Baseline (Sequential)")
    
    # Plot optimized
    print("Plotting optimized results...")
    plot_results(ax2, args.dem_file, args.stream_file, args.optimized_file, "Optimized (Parallel)")
    
    # Overall title
    fig.suptitle("Retrogression Analysis: Baseline vs Optimized", fontsize=16, fontweight='bold')
    
    plt.tight_layout()

    # Save
    output_path = os.path.join(args.output_dir, "comparison_baseline_vs_optimized.png")
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\n✓ Comparison visualization saved to: {output_path}")
    
    # Close plot to free memory
    plt.close()

if __name__ == "__main__":
    main()
