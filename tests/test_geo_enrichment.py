import json
import os
import tempfile
import unittest


from TutorDexAggregator import geo_enrichment as geo


class TestGeoEnrichment(unittest.TestCase):
    def setUp(self) -> None:
        self._old_region = os.environ.get("REGION_GEOJSON_PATH")
        self._old_mrt = os.environ.get("MRT_DATA_JSON_PATH")
        self._old_enabled = os.environ.get("GEO_ENRICHMENT_ENABLED")
        os.environ["GEO_ENRICHMENT_ENABLED"] = "1"

        self._tmpdir = tempfile.TemporaryDirectory()
        base = self._tmpdir.name

        region_path = os.path.join(base, "regions.geojson")
        mrt_path = os.path.join(base, "mrt.json")

        # Square polygon around (lon=103.0..104.0, lat=1.0..2.0) => Central (kml_5).
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"Name": "kml_5"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [103.0, 1.0],
                                [104.0, 1.0],
                                [104.0, 2.0],
                                [103.0, 2.0],
                                [103.0, 1.0],
                            ]
                        ],
                    },
                }
            ],
        }

        mrt = [
            {"name": "Station A", "address": "A", "latitude": 1.50, "longitude": 103.50, "line": "EW"},
            {"name": "Station B", "address": "B", "latitude": 1.90, "longitude": 103.90, "line": "NS"},
        ]

        with open(region_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f)
        with open(mrt_path, "w", encoding="utf-8") as f:
            json.dump(mrt, f)

        os.environ["REGION_GEOJSON_PATH"] = region_path
        os.environ["MRT_DATA_JSON_PATH"] = mrt_path

        geo._load_regions.cache_clear()
        geo._load_mrt_stations.cache_clear()

    def tearDown(self) -> None:
        if self._old_region is None:
            os.environ.pop("REGION_GEOJSON_PATH", None)
        else:
            os.environ["REGION_GEOJSON_PATH"] = self._old_region

        if self._old_mrt is None:
            os.environ.pop("MRT_DATA_JSON_PATH", None)
        else:
            os.environ["MRT_DATA_JSON_PATH"] = self._old_mrt

        if self._old_enabled is None:
            os.environ.pop("GEO_ENRICHMENT_ENABLED", None)
        else:
            os.environ["GEO_ENRICHMENT_ENABLED"] = self._old_enabled

        geo._load_regions.cache_clear()
        geo._load_mrt_stations.cache_clear()
        self._tmpdir.cleanup()

    def test_enrich_from_coords(self):
        res = geo.enrich_from_coords(lat=1.51, lon=103.49)
        self.assertEqual(res.region, "Central")
        self.assertEqual(res.nearest_mrt, "Station A")
        self.assertEqual(res.nearest_mrt_line, "EW")
        self.assertIsInstance(res.nearest_mrt_distance_m, int)
        self.assertTrue(res.meta.get("ok"))


if __name__ == "__main__":
    unittest.main()

