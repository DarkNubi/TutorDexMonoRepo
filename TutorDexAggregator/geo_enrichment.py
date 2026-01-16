from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from shared.config import load_aggregator_config

logger = logging.getLogger("geo_enrichment")


def _env_flag(name: str) -> Optional[bool]:
    raw = os.environ.get(name)
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return None

def _enabled() -> bool:
    override = _env_flag("GEO_ENRICHMENT_ENABLED")
    if override is not None:
        return bool(override)
    return bool(load_aggregator_config().geo_enrichment_enabled)


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parent / "data"


def _region_geojson_path() -> Path:
    p = str(os.environ.get("REGION_GEOJSON_PATH") or "").strip()
    if not p:
        p = str(load_aggregator_config().region_geojson_path or "").strip()
    return Path(p) if p else (_default_data_dir() / "2019_region_boundary.geojson")


def _mrt_data_path() -> Path:
    p = str(os.environ.get("MRT_DATA_JSON_PATH") or "").strip()
    if not p:
        p = str(load_aggregator_config().mrt_data_json_path or "").strip()
    return Path(p) if p else (_default_data_dir() / "mrt_data.json")


def _safe_float(x: Any) -> Optional[float]:
    try:
        f = float(x)
    except Exception:
        return None
    if not math.isfinite(f):
        return None
    return f


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Returns meters.
    r = 6378137.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(dlmb / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))
    return r * c


# --------------------------
# Region lookup (GeoJSON)
# --------------------------

