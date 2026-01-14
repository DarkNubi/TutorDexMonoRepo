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
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import requests

from shared.config import load_aggregator_config

AGG_DIR = Path(__file__).resolve().parents[1]
if str(AGG_DIR) not in sys.path:
    sys.path.insert(0, str(AGG_DIR))

from supabase_env import resolve_supabase_url  # noqa: E402

try:
    from support_checks import has_remarks_marker, rate_is_quote_like, substring_supported  # type: ignore
except Exception:
    has_remarks_marker = None  # type: ignore
    rate_is_quote_like = None  # type: ignore
    substring_supported = None  # type: ignore


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _supabase_cfg() -> Tuple[str, str]:
    cfg = load_aggregator_config()
    url = resolve_supabase_url()
    key = str(cfg.supabase_auth_key or "").strip()
    enabled = bool(cfg.supabase_enabled) and bool(url and key)
    if not enabled:
        raise SystemExit(
            "Supabase not enabled. Set SUPABASE_ENABLED=1, SUPABASE_SERVICE_ROLE_KEY, and one of SUPABASE_URL_HOST / SUPABASE_URL_DOCKER / SUPABASE_URL."
        )
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
    ("academic_display_text", "str"),
    ("learning_mode.mode", "str"),
    ("learning_mode.raw_text", "str"),
    ("address", "list"),
    ("postal_code", "list"),
    ("nearest_mrt", "list"),
    ("lesson_schedule", "list"),
    ("start_date", "str"),
    ("time_availability.note", "str"),
    ("time_availability.explicit", "json"),
    ("time_availability.estimated", "json"),
    ("rate.min", "num"),
    ("rate.max", "num"),
    ("rate.raw_text", "str"),
    ("additional_remarks", "str"),
]


