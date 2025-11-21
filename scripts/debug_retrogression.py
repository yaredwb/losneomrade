import sys
import os
from pathlib import Path
import geopandas as gpd
import numpy as np
from scipy.ndimage import label

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from losneomrade import terrain_criteria, retrogression, utils
from shapely.geometry import Point

# Configuration
STREAM_FILE = "data/streams_subset_15.geojson"
CUSTOM_DEM = "data/dem_byneset_5m.tif"
SOURCE_DEPTH = 0.0
BUFFER_DISTANCE = 300
POINTS_PER_METER = 1/10
INITIAL_BUFFER = 10

print("\n" + "="*70)
print("DEBUG: Investigating Retrogression Discrepancy")
print("="*70)

# Load data
streams = gpd.read_file(STREAM_FILE)
print(f"\nLoaded {len(streams)} streams")

# Generate source points
source_points = terrain_criteria.generate_source_points(streams, distance_chainage=1/POINTS_PER_METER)
print(f"Generated {len(source_points)} source points")

# Create initial release zones (matching baseline logic)
point_geometries = [Point(x, y) for x, y in source_points[:, :2]]
points_gdf = gpd.GeoDataFrame(geometry=point_geometries, crs=streams.crs)
initial_release = points_gdf.buffer(INITIAL_BUFFER)
initial_release_gdf = gpd.GeoDataFrame(geometry=initial_release, crs=streams.crs)
initial_release_dissolved = initial_release_gdf.dissolve()

print(f"\nAfter dissolve:")
print(f"  - GeoDataFrame rows: {len(initial_release_dissolved)}")
print(f"  - Geometry type: {type(initial_release_dissolved.geometry.iloc[0])}")
print(f"  - Is MultiPolygon: {initial_release_dissolved.geometry.iloc[0].geom_type == 'MultiPolygon'}")
if initial_release_dissolved.geometry.iloc[0].geom_type == 'MultiPolygon':
    print(f"  - Number of sub-polygons: {len(initial_release_dissolved.geometry.iloc[0].geoms)}")

# Load DEM
window_data = utils.generate_windows(CUSTOM_DEM)
dem_array = window_data["full_array"]
dem_profile = window_data["profile"]

# Rasterize
print("\nRasterizing...")
rel = utils.rasterize_shape(initial_release_dissolved, dem_profile)
print(f"  - Rasterized array shape: {rel.shape}")
print(f"  - Non-zero pixels: {np.sum(rel > 0)}")

# Label connected components
labeled_array, num_features = label(rel)
print(f"  - Connected components: {num_features}")

# Show distribution
if num_features > 0:
    for i in range(1, min(num_features + 1, 6)):  # Show first 5
        count = np.sum(labeled_array == i)
        print(f"    Component {i}: {count} pixels")
    if num_features > 5:
        print(f"    ... and {num_features - 5} more components")

print("\n" + "="*70)
print("This explains why the parallel version splits into components!")
print("="*70)
