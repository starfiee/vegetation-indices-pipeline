# Vegetation Indices Pipeline

Automated satellite-based vegetation indices pipeline using Google Earth Engine (GEE) and Sentinel-2 imagery. Computes NDVI, NDMI, and NDRE at pixel level for farm polygons and stores results in MySQL.

## What it does

- Fetches all clean Sentinel-2 images after the last stored date for each farm
- Checks cloud cover at field level using Cloud Score Plus (threshold: 25%)
- Computes NDVI, NDMI, NDRE from the same image
- Saves pixel-level data (lat, lng, value, class) to MySQL
- Saves summary stats (min, max, mean) per farm per date
- Generates PNG maps on demand (continuous or classification)

## Indices

| Index | Bands | Resolution | Description |
|-------|-------|------------|-------------|
| NDVI  | B8, B4 | 10m | Vegetation health |
| NDMI  | B8A, B11 | 20m | Moisture content |
| NDRE  | B8A, B5 | 20m | Chlorophyll / nutrient |

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/starfiee/vegetation-indices-pipeline.git
cd vegetation-indices-pipeline
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Authenticate with Google Earth Engine

```bash
earthengine authenticate
```

### 4. Create your .env file

```bash
cp .env.example .env
```

Fill in your values:
```
GEE_PROJECT_ID=your-gee-project-id
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=yourpassword
DB_NAME=vegetation_pipeline
```



### 5. Set up the database

Create the database in MySQL:

```sql
CREATE DATABASE vegetation_pipeline;
```

Then run the schema:

```sql
mysql -u root -p vegetation_pipeline < vegetation_pipeline/db/schema.sql
```

### 6. Run the pipeline

```bash
python cron_job.py
```

### 7. Generate PNG maps

```bash
python png_generator.py [field_id] [image_date] [index] [png_type]
```

Examples:

```bash
python png_generator.py 12362 2026-05-07 ndvi map
python png_generator.py 12362 2026-05-07 ndmi class
python png_generator.py 12362 2026-05-07 ndre all
```

PNG output goes to stdout. Redirect to a file:

```bash
python png_generator.py 12362 2026-05-07 ndvi map > ndvi_map.png
```

## Database tables

| Table | Description |
|-------|-------------|
| ndvi_pixels | Pixel-level NDVI values |
| ndvi_results | Summary stats per farm per date |
| ndmi_pixels | Pixel-level NDMI values |
| ndmi_results | Summary stats per farm per date |
| ndre_pixels | Pixel-level NDRE values |
| ndre_results | Summary stats per farm per date |

## Project structure
vegetation-indices-pipeline/

├── vegetation_pipeline/

│   └── db/

│       ├── connection.py     # Database connector

│       ├── schema.sql        # Table definitions

│       └── init.py

├── config/                   # Reserved for index config (coming soon)

├── cron_job.py               # Main pipeline runner

├── png_generator.py          # On-demand PNG generator

├── requirements.txt

├── .env.example

└── .gitignore

## License

MIT