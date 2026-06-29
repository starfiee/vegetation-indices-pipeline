"""
cron_runner.py — Phase 3

What this script does:
    Runs automatically  via cron job
    Loops through all active farms in database
    For each farm finds last stored date across
    all three indices (NDVI, NDMI, NDRE)
    Fetches ALL clean Sentinel-2 images after that date
    Computes NDVI, NDMI, NDRE from same image
    Saves pixel data to ndvi_pixels, ndmi_pixels, ndre_pixels

When it runs:
    Triggered by cron scheduler 
    Runs at night: 0 2 * * * python cron_runner.py

What it does NOT do:
    Does NOT accept input from PHP
    Does NOT generate PNG maps
    Does NOT have timeout concern

Databases:
    sawie_ndvi : our pixel tables (local testing)
"""

import sys
import os
import json
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv
from rasterio.transform import from_bounds
from shapely.geometry import Polygon
import ee

load_dotenv() # function used to read secret keys and configuration settings from a local .env 
from vegetation_pipeline.db.connection import get_connection
ee.Initialize(project=os.getenv('GEE_PROJECT_ID'))


# ── FUNCTION 1 — Log ───────────────────────────────────────
def log(msg, farm_id=None):
    """
    Prints timestamped log message.
    farm_id is optional — adds farm context to log line.
    sys.stdout.flush() forces immediate output
    so logs appear in real time not in batches.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if farm_id:
        print(f"[{timestamp}] Farm {farm_id}: {msg}")
    else:
        print(f"[{timestamp}] {msg}")
    sys.stdout.flush()

# ── FUNCTION 2 — Get Last Stored Date ─────────────────────
def get_last_stored_date(farm_id):
    """
    Checks ndvi_results, ndmi_results, ndre_results
    for last stored image_date for this farm.

    Returns OLDEST date among all three so no
    index falls behind the others.

    Returns:
        str  : oldest date as 'YYYY-MM-DD'
        None : if no data exists for this farm
    """
    conn   = get_connection()
    cursor = conn.cursor()

    dates  = []
    tables = ['ndvi_results', 'ndmi_results', 'ndre_results']

    for table in tables:
        try:
            cursor.execute(f"""
                SELECT MAX(image_date)
                FROM {table}
                WHERE field_id = %s
            """, (farm_id,))
            result = cursor.fetchone()
            if result[0] is not None:
                dates.append(result[0])
        except Exception:
            continue

    cursor.close()
    conn.close()

    if not dates:
        return None
    return str(min(dates))

# ── FUNCTION 3 — Build Polygon ────────────────────────────
def build_polygon(lat_values, lng_values):
    """
    Builds Shapely polygon from lat/lng lists.
    lng comes first in zip because Shapely uses (x, y)
    which is (longitude, latitude).
    """
    coords  = list(zip(lng_values, lat_values))
    polygon = Polygon(coords)
    return polygon

# ── FUNCTION 4 — Fetch All Clean Images ───────────────────
def fetch_all_clean_images(polygon, search_from):
    """
    Searches GEE for ALL clean Sentinel-2 images
    from search_from to today for this polygon.

    Cloud check is at FIELD level not tile level.
    Uses Cloud Score Plus cs_cdf band.
    Threshold: field average cloud probability < 25%

    Unlike data_collector.py which returns ONE image,
    this returns ALL clean images found (oldest first).

    Returns:
        list of dicts with image, image_date,
        cloud_prob, cloud_prob_array, gee_polygon
    """
    coords      = list(polygon.exterior.coords)
    gee_polygon = ee.Geometry.Polygon(coords)
    today       = datetime.now().strftime('%Y-%m-%d')

    collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
        .filterBounds(gee_polygon) \
        .filterDate(search_from, today) \
        .sort('system:time_start', True)

    total = collection.size().getInfo()
    log(f"Found {total} total images from {search_from} to {today}")

    if total == 0:
        return []

    image_list   = collection.toList(total)
    clean_images = []

    for i in range(total):
        candidate      = ee.Image(image_list.get(i))
        candidate_date = candidate.date().format('YYYY-MM-dd').getInfo()

        try:
            cs_plus = ee.ImageCollection(
                'GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED') \
                .filterBounds(gee_polygon) \
                .filterDate(
                    candidate_date,
                    (datetime.strptime(candidate_date, '%Y-%m-%d')
                    + timedelta(days=1)).strftime('%Y-%m-%d')
                ).first()

            cloud_score      = cs_plus.select('cs_cdf')
            cloud_result     = cloud_score.sampleRectangle(region=gee_polygon)
            cs_values        = cloud_result.getInfo()['properties']['cs_cdf']
            cloud_prob_array = 1 - np.array(cs_values)
            field_cloud_prob = float(np.mean(cloud_prob_array))

            if field_cloud_prob < 0.25:
                log(f"Clean: {candidate_date} | Cloud: {field_cloud_prob*100:.1f}%")
                clean_images.append({
                    'image'            : candidate,
                    'image_date'       : candidate_date,
                    'cloud_prob'       : field_cloud_prob,
                    'cloud_prob_array' : cloud_prob_array,
                    'gee_polygon'      : gee_polygon
                })
            else:
                log(f"Cloudy: {candidate_date} | Cloud: {field_cloud_prob*100:.1f}% — skip")

        except Exception as e:
            log(f"Error checking {candidate_date}: {e}")
            continue

    log(f"{len(clean_images)} clean images found")
    return clean_images

# ── FUNCTION 5 — Classify NDVI ────────────────────────────
def classify_ndvi(value):
    if value <= 0.2:  return "Water"
    if value <= 0.3:  return "Builtup Area"
    if value <= 0.4:  return "Barren Land"
    if value <= 0.5:  return "Agri Barren Land"
    if value <= 0.6:  return "Clouds"
    if value <= 0.7:  return "Sparse vegetation"
    if value <= 0.8:  return "Low vegetation"
    if value <= 0.9:  return "Moderate healthy vegetation"
    if value <= 0.95: return "High vegetation"
    return "Extremely High vegetation"

# ── FUNCTION 6 — Classify NDMI ────────────────────────────
def classify_ndmi(value):
    if value <= -0.3: return "Severe Dry"
    if value <= -0.1: return "Critical Dry"
    if value <= 0.1:  return "Low Moisture"
    if value <= 0.3:  return "Moderate Moisture"
    if value <= 0.5:  return "High Moisture"
    return "Very High Moisture"

# ── FUNCTION 7 — Classify NDRE ────────────────────────────
def classify_ndre(value):
    if value <= -0.3: return "Severe Nutrient Stress"
    if value <= -0.1: return "Critical Nutrient Stress"
    if value <= 0.1:  return "Low Nutrient"
    if value <= 0.3:  return "Moderate Nutrient"
    if value <= 0.5:  return "High Nutrient"
    return "Very High Nutrient"

# ── FUNCTION 8 — Calculate Pixel Coordinates ──────────────
def calculate_pixel_coordinates(row, col, transform):
    """
    Converts pixel grid row/col to real GPS lat/lng.
    Uses Affine transform from rasterio.from_bounds.
    """
    pixel_width  = abs(transform[0])
    pixel_height = abs(transform[4])
    west         = transform[2]
    north        = transform[5]
    lng = west  + (col + 0.5) * pixel_width
    lat = north - (row + 0.5) * pixel_height
    return round(lat, 6), round(lng, 6)

# ── FUNCTION 9 — Save Pixels ──────────────────────────────
def save_pixels(farm_id, image_date, values,
                cloud_prob_array, transform,
                table, value_col, class_col, classify_fn):
    """
    Generic pixel saver — works for NDVI, NDMI, NDRE.
    Same logic, different table and column names.

    Filters out pixels with value <= -2
    (sentinel value for outside-polygon pixels)

    Uses INSERT IGNORE for idempotency —
    running twice does not create duplicates.
    """
    conn   = get_connection()
    cursor = conn.cursor()

    pixel_rows = []
    rows       = len(values)
    cols       = len(values[0])

    for r in range(rows):
        for c in range(cols):
            val = values[r][c]
            if val is None or float(val) <= -2:
                continue

            val        = float(val)
            cloud_prob = float(cloud_prob_array[r][c]) \
                         if r < cloud_prob_array.shape[0] \
                         and c < cloud_prob_array.shape[1] else None
            lat, lng   = calculate_pixel_coordinates(r, c, transform)
            cls        = classify_fn(val)

            pixel_rows.append((
                farm_id, image_date,
                r, c, lat, lng,
                val, cloud_prob, cls
            ))

    if pixel_rows:
        cursor.executemany(f"""
            INSERT IGNORE INTO {table}
            (field_id, image_date,
             pixel_row, pixel_col,
             latitude, longitude,
             {value_col}, cloud_prob, {class_col})
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, pixel_rows)
        log(f"Saved {len(pixel_rows)} pixels to {table}")

    conn.commit()
    cursor.close()
    conn.close()