def _get_path(obj: Any, path: str) -> Any:
    cur: Any = obj
    for part in str(path).split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _normalize_field(field_type: str, value: Any) -> Any:
    if field_type == "str":
        return _normalize_str(value)
    if field_type == "num":
        return _normalize_num(value)
    if field_type == "list":
        return _normalize_list(value)
    if field_type == "json":
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return _normalize_str(value)
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

            va = _normalize_field(field_type, _get_path(a_json, field))
            vb = _normalize_field(field_type, _get_path(b_json, field))

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

    # Optional deeper metrics that require joining raw_text from `telegram_messages_raw`.
    # Enable with `AB_EXTRA_METRICS=1`.
    if _truthy(str(load_aggregator_config().ab_extra_metrics or "").strip()):
        url, key = _supabase_cfg()

        def _chunks(xs: List[str], n: int) -> Iterable[List[str]]:
            for i in range(0, len(xs), max(1, n)):
                yield xs[i : i + n]

        def _fetch_raw_text_map(raw_ids: List[str]) -> Dict[str, str]:
            out: Dict[str, str] = {}
            for chunk in _chunks(raw_ids, 150):
                items = ",".join(quote(str(rid), safe="") for rid in chunk if str(rid).strip())
                if not items:
                    continue
                q = f"select=id,raw_text&id=in.({items})"
                rows = _get_rows(url, key, "telegram_messages_raw", q, timeout=30)
                for r in rows:
                    rid = r.get("id")
                    if rid is None:
                        continue
                    out[str(rid)] = str(r.get("raw_text") or "")
            return out

        raw_text_by_id = _fetch_raw_text_map(raw_ids_both)

        TIME_RE = re.compile(r"^\\d{2}:\\d{2}-\\d{2}:\\d{2}$")

        def _valid_time_slot(s: Any) -> bool:
            if not isinstance(s, str):
                return False
            t = s.strip().replace("–", "-").replace("—", "-").replace("−", "-").replace("‒", "-")
            t = re.sub(r"\\s*-\\s*", "-", t)
            if not TIME_RE.match(t):
                return False
            try:
                start, end = t.split("-", 1)
                sh, sm = start.split(":")
                eh, em = end.split(":")
                sh_i, sm_i, eh_i, em_i = int(sh), int(sm), int(eh), int(em)
                if not (0 <= sh_i <= 23 and 0 <= eh_i <= 23 and 0 <= sm_i <= 59 and 0 <= em_i <= 59):
                    return False
                if (sh_i, sm_i) > (eh_i, em_i):
                    return False
                return True
            except Exception:
                return False

        def _extract_rate(parsed: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
            rate = parsed.get("rate")
            if not isinstance(rate, dict):
                return None, None, None
            raw = rate.get("raw_text")
            raw_s = str(raw).strip() if isinstance(raw, str) and str(raw).strip() else None

            def _num(v: Any) -> Optional[float]:
                if v is None:
                    return None
                if isinstance(v, (int, float)):
                    return float(v)
                try:
                    sv = str(v).strip()
                    if re.fullmatch(r"-?\\d+(?:\\.\\d+)?", sv):
                        return float(sv)
                except Exception:
                    return None
                return None

            return _num(rate.get("min")), _num(rate.get("max")), raw_s

        def _extra_metrics_for_pipeline(rows_by_raw: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
            ok_rows = [r for r in rows_by_raw.values() if str(r.get("status")) == "ok" and r.get("raw_id") is not None]

            time_total = 0
            time_invalid = 0
            time_structure_errors = 0
            time_non_empty_rows = 0
            time_note_present_rows = 0

            quote_cases = 0
            quote_minmax_nonnull = 0

            remarks_nonnull = 0
            remarks_no_marker = 0
            remarks_not_substring = 0

            signals_ok = 0
            signals_subjects_nonempty = 0
            signals_academic_requests_nonnull = 0
            signals_ambiguous = 0
            signals_display_mismatch = 0

            by_channel: Dict[str, Dict[str, int]] = {}

            display_academic_hint_re = re.compile(r"(?i)\b(p\\s*\\d|pri\\b|primary\\b|sec\\b|s\\s*\\d|secondary\\b|jc\\b|j\\s*\\d|ib\\b|igcse\\b)\\b")

            for r in ok_rows:
                rid = str(r.get("raw_id"))
                parsed = r.get("canonical_json") if isinstance(r.get("canonical_json"), dict) else {}
                raw_text = raw_text_by_id.get(rid, "")
                channel = str(r.get("channel_link") or "unknown")

                ta = parsed.get("time_availability") if isinstance(parsed.get("time_availability"), dict) else None
                if not ta:
                    time_structure_errors += 1
                else:
                    # Row-level time coverage.
                    has_any = False
                    for section in ("explicit", "estimated"):
                        day_map = ta.get(section) if isinstance(ta.get(section), dict) else {}
                        for slots in day_map.values():
                            if isinstance(slots, list) and any(isinstance(x, str) and str(x).strip() for x in slots):
                                has_any = True
                                break
                        if has_any:
                            break
                    if has_any:
                        time_non_empty_rows += 1
                    note_s = str(ta.get("note") or "").strip() if isinstance(ta.get("note"), (str, type(None))) else ""
                    if note_s:
                        time_note_present_rows += 1

                    for section in ("explicit", "estimated"):
                        day_map = ta.get(section) if isinstance(ta.get(section), dict) else None
                        if not day_map:
                            time_structure_errors += 1
                            continue
                        for slots in day_map.values():
                            if not isinstance(slots, list):
                                time_structure_errors += 1
                                continue
                            for slot in slots:
                                time_total += 1
                                if not _valid_time_slot(slot):
                                    time_invalid += 1

                meta = r.get("meta") if isinstance(r.get("meta"), dict) else {}
                rmin, rmax, rraw = _extract_rate(parsed)
                is_quote = bool(rate_is_quote_like(rraw)) if rate_is_quote_like else False
                if is_quote:
                    quote_cases += 1
                    if rmin is not None or rmax is not None:
                        quote_minmax_nonnull += 1

                ar = parsed.get("additional_remarks")
                ar_s = str(ar).strip() if isinstance(ar, str) and str(ar).strip() else None
                if ar_s:
                    remarks_nonnull += 1
                    marker = bool(has_remarks_marker(raw_text)) if has_remarks_marker else False
                    if not marker:
                        remarks_no_marker += 1
                    elif substring_supported and not substring_supported(raw_text, ar_s):
                        remarks_not_substring += 1

                sig = meta.get("signals") if isinstance(meta.get("signals"), dict) else None
                if sig and sig.get("ok") is True and isinstance(sig.get("signals"), dict):
                    signals_ok += 1
                    sig_obj = sig.get("signals") if isinstance(sig.get("signals"), dict) else {}
                    subj = sig_obj.get("subjects") if isinstance(sig_obj.get("subjects"), list) else []
                    if any(isinstance(x, str) and x.strip() for x in subj):
                        signals_subjects_nonempty += 1
                    arq = sig_obj.get("academic_requests")
                    if isinstance(arq, list) and len(arq) > 0:
                        signals_academic_requests_nonnull += 1
                    flags = sig_obj.get("confidence_flags") if isinstance(sig_obj.get("confidence_flags"), dict) else {}
                    if bool(flags.get("ambiguous_academic_mapping")):
                        signals_ambiguous += 1

                    # Non-fatal mismatch proxy: display text hints academic content but signals has no subjects.
                    disp = parsed.get("academic_display_text")
                    disp_s = str(disp) if isinstance(disp, str) else ""
                    if disp_s and display_academic_hint_re.search(disp_s) and not any(isinstance(x, str) and x.strip() for x in subj):
                        signals_display_mismatch += 1

                bc = by_channel.setdefault(channel, {"ok_rows": 0})
                bc["ok_rows"] = bc.get("ok_rows", 0) + 1
                if sig and sig.get("ok") is True:
                    bc["signals_ok"] = bc.get("signals_ok", 0) + 1
                    sig_obj = sig.get("signals") if isinstance(sig.get("signals"), dict) else {}
                    subj = sig_obj.get("subjects") if isinstance(sig_obj.get("subjects"), list) else []
                    if any(isinstance(x, str) and x.strip() for x in subj):
                        bc["signals_subjects_nonempty"] = bc.get("signals_subjects_nonempty", 0) + 1
                    arq = sig_obj.get("academic_requests")
                    if isinstance(arq, list) and len(arq) > 0:
                        bc["signals_academic_requests_nonnull"] = bc.get("signals_academic_requests_nonnull", 0) + 1
                    flags = sig_obj.get("confidence_flags") if isinstance(sig_obj.get("confidence_flags"), dict) else {}
                    if bool(flags.get("ambiguous_academic_mapping")):
                        bc["signals_ambiguous"] = bc.get("signals_ambiguous", 0) + 1

            time_valid_rate = None
            if time_total:
                time_valid_rate = (time_total - time_invalid) / float(time_total)

            return {
                "ok_rows": len(ok_rows),
                "time_slots_total": time_total,
                "time_slots_invalid": time_invalid,
                "time_structure_errors": time_structure_errors,
                "time_valid_rate": time_valid_rate,
                "time_non_empty_rows": time_non_empty_rows,
                "time_non_empty_rate": (time_non_empty_rows / float(len(ok_rows))) if ok_rows else None,
                "time_note_present_rows": time_note_present_rows,
                "time_note_present_rate": (time_note_present_rows / float(len(ok_rows))) if ok_rows else None,
                "rate_quote_cases": quote_cases,
                "rate_quote_minmax_nonnull": quote_minmax_nonnull,
                "additional_remarks_nonnull": remarks_nonnull,
                "additional_remarks_no_marker": remarks_no_marker,
                "additional_remarks_not_substring": remarks_not_substring,
                "signals_ok": signals_ok,
                "signals_subjects_nonempty": signals_subjects_nonempty,
                "signals_academic_requests_nonnull": signals_academic_requests_nonnull,
                "signals_ambiguous": signals_ambiguous,
                "signals_display_mismatch": signals_display_mismatch,
                "by_channel": by_channel,
            }

        summary["extra_metrics"] = {
            "enabled": True,
            "pipelines": {
                "a": _extra_metrics_for_pipeline(a_by_raw),
                "b": _extra_metrics_for_pipeline(b_by_raw),
            },
        }

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
                va = _normalize_field(field_type, _get_path(a_json, field))
                vb = _normalize_field(field_type, _get_path(b_json, field))
                row[f"{field}_a"] = _val_for_csv(va)
                row[f"{field}_b"] = _val_for_csv(vb)
                row[f"{field}_eq"] = "1" if va == vb else "0"

            w.writerow(row)

    return {"summary": str(summary_path), "csv": str(csv_path)}


def main() -> None:
    # Minimal "standalone" usage via env vars.
    # Prefer the experiment runner for a full workflow.
    cfg0 = load_aggregator_config()
    pipeline_a = str(cfg0.ab_pipeline_a or "").strip()
    pipeline_b = str(cfg0.ab_pipeline_b or "").strip()
    if not pipeline_a or not pipeline_b:
        raise SystemExit("Set AB_PIPELINE_A and AB_PIPELINE_B to compare.")

    since = str(cfg0.ab_since_iso or "").strip() or None
    until = str(cfg0.ab_until_iso or "").strip() or None
    out_dir = Path(str(cfg0.ab_out_dir or "").strip() or f"utilities/out/ab_compare_{int(time.time())}")

    cfg = CompareConfig(pipeline_a=pipeline_a, pipeline_b=pipeline_b, since_iso=since, until_iso=until)
    res = compare_runs(cfg)
    paths = write_reports(out_dir, cfg, res)
    print(f"Wrote: {paths['summary']}")
    print(f"Wrote: {paths['csv']}")


if __name__ == "__main__":
    main()
