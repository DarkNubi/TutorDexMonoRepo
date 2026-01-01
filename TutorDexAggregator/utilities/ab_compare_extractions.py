"""
A/B comparison utilities for `public.telegram_extractions`.

This script is designed to be:
- dependency-light (requests + stdlib)
- runnable as a standalone report generator
- importable by an experiment runner

It produces:
- `summary.json` with aggregate metrics
- `side_by_side.csv` with per-raw_id comparisons (field-by-field)
"""

from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import requests


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _supabase_cfg() -> Tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
    enabled = _truthy(os.environ.get("SUPABASE_ENABLED")) and bool(url and key)
    if not enabled:
        raise SystemExit("Supabase not enabled. Set SUPABASE_ENABLED=1, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.")
    return url, key


def _headers(key: str) -> Dict[str, str]:
    return {"apikey": key, "authorization": f"Bearer {key}", "content-type": "application/json"}


def _get_rows(url: str, key: str, table: str, query: str, *, timeout: int = 30) -> List[Dict[str, Any]]:
    resp = requests.get(f"{url}/rest/v1/{table}?{query}", headers=_headers(key), timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"get {table} failed status={resp.status_code} body={resp.text[:300]}")
    try:
        data = resp.json()
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _normalize_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


def _normalize_num(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        s = str(value).strip()
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _normalize_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        items = [str(x).strip() for x in value if str(x).strip()]
    else:
        s = str(value).strip()
        if not s:
            return None
        items = [s]
    if not items:
        return None
    # Stable compare: case-insensitive unique + sort
    dedup: Dict[str, str] = {}
    for it in items:
        k = it.strip().lower()
        if k and k not in dedup:
            dedup[k] = it.strip()
    return sorted(dedup.values(), key=lambda x: x.lower())


def _val_for_csv(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


FIELDS: List[Tuple[str, str]] = [
    # (field, type)
    ("assignment_code", "str"),
    ("is_tuition_centre", "bool"),
    ("subjects", "list"),
    ("level", "list"),
    ("specific_student_level", "list"),
    ("learning_mode", "list"),
    ("address", "list"),
    ("postal_code", "list"),
    ("postal_code_estimated", "list"),
    ("nearest_mrt", "list"),
    ("frequency", "str"),
    ("duration", "str"),
    ("hourly_rate", "str"),
    ("rate_min", "num"),
    ("rate_max", "num"),
    ("student_gender", "list"),
    ("tutor_gender", "list"),
]


def _normalize_field(field_type: str, value: Any) -> Any:
    if field_type == "str":
        return _normalize_str(value)
    if field_type == "num":
        return _normalize_num(value)
    if field_type == "list":
        return _normalize_list(value)
    if field_type == "bool":
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in {"1", "true", "yes", "y", "on"}:
            return True
        if s in {"0", "false", "no", "n", "off"}:
            return False
        return None
    return value


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    return True


@dataclass
class CompareConfig:
    pipeline_a: str
    pipeline_b: str
    since_iso: Optional[str] = None
    until_iso: Optional[str] = None
    channels: Optional[List[str]] = None
    limit_per_pipeline: int = 50000


def fetch_extractions_for_pipeline(cfg: CompareConfig, pipeline_version: str) -> List[Dict[str, Any]]:
    url, key = _supabase_cfg()
    select = "id,raw_id,channel_link,message_id,message_date,status,llm_model,canonical_json,error_json,meta,created_at"

    parts = [
        f"select={quote(select, safe=',')}",
        f"pipeline_version=eq.{quote(pipeline_version, safe='')}",
        "raw_id=not.is.null",
        f"limit={int(max(1, min(cfg.limit_per_pipeline, 200000)))}",
        "order=raw_id.asc",
    ]
    if cfg.since_iso:
        parts.append(f"message_date=gte.{quote(cfg.since_iso, safe='')}")
    if cfg.until_iso:
        parts.append(f"message_date=lt.{quote(cfg.until_iso, safe='')}")
    if cfg.channels:
        # channel_link=in.(...)
        items = ",".join(quote(str(c), safe="") for c in cfg.channels if str(c).strip())
        if items:
            parts.append(f"channel_link=in.({items})")

    q = "&".join(parts)
    return _get_rows(url, key, "telegram_extractions", q)


def compare_runs(cfg: CompareConfig) -> Dict[str, Any]:
    a_rows = fetch_extractions_for_pipeline(cfg, cfg.pipeline_a)
    b_rows = fetch_extractions_for_pipeline(cfg, cfg.pipeline_b)

    a_by_raw: Dict[str, Dict[str, Any]] = {str(r["raw_id"]): r for r in a_rows if r.get("raw_id") is not None}
    b_by_raw: Dict[str, Dict[str, Any]] = {str(r["raw_id"]): r for r in b_rows if r.get("raw_id") is not None}

    raw_ids_a = set(a_by_raw.keys())
    raw_ids_b = set(b_by_raw.keys())
    raw_ids_both = sorted(raw_ids_a & raw_ids_b, key=lambda x: int(x) if x.isdigit() else x)

    def _status_counts(rows: Iterable[Dict[str, Any]]) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for r in rows:
            s = str(r.get("status") or "unknown")
            out[s] = out.get(s, 0) + 1
        return out

    summary: Dict[str, Any] = {
        "pipelines": {"a": cfg.pipeline_a, "b": cfg.pipeline_b},
        "counts": {
            "a": {"total": len(a_by_raw), "by_status": _status_counts(a_by_raw.values())},
            "b": {"total": len(b_by_raw), "by_status": _status_counts(b_by_raw.values())},
            "intersection_raw_ids": len(raw_ids_both),
        },
        "field_metrics": {},
    }

    # Field-level metrics computed on intersection rows (and also on "both ok" subset).
    both_ok = []
    for rid in raw_ids_both:
        if str(a_by_raw[rid].get("status")) == "ok" and str(b_by_raw[rid].get("status")) == "ok":
            both_ok.append(rid)
    summary["counts"]["both_ok"] = len(both_ok)

    field_metrics: Dict[str, Any] = {}
    for field, field_type in FIELDS:
        present_a = 0
        present_b = 0
        match = 0
        denom = 0
        match_ok = 0
        denom_ok = 0

        for rid in raw_ids_both:
            a_json = (a_by_raw[rid].get("canonical_json") or {}) if isinstance(a_by_raw[rid].get("canonical_json"), dict) else {}
            b_json = (b_by_raw[rid].get("canonical_json") or {}) if isinstance(b_by_raw[rid].get("canonical_json"), dict) else {}

            va = _normalize_field(field_type, a_json.get(field))
            vb = _normalize_field(field_type, b_json.get(field))

            if _present(va):
                present_a += 1
            if _present(vb):
                present_b += 1
            denom += 1
            if va == vb:
                match += 1

            if rid in both_ok:
                denom_ok += 1
                if va == vb:
                    match_ok += 1

        field_metrics[field] = {
            "type": field_type,
            "coverage_a": (present_a / denom) if denom else None,
            "coverage_b": (present_b / denom) if denom else None,
            "match_rate_all": (match / denom) if denom else None,
            "match_rate_both_ok": (match_ok / denom_ok) if denom_ok else None,
        }

    summary["field_metrics"] = field_metrics
    return {
        "summary": summary,
        "a_by_raw": a_by_raw,
        "b_by_raw": b_by_raw,
        "raw_ids_both": raw_ids_both,
        "raw_ids_both_ok": both_ok,
    }


def write_reports(out_dir: Path, cfg: CompareConfig, result: Dict[str, Any]) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    csv_path = out_dir / "side_by_side.csv"
    a_by_raw: Dict[str, Dict[str, Any]] = result["a_by_raw"]
    b_by_raw: Dict[str, Dict[str, Any]] = result["b_by_raw"]
    raw_ids_both: List[str] = result["raw_ids_both"]

    base_cols = [
        "raw_id",
        "channel_link",
        "message_id",
        "status_a",
        "status_b",
        "llm_model_a",
        "llm_model_b",
        "prompt_sha_a",
        "prompt_sha_b",
        "examples_sha_a",
        "examples_sha_b",
    ]
    field_cols: List[str] = []
    for f, _t in FIELDS:
        field_cols.extend([f"{f}_a", f"{f}_b", f"{f}_eq"])
    cols = base_cols + field_cols

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for rid in raw_ids_both:
            ra = a_by_raw[rid]
            rb = b_by_raw[rid]

            meta_a = ra.get("meta") if isinstance(ra.get("meta"), dict) else {}
            meta_b = rb.get("meta") if isinstance(rb.get("meta"), dict) else {}
            prompt_a = meta_a.get("prompt") if isinstance(meta_a.get("prompt"), dict) else {}
            prompt_b = meta_b.get("prompt") if isinstance(meta_b.get("prompt"), dict) else {}
            ex_a = meta_a.get("examples") if isinstance(meta_a.get("examples"), dict) else {}
            ex_b = meta_b.get("examples") if isinstance(meta_b.get("examples"), dict) else {}

            a_json = ra.get("canonical_json") if isinstance(ra.get("canonical_json"), dict) else {}
            b_json = rb.get("canonical_json") if isinstance(rb.get("canonical_json"), dict) else {}

            row: Dict[str, Any] = {
                "raw_id": rid,
                "channel_link": _val_for_csv(ra.get("channel_link") or rb.get("channel_link")),
                "message_id": _val_for_csv(ra.get("message_id") or rb.get("message_id")),
                "status_a": _val_for_csv(ra.get("status")),
                "status_b": _val_for_csv(rb.get("status")),
                "llm_model_a": _val_for_csv(ra.get("llm_model")),
                "llm_model_b": _val_for_csv(rb.get("llm_model")),
                "prompt_sha_a": _val_for_csv(prompt_a.get("sha256")),
                "prompt_sha_b": _val_for_csv(prompt_b.get("sha256")),
                "examples_sha_a": _val_for_csv(ex_a.get("sha256")),
                "examples_sha_b": _val_for_csv(ex_b.get("sha256")),
            }

            for field, field_type in FIELDS:
                va = _normalize_field(field_type, a_json.get(field))
                vb = _normalize_field(field_type, b_json.get(field))
                row[f"{field}_a"] = _val_for_csv(va)
                row[f"{field}_b"] = _val_for_csv(vb)
                row[f"{field}_eq"] = "1" if va == vb else "0"

            w.writerow(row)

    return {"summary": str(summary_path), "csv": str(csv_path)}


def main() -> None:
    # Minimal "standalone" usage via env vars.
    # Prefer the experiment runner for a full workflow.
    pipeline_a = (os.environ.get("AB_PIPELINE_A") or "").strip()
    pipeline_b = (os.environ.get("AB_PIPELINE_B") or "").strip()
    if not pipeline_a or not pipeline_b:
        raise SystemExit("Set AB_PIPELINE_A and AB_PIPELINE_B to compare.")

    since = (os.environ.get("AB_SINCE_ISO") or "").strip() or None
    until = (os.environ.get("AB_UNTIL_ISO") or "").strip() or None
    out_dir = Path(os.environ.get("AB_OUT_DIR") or f"utilities/out/ab_compare_{int(time.time())}")

    cfg = CompareConfig(pipeline_a=pipeline_a, pipeline_b=pipeline_b, since_iso=since, until_iso=until)
    res = compare_runs(cfg)
    paths = write_reports(out_dir, cfg, res)
    print(f"Wrote: {paths['summary']}")
    print(f"Wrote: {paths['csv']}")


if __name__ == "__main__":
    main()

