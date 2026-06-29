"""
png_generator.py — Phase 3

Goal:
Read pixel data from database
Generate PNG on demand for any index
No permanent storage — called only when needed
PNG output goes to stdout — PHP streams to browser

Called by PHP :
python png_generator.py [field_id] [image_date] [index] [png_type]

index options:
  ndvi  = NDVI vegetation index
  ndmi  = NDMI moisture index
  ndre  = NDRE nutrient index

png_type options:
  map    = continuous color map
  class  = classification map
  all    = generate both map and class

Example:
python png_generator.py 12362 2026-05-07 ndvi map
python png_generator.py 12362 2026-05-07 ndmi class
python png_generator.py 12362 2026-05-07 ndre all

Color schemes match original R scripts exactly:
  NDVI map   : default terra plot colors
  NDVI class : 7 classes with terrain colors (R reclass_matrix)
  NDMI map   : light blue to dark blue
  NDMI class : 6 moisture classes light blue to dark blue
  NDRE map   : orange to dark red
  NDRE class : 6 nutrient classes orange to dark red
"""

import sys
import os
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Patch
import numpy as np
from dotenv import load_dotenv

load_dotenv()
from vegetation_pipeline.db.connection import get_connection

# ── Index Configuration ────────────────────────────────────
# All index-specific settings in one place
# Adding a new index = add one entry here only
# NDVI class PNG uses 7 classes matching R reclass_matrix:
#   -Inf,0.25,1 | 0.25,0.3,2 | 0.3,0.4,3 | 0.4,0.5,4
#    0.5,0.6,5  | 0.6,0.8,6  | 0.8,Inf,7
# NDMI and NDRE class PNGs use 6 classes matching R ndmi_breaks
# and ndre_breaks respectively.

INDEX_CONFIG = {
    'ndvi': {
        'table'    : 'ndvi_pixels',
        'value_col': 'ndvi_value',
        'class_col': 'ndvi_class',
        'label'    : 'NDVI',
        'cmap'     : 'RdYlGn',   
        'vmin'     : -1.0,
        'vmax'     :  1.0,

        # 7 classes matching R reclass_matrix for classification PNG
        'classes'  : [
            (-1.0,  0.25, '#F2F2A0', 'Very Low (<=0.25)'),
            ( 0.25, 0.30, '#D4C878', 'Low (0.25-0.30)'),
            ( 0.30, 0.40, '#A8C878', 'Low-Medium (0.30-0.40)'),
            ( 0.40, 0.50, '#78C878', 'Medium (0.40-0.50)'),
            ( 0.50, 0.60, '#50A050', 'Medium-High (0.50-0.60)'),
            ( 0.60, 0.80, '#287828', 'High (0.60-0.80)'),
            ( 0.80, 1.00, '#005000', 'Very High (>0.80)'),
        ]
    },

    'ndmi': {
        'table'    : 'ndmi_pixels',
        'value_col': 'ndmi_value',
        'class_col': 'ndmi_class',
        'label'    : 'NDMI',
        'cmap'     : 'Blues',    
        'vmin'     : -1.0,
        'vmax'     :  1.0,

        # 6 classes matching R ndmi_breaks and ndmi_labels
        'classes'  : [
            (-1.0, -0.3, '#8B0000', 'Severe Dry'),
            (-0.3, -0.1, '#FF4500', 'Critical Dry (Stress)'),
            (-0.1,  0.1, '#FFD700', 'Low Moisture'),
            ( 0.1,  0.3, '#ADD8E6', 'Moderate Moisture'),
            ( 0.3,  0.5, '#1E90FF', 'High Moisture'),
            ( 0.5,  1.0, '#00008B', 'Very High Moisture'),
        ]
    },

    'ndre': {
        'table'    : 'ndre_pixels',
        'value_col': 'ndre_value',
        'class_col': 'ndre_class',
        'label'    : 'NDRE',
        'cmap'     : 'YlOrRd',   
                                  
        'vmin'     : -1.0,
        'vmax'     :  1.0,

        # 6 classes matching R ndre_breaks and ndre_labels
        'classes'  : [
            (-1.0, -0.3, '#8B0000', 'Severe Nutrient Stress'),
            (-0.3, -0.1, '#FF4500', 'Critical Nutrient Stress'),
            (-0.1,  0.1, '#FFD700', 'Low Nutrient'),
            ( 0.1,  0.3, '#90EE90', 'Moderate Nutrient'),
            ( 0.3,  0.5, '#228B22', 'High Nutrient'),
            ( 0.5,  1.0, '#003300', 'Very High Nutrient'),
        ]
    }
}