def _point_in_ring(lon: float, lat: float, ring: List[List[float]]) -> bool:
    # Ray casting algorithm. Ring is list of [lon, lat] points.
    inside = False
    n = len(ring)
    if n < 4:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        # Check if edge crosses horizontal ray.
        intersects = ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi)
        if intersects:
            inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, polygon: List[List[List[float]]]) -> bool:
    # polygon = [outer_ring, hole_ring1, ...]
    if not polygon:
        return False
    outer = polygon[0]
    if not _point_in_ring(lon, lat, outer):
        return False
    for hole in polygon[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


def _iter_polygons(geometry: Dict[str, Any]) -> Iterable[List[List[List[float]]]]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon" and isinstance(coords, list):
        # coords: [ring, ring, ...]
        poly: List[List[List[float]]] = []
        for ring in coords:
            if isinstance(ring, list):
                pts: List[List[float]] = []
                for p in ring:
                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                        lon = _safe_float(p[0])
                        lat = _safe_float(p[1])
                        if lon is None or lat is None:
                            continue
                        pts.append([lon, lat])
                if pts:
                    poly.append(pts)
        if poly:
            yield poly
        return
    if gtype == "MultiPolygon" and isinstance(coords, list):
        for poly_coords in coords:
            if not isinstance(poly_coords, list):
                continue
            poly2: List[List[List[float]]] = []
            for ring in poly_coords:
                if isinstance(ring, list):
                    pts2: List[List[float]] = []
                    for p in ring:
                        if isinstance(p, (list, tuple)) and len(p) >= 2:
                            lon = _safe_float(p[0])
                            lat = _safe_float(p[1])
                            if lon is None or lat is None:
                                continue
                            pts2.append([lon, lat])
                    if pts2:
                        poly2.append(pts2)
            if poly2:
                yield poly2
        return


def _kml_name_to_region(name: str) -> Optional[str]:
    key = str(name or "").strip()
    mapping = {
        "kml_5": "Central",
        "kml_4": "East",
        "kml_3": "North-East",
        "kml_2": "North",
        "kml_1": "West",
    }
    return mapping.get(key)


@lru_cache(maxsize=1)
def _load_regions() -> Tuple[Optional[List[Tuple[str, List[List[List[List[float]]]]]]], Optional[str]]:
    path = _region_geojson_path()
    if not path.exists():
        return None, f"missing_region_geojson:{path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"region_geojson_read_error:{e}"
    feats = data.get("features") if isinstance(data, dict) else None
    if not isinstance(feats, list) or not feats:
        return None, "region_geojson_no_features"

    out: List[Tuple[str, List[List[List[List[float]]]]]] = []
    for f in feats:
        if not isinstance(f, dict):
            continue
        props = f.get("properties") if isinstance(f.get("properties"), dict) else {}
        raw_name = props.get("Name") or props.get("name") or props.get("NAME")
        region = _kml_name_to_region(str(raw_name or "").strip())
        if not region:
            continue
        geom = f.get("geometry") if isinstance(f.get("geometry"), dict) else None
        if not geom:
            continue
        polys = list(_iter_polygons(geom))
        if not polys:
            continue
        out.append((region, polys))

    if not out:
        return None, "region_geojson_no_supported_polygons"
    return out, None


def lookup_region(*, lat: float, lon: float) -> Tuple[Optional[str], Optional[str]]:
    regions, err = _load_regions()
    if err or not regions:
        return None, err
    for region, polys in regions:
        for poly in polys:
            if _point_in_polygon(float(lon), float(lat), poly):
                return region, None
    return None, "region_not_found"


# --------------------------
# Nearest MRT lookup (static JSON)
# --------------------------

@lru_cache(maxsize=1)
def _load_mrt_stations() -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    path = _mrt_data_path()
    if not path.exists():
        return None, f"missing_mrt_data:{path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"mrt_data_read_error:{e}"
    if not isinstance(data, list) or not data:
        return None, "mrt_data_empty"
    out: List[Dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        lat = _safe_float(row.get("latitude"))
        lon = _safe_float(row.get("longitude"))
        if not name or lat is None or lon is None:
            continue
        out.append(
            {
                "name": name,
                "address": str(row.get("address") or "").strip() or None,
                "line": str(row.get("line") or "").strip() or None,
                "latitude": lat,
                "longitude": lon,
            }
        )
    if not out:
        return None, "mrt_data_no_valid_rows"
    return out, None


def lookup_nearest_mrt(*, lat: float, lon: float) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    stations, err = _load_mrt_stations()
    if err or not stations:
        return None, err
    best: Optional[Dict[str, Any]] = None
    best_d = float("inf")
    for s in stations:
        d = _haversine_m(float(lat), float(lon), float(s["latitude"]), float(s["longitude"]))
        if d < best_d:
            best_d = d
            best = s
    if not best or not math.isfinite(best_d):
        return None, "mrt_not_found"
    out = dict(best)
    out["distance_m"] = int(round(best_d))
    return out, None


@dataclass(frozen=True)
class GeoEnrichmentResult:
    region: Optional[str]
    nearest_mrt: Optional[str]
    nearest_mrt_line: Optional[str]
    nearest_mrt_distance_m: Optional[int]
    meta: Dict[str, Any]


def enrich_from_coords(*, lat: Any, lon: Any) -> GeoEnrichmentResult:
    """
    Computes:
    - region (from local GeoJSON polygon lookup)
    - nearest MRT (from local station dataset + Haversine)

    Purely offline once the data files exist; safe to call in the persistence path.
    """
    if not _enabled():
        return GeoEnrichmentResult(
            region=None,
            nearest_mrt=None,
            nearest_mrt_line=None,
            nearest_mrt_distance_m=None,
            meta={"ok": True, "skipped": "disabled"},
        )

    lat_f = _safe_float(lat)
    lon_f = _safe_float(lon)
    if lat_f is None or lon_f is None:
        return GeoEnrichmentResult(
            region=None,
            nearest_mrt=None,
            nearest_mrt_line=None,
            nearest_mrt_distance_m=None,
            meta={"ok": True, "skipped": "missing_coords"},
        )

    region, region_err = lookup_region(lat=lat_f, lon=lon_f)
    mrt, mrt_err = lookup_nearest_mrt(lat=lat_f, lon=lon_f)

    return GeoEnrichmentResult(
        region=region,
        nearest_mrt=(mrt or {}).get("name") if isinstance(mrt, dict) else None,
        nearest_mrt_line=(mrt or {}).get("line") if isinstance(mrt, dict) else None,
        nearest_mrt_distance_m=(mrt or {}).get("distance_m") if isinstance(mrt, dict) else None,
        meta={
            "ok": True,
            "region_error": region_err,
            "mrt_error": mrt_err,
            "region_geojson_path": str(_region_geojson_path()),
            "mrt_data_path": str(_mrt_data_path()),
        },
    )