def save_results(farm_id, image_date, values,
                 cloud_prob, table, min_col, max_col, mean_col):
    """
    Saves summary statistics to results table.
    One row per farm per date per index.

    Args:
        farm_id    : farm ID
        image_date : date string
        values     : 2D list of index values
        cloud_prob : average cloud probability
        table      : results table name
        min_col    : column name for minimum value
        max_col    : column name for maximum value
        mean_col   : column name for mean value
    """
    arr   = np.array(values, dtype=float)
    flat  = arr.flatten()
    flat[flat <= -2] = np.nan
    valid = flat[~np.isnan(flat)]

    if len(valid) == 0:
        log(f"No valid pixels for {table} — skipping results")
        return

    val_min  = float(np.min(valid))
    val_max  = float(np.max(valid))
    val_mean = float(np.mean(valid))

    conn   = get_connection()
    cursor = conn.cursor()

    cursor.execute(f"""
        INSERT IGNORE INTO {table}
        (field_id, image_date,
         {min_col}, {max_col}, {mean_col},
         cloud_prob, total_pixels, valid_pixels, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        farm_id, image_date,
        val_min, val_max, val_mean,
        cloud_prob,
        len(valid), len(valid),  
        'clean'
    ))

    conn.commit()
    cursor.close()
    conn.close()

    log(f"Saved summary to {table} — mean: {val_mean:.4f}")
# ── FUNCTION 10 — Process One Image ───────────────────────
def process_one_image(farm_id, polygon, image_data):
    """
    Fetches NDVI, NDMI, NDRE from one GEE image.
    All three indices from same image = same date,
    same cloud check, same polygon masking.

    NDVI uses B8 + B4 at native 10m resolution
    NDMI uses B8A + B11 at 20m resolution
    NDRE uses B8A + B5  at 20m resolution
    """
    image            = image_data['image']
    image_date       = image_data['image_date']
    cloud_prob_array = image_data['cloud_prob_array']
    gee_polygon      = image_data['gee_polygon']
    west, south, east, north = polygon.bounds

    # NDVI — B8, B4 at 10m
    ndvi        = image.normalizedDifference(['B8', 'B4'])
    ndvi_masked = ndvi.updateMask(
                    ee.Image.constant(1).clip(gee_polygon)
                  ).unmask(-2)
    ndvi_values = ndvi_masked.sampleRectangle(
                    region=gee_polygon
                  ).getInfo()['properties']['nd']
    h, w        = len(ndvi_values), len(ndvi_values[0])
    transform   = from_bounds(west, south, east, north, w, h)

    # NDMI — B8A, B11 at 20m
    ndmi        = image.normalizedDifference(['B8A', 'B11'])
    ndmi_masked = ndmi.updateMask(
                    ee.Image.constant(1).clip(gee_polygon)
                  ).unmask(-2)
    ndmi_values = ndmi_masked.sampleRectangle(
                    region=gee_polygon
                  ).getInfo()['properties']['nd']
    mh, mw      = len(ndmi_values), len(ndmi_values[0])
    ndmi_tf     = from_bounds(west, south, east, north, mw, mh)

    # NDRE — B8A, B5 at 20m
    ndre        = image.normalizedDifference(['B8A', 'B5'])
    ndre_masked = ndre.updateMask(
                    ee.Image.constant(1).clip(gee_polygon)
                  ).unmask(-2)
    ndre_values = ndre_masked.sampleRectangle(
                    region=gee_polygon
                  ).getInfo()['properties']['nd']
    rh, rw      = len(ndre_values), len(ndre_values[0])
    ndre_tf     = from_bounds(west, south, east, north, rw, rh)

    # Save all three
    save_pixels(farm_id, image_date,
                ndvi_values, cloud_prob_array, transform,
                'ndvi_pixels', 'ndvi_value', 'ndvi_class',
                classify_ndvi)

    save_pixels(farm_id, image_date,
                ndmi_values, cloud_prob_array, ndmi_tf,
                'ndmi_pixels', 'ndmi_value', 'ndmi_class',
                classify_ndmi)

    save_pixels(farm_id, image_date,
                ndre_values, cloud_prob_array, ndre_tf,
                'ndre_pixels', 'ndre_value', 'ndre_class',
                classify_ndre)
    # Save summary stats to results tables
    save_results(farm_id, image_date,
                 ndvi_values, image_data['cloud_prob'],
                 'ndvi_results', 'ndvi_min', 'ndvi_max', 'ndvi_mean')

    save_results(farm_id, image_date,
                 ndmi_values, image_data['cloud_prob'],
                 'ndmi_results', 'ndmi_min', 'ndmi_max', 'ndmi_mean')

    save_results(farm_id, image_date,
                 ndre_values, image_data['cloud_prob'],
                 'ndre_results', 'ndre_min', 'ndre_max', 'ndre_mean')
    log(f"Saved NDVI + NDMI + NDRE for {image_date}", farm_id)

# ── MAIN ───────────────────────────────────────────────────
if __name__ == "__main__":

    log("=" * 50)
    log("CRON RUNNER STARTED — TEST MODE")
    log("=" * 50)

    # Hardcoded test farm
    # In production replace with get_active_farms()
    farm_id    = 12362
    lat_values = [
        31.181412, 31.181004, 31.180714, 31.180635,
        31.180370, 31.180285, 31.180252, 31.179164,
        31.179100, 31.179600, 31.179972, 31.179927,
        31.180291, 31.180273
    ]
    lng_values = [
        70.872642, 70.871164, 70.871153, 70.869695,
        70.869708, 70.868820, 70.868386, 70.868454,
        70.869017, 70.871185, 70.871865, 70.872600,
        70.872497, 70.872891
    ]

    polygon   = build_polygon(lat_values, lng_values)
    last_date = get_last_stored_date(farm_id)

    if last_date:
        search_from = (
            datetime.strptime(last_date, '%Y-%m-%d')
            + timedelta(days=1)
        ).strftime('%Y-%m-%d')
        log(f"Last stored date: {last_date} → searching from {search_from}", farm_id)
    else:
        search_from = '2026-05-06'
        log(f"No history found → using test start date: {search_from}", farm_id)

    clean_images = fetch_all_clean_images(polygon, search_from)

    if not clean_images:
        log("No clean images found — nothing to do")
    else:
        for image_data in clean_images:
            try:
                process_one_image(farm_id, polygon, image_data)
            except Exception as e:
                log(f"Error on {image_data['image_date']}: {e}", farm_id)
                continue

    log("=" * 50)
    log("CRON RUNNER TEST COMPLETED")
    log("=" * 50)