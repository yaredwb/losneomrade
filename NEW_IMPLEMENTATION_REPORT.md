# Løsneområde Implementation Report

## 1. Introduction

This report provides a comprehensive overview of the `losneomrade` Python repository. The primary purpose of this repository is to calculate and model potential quick-clay landslide release areas in Norway. It provides tools to assess landslide hazards based on terrain characteristics and geotechnical parameters.

The repository implements two main methodologies for this purpose:

1. **Terrain Criteria Analysis**: A pixel-based method that calculates slope angles from a given set of source points to all other points in a Digital Elevation Model (DEM). This helps identify areas that meet specific slope criteria for potential instability.
2. **Landslide Retrogression Analysis**: An iterative simulation that models the progressive failure of a slope, starting from an initial release area. This method helps to estimate the full extent of a potential landslide.

The package is designed to work with geospatial data, leveraging common Python libraries for GIS analysis and data manipulation. It can fetch elevation data directly from Norwegian public data sources (Høydedata.no) and integrates with marine clay deposit maps (MSML).

## 2. Project Structure

The repository is organized into the following main directories and files:

- `src/losneomrade/`: Contains the core source code.
  - `__init__.py`: Initializes the package.
  - `terrain_criteria.py`: Implements the pixel-based terrain criteria analysis.
  - `retrogression.py`: Implements the landslide retrogression simulation.
  - `utils.py`: A collection of utility functions for data fetching, coordinate transformations, and geospatial operations.
- `notebooks/`: Contains Jupyter notebooks for demonstrating the usage of the library.
  - `test.ipynb`: A notebook with practical examples of running both terrain criteria and retrogression analyses.
- `tests/`: Contains unit tests for the source code.
  - `test_losneomrade.py`: Tests for the main analysis functions.
  - `test_utils.py`: Tests for the utility functions.
  - `testdata/`: Contains data used for testing, such as GeoJSON templates.
- `pyproject.toml`: Defines project metadata and dependencies.
- `README.md`: Provides a general introduction to the project.

## 3. Dependencies

The project relies on several key open-source libraries for its functionality:

- **numpy**: For numerical operations and array manipulation.
- **pandas**: For data structures and analysis.
- **geopandas**: For working with geospatial data in a DataFrame-like structure.
- **Shapely**: For geometric operations.
- **rasterio**: For reading, writing, and processing raster data (DEMs).
- **matplotlib** & **plotly**: For plotting and visualization.
- **scipy**: For scientific and technical computing, particularly for spatial distance calculations.
- **requests** & **urllib3**: For making HTTP requests to fetch data from web services.
- **tqdm**: For displaying progress bars during long computations.

## 4. Methodology

The repository implements two distinct but related methods for landslide analysis.

### 4.1. Terrain Criteria (`terrain_criteria.py`)

This method evaluates the terrain based on slope angles relative to a set of source points. The core idea is to identify all areas in a DEM that have a slope angle greater than a specified threshold when measured from the source points.

#### Key Functions and Procedures for Terrain Criteria

1. **`run_terrain_criteria`**: This is the main wrapper function that orchestrates the entire process. It takes the calculation bounds, source points (as a GeoDataFrame or NumPy array), and other parameters.
2. **`generate_source_points`**: If the input is a line (e.g., a road or river), this function generates a series of points along that line at a specified distance. These points then serve as the source for the slope calculations.
3. **`terrain_criteria`**: This function manages the main calculation. It fetches the DEM data for the specified bounds, sets the elevation for the source points, and then iterates through the DEM in windows (smaller chunks) to perform the slope calculations.
4. **`compute_from_windows`**: To handle large DEMs without consuming excessive memory, the calculation is performed on smaller windows of the raster. For each window, this function calculates the slope from every pixel in the window to all the source points.
5. **`compute_slope` (in `utils.py`)**: This is the core calculation engine. For each pixel in the DEM window, it calculates the distance and height difference to every source point. The slope is calculated as `height_difference / distance`. It then finds the maximum slope for each pixel from all source points. A minimum height difference (`h_min`) can be set to avoid calculating slopes for very small height differences.
6. **`reclass`**: After the slope values are calculated, they are reclassified into discrete categories based on predefined slope thresholds (e.g., 1:20, 1:15, 1:5). This makes the results easier to interpret.
7. **`polygonize_terrain_criteria`**: The final raster with the classified slope values is converted into a vector format (polygons). Each polygon represents an area with a specific slope class.
8. **`clip_results_to_msml`**: Optionally, the final results can be clipped to areas known to have marine clay deposits (MSML), which are more susceptible to quick-clay landslides. This is done by fetching data from NVE's map services.

### 4.2. Retrogression (`retrogression.py`)

This method simulates the progressive failure of a landslide. It starts with an initial release area and iteratively expands it based on a slope criterion.

#### Key Functions and Procedures for Retrogression

1. **`run_retrogression`**: The main wrapper function for the retrogression analysis. It takes the calculation bounds, an initial release shape, and parameters like minimum slope and length.
2. **`landslide_retrogression`**: This is the core of the simulation. It works as follows:
    a. **Initialization**: It starts with an initial release area, which is a binary mask on the DEM.
    b. **Iteration**: In each step of the simulation, it creates a buffer of one pixel around the current release area. These are the "neighbor" pixels.
    c. **Slope Check**: For each neighbor pixel, it calculates the slope back to the original release points.
    d. **Expansion**: If the slope of a neighbor pixel is greater than the `min_slope` threshold, that pixel is added to the release area for the next iteration.
    e. **Stop Criteria**: The simulation stops when no new pixels are added to the release area in an iteration, or when a maximum length is reached. A `min_length` parameter ensures that the simulation runs for a certain number of iterations before the slope check is applied, simulating an initial failure before the retrogression slows down.
3. **`create_buffer`**: A utility function that uses binary dilation to create a one-pixel buffer around the current release area.
4. **Animation**: The function can also return a series of frames representing the landslide's growth at each iteration, which can be used to create an animation of the retrogression process.

## 5. Utility Functions (`utils.py`)

The `utils.py` module contains a host of helper functions that are critical for the main analysis modules.

- **`get_hoydedata`**: Downloads DEM data from `hoydedata.no` for a given bounding box and resolution.
- **`get_msml_mask`**: Fetches marine clay (MSML) and "area under marine limit" (AUMG) polygons from NVE's GIS services.
- **`compute_slope`**: As described earlier, this is the fundamental function for calculating slope between sets of points.
- **`set_z_from_raster`**: Assigns elevation values to a set of (x, y) points by sampling them from a DEM raster.
- **`rasterize_shape`** and **`polygonize_results`**: Functions for converting between vector (shapes) and raster (arrays) formats.
- **`generate_plotly_profile`**: Creates a terrain profile plot from a line, which can be used for visualization.

## 6. Usage Examples

The `notebooks/test.ipynb` notebook provides clear examples of how to use the repository's functions.

### Example: Terrain Criteria

```python
from losneomrade import terrain_criteria

# Define calculation bounds and source line
xmin, xmax, ymin, ymax = 268463.9, 270007.6, 6651396.2, 6652564.4
source_line = gpd.GeoDataFrame(geometry=[LineString(...)], crs=25833)

# Run the analysis
tc = terrain_criteria.run_terrain_criteria(
    bounds=(xmin, xmax, ymin, ymax),
    source=source_line,
    source_depth=0.5,
    clip_to_msml=True,
    h_min=5
)

# Plot the results
tc.plot(column="slope", categorical=True, legend=True)
```

### Example: Retrogression

```python
from losneomrade import retrogression

# Use the same bounds and source line
retro, animation = retrogression.run_retrogression(
    bounds=(xmin, xmax, ymin, ymax),
    rel_shape=source_line,
    point_depth=0.5,
    clip_to_msml=True,
    min_slope=1/15,
    min_length=75,
    return_animation=True
)

# Plot the final release area
retro.plot()
```

## 7. Conclusion

The `losneomrade` repository is a powerful tool for performing preliminary assessments of quick-clay landslide hazards in Norway. It provides two robust, well-implemented methodologies that are grounded in established geotechnical principles. The code is well-structured, making good use of helper functions and established geospatial libraries. The inclusion of notebooks and tests makes it a valuable resource for both practical applications and further research.
