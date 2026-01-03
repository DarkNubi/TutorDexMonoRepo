# Geo Enrichment Data Files

This folder holds *local*, offline datasets used by server-side geo enrichment during persistence:

- `2019_region_boundary.geojson`
  - GeoJSON feature collection of Singapore region polygons (Central/East/North/North-East/West).
  - Expected to have `properties.Name` values like `kml_1..kml_5` (the code maps these to region names).

- `mrt_data.json`
  - JSON array of MRT stations with fields:
    - `name` (string)
    - `address` (string)
    - `latitude` (string/number)
    - `longitude` (string/number)
    - `line` (string)

These files are loaded by `TutorDexAggregator/geo_enrichment.py`.

Override paths (optional):
- `REGION_GEOJSON_PATH=/path/to/2019_region_boundary.geojson`
- `MRT_DATA_JSON_PATH=/path/to/mrt_data.json`