# ── FUNCTION 1 — parse_arguments ──────────────────────────
def parse_arguments():
    """
    Reads 4 command line arguments from PHP.

    Args:
        args[0] = field_id   (int)
        args[1] = image_date (YYYY-MM-DD)
        args[2] = index      (ndvi / ndmi / ndre)
        args[3] = png_type   (map / class / all)

    Returns:
        field_id   (int)
        image_date (str)
        index      (str)
        png_type   (str)
    """
    args = sys.argv[1:]

    if len(args) < 4:
        raise Exception(
            "Usage: python png_generator.py "
            "[field_id] [image_date] [index] [png_type]"
        )

    field_id   = int(args[0])
    image_date = str(args[1])
    index      = str(args[2]).lower()
    png_type   = str(args[3]).lower()

    if index not in INDEX_CONFIG:
        raise Exception(
            f"Unknown index: {index}. Use ndvi, ndmi, or ndre"
        )

    if png_type not in ['map', 'class', 'all']:
        raise Exception(
            f"Unknown png_type: {png_type}. Use map, class, or all"
        )

    return field_id, image_date, index, png_type

# ── FUNCTION 2 — load_pixels_from_db ──────────────────────
def load_pixels_from_db(field_id, image_date, index):
    """
    Reads pixel data from the correct table based on index.
    Reconstructs 2D grid from flat database rows.

    This reverses what cron_runner.py does:
    cron_runner flattens 2D grid → saves as rows
    This function takes rows → rebuilds 2D grid

    Args:
        field_id   (int) : farm ID
        image_date (str) : date YYYY-MM-DD
        index      (str) : ndvi / ndmi / ndre

    Returns:
        band     (numpy 2D) : index values grid
        lat_grid (numpy 2D) : latitude per pixel
        lng_grid (numpy 2D) : longitude per pixel
        west, east, south, north (float) : bounding box
    """
    config    = INDEX_CONFIG[index]
    table     = config['table']
    value_col = config['value_col']

    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT pixel_row, pixel_col,
               latitude, longitude,
               {value_col}
        FROM {table}
        WHERE field_id   = %s
        AND   image_date = %s
        ORDER BY pixel_row, pixel_col
    """, (field_id, image_date))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        raise Exception(
            f"No {index.upper()} pixels found for "
            f"field {field_id} on {image_date}"
        )

    max_row  = max(r[0] for r in rows)
    max_col  = max(r[1] for r in rows)

    band     = np.full((max_row + 1, max_col + 1), np.nan)
    lat_grid = np.full((max_row + 1, max_col + 1), np.nan)
    lng_grid = np.full((max_row + 1, max_col + 1), np.nan)

    for pixel_row, pixel_col, lat, lng, val in rows:
        band    [pixel_row][pixel_col] = val
        lat_grid[pixel_row][pixel_col] = lat
        lng_grid[pixel_row][pixel_col] = lng

    west  = float(np.nanmin(lng_grid))
    east  = float(np.nanmax(lng_grid))
    south = float(np.nanmin(lat_grid))
    north = float(np.nanmax(lat_grid))

    print(f"Loaded {len(rows)} {index.upper()} pixels | "
          f"Grid: {max_row+1} x {max_col+1}", file=sys.stderr)

    return band, lat_grid, lng_grid, west, east, south, north

# ── FUNCTION 3 — load_polygon_from_db ─────────────────────
def load_polygon_from_db(field_id, image_date, index):
    """
    Gets boundary extent from pixel lat/lng.
    Used to draw polygon outline on PNG.

    Args:
        field_id   (int) : farm ID
        image_date (str) : date YYYY-MM-DD
        index      (str) : which table to read from

    Returns:
        poly_x (list) : longitude boundary points
        poly_y (list) : latitude boundary points
    """
    config = INDEX_CONFIG[index]
    table  = config['table']

    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT MIN(longitude), MAX(longitude),
               MIN(latitude),  MAX(latitude)
        FROM {table}
        WHERE field_id   = %s
        AND   image_date = %s
    """, (field_id, image_date))

    result = cursor.fetchone()
    cursor.close()
    conn.close()

    west, east, south, north = result

    poly_x = [west, east, east, west, west]
    poly_y = [north, north, south, south, north]

    return poly_x, poly_y

# ── FUNCTION 4 — output_png ───────────────────────────────
def output_png(fig, field_id, image_date, index, png_type):
    """
    Outputs PNG bytes to stdout so PHP can stream to browser.
    Nothing is saved to disk.

    PHP usage:
        header('Content-Type: image/png');
        passthru("python png_generator.py 12362 2026-05-07 ndvi map");

    Args:
        fig        : matplotlib figure object
        field_id   : farm ID (for logging)
        image_date : date string (for logging)
        index      : ndvi/ndmi/ndre (for logging)
        png_type   : map/class (for logging)
    """
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    sys.stdout.buffer.write(buf.read())
    plt.close(fig)

    print(f"PNG sent to stdout: {index.upper()} {png_type} "
          f"field {field_id} {image_date}", file=sys.stderr)

# ── FUNCTION 5 — generate_map_png ─────────────────────────
def generate_map_png(band, west, east, south, north,
                     poly_x, poly_y, field_id, image_date, index):
    """
    Generates continuous color map PNG for any index.

    Color schemes matching R scripts:
        NDVI : RdYlGn  (Red to Yellow to Green)
        NDMI : Blues   (Light Blue to Dark Blue)
               matches R: colorRampPalette(c("#ADD8E6","#00008B"))
        NDRE : YlOrRd  (Yellow to Orange to Dark Red)
               matches R: colorRampPalette(c("#FFA500","#8B0000"))

    Args:
        band                        : 2D numpy array of values
        west, east, south, north    : bounding box coordinates
        poly_x, poly_y              : polygon boundary points
        field_id, image_date, index : metadata for title/logging
    """
    config = INDEX_CONFIG[index]

    fig, ax     = plt.subplots(figsize=(7, 7))
    band_masked = np.ma.masked_invalid(band)
    cmap        = plt.cm.get_cmap(config['cmap']).copy()
    cmap.set_bad(color='white')

    im = ax.imshow(
        band_masked,
        cmap   = cmap,
        vmin   = config['vmin'],
        vmax   = config['vmax'],
        extent = [west, east, south, north],
        origin = 'upper'
    )

    ax.plot(poly_x, poly_y, color='red', linewidth=2)
    ax.set_title(
        f"{config['label']} — Field {field_id} — {image_date}"
    )
    plt.colorbar(im, ax=ax)

    output_png(fig, field_id, image_date, index, 'map')

# ── FUNCTION 6 — generate_class_png ───────────────────────
def generate_class_png(band, west, east, south, north,
                       poly_x, poly_y, field_id, image_date, index):
    """
    Generates classification PNG for any index.
    Class breaks and colors from INDEX_CONFIG.

    Matches R scripts:
        NDVI : 7 classes from R reclass_matrix
               terrain colors yellow to dark green
        NDMI : 6 classes from R ndmi_breaks/ndmi_labels
               light blue to dark blue tones
        NDRE : 6 classes from R ndre_breaks/ndre_labels
               orange to dark red tones

    Args:
        band                        : 2D numpy array of values
        west, east, south, north    : bounding box coordinates
        poly_x, poly_y              : polygon boundary points
        field_id, image_date, index : metadata for title/logging
    """
    config  = INDEX_CONFIG[index]
    classes = config['classes']

    class_grid = np.full(band.shape, np.nan, dtype=float)
    colors     = []
    labels     = []

    for i, (low, high, color, label) in enumerate(classes):
        mask = ~np.isnan(band) & (band >= low) & (band < high)
        class_grid[mask] = i
        colors.append(color)
        labels.append(label)

    class_masked = np.ma.masked_invalid(class_grid)
    cmap_class   = mcolors.ListedColormap(colors)
    cmap_class.set_bad(color='white')

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.imshow(
        class_masked,
        cmap   = cmap_class,
        vmin   = 0,
        vmax   = len(classes) - 1,
        extent = [west, east, south, north],
        origin = 'upper'
    )

    ax.plot(poly_x, poly_y, color='red', linewidth=2)
    ax.set_title(
        f"{config['label']} Classification — "
        f"Field {field_id} — {image_date}"
    )

    legend_elements = [
        Patch(facecolor=color, label=label)
        for _, _, color, label in classes
    ]
    ax.legend(
        handles    = legend_elements,
        loc        = 'upper left',
        fontsize   = 6,
        framealpha = 0.8
    )

    output_png(fig, field_id, image_date, index, 'class')

# ── MAIN ───────────────────────────────────────────────────
if __name__ == "__main__":

    field_id, image_date, index, png_type = parse_arguments()

    print(f"Generating {index.upper()} {png_type} PNG "
          f"for field {field_id} on {image_date}", file=sys.stderr)

    band, lat_grid, lng_grid, west, east, south, north = \
        load_pixels_from_db(field_id, image_date, index)

    poly_x, poly_y = \
        load_polygon_from_db(field_id, image_date, index)

    if png_type == 'map' or png_type == 'all':
        generate_map_png(
            band, west, east, south, north,
            poly_x, poly_y, field_id, image_date, index
        )

    if png_type == 'class' or png_type == 'all':
        generate_class_png(
            band, west, east, south, north,
            poly_x, poly_y, field_id, image_date, index
        )

    print("Done", file=sys.stderr)