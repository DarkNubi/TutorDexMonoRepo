# Deterministic Academic Signals (`meta.signals`)

TutorDex runs an LLM extractor to produce a **display** JSON (stored in `telegram_extractions.canonical_json`).
Separately, the queue worker produces deterministic **matching signals** from text and stores them under `telegram_extractions.meta.signals`.

This keeps the LLM as the UX layer while enabling conservative, testable matching logic.

## Where signals are computed

- Worker: `TutorDexAggregator/workers/extract_worker.py`
- Builder: `TutorDexAggregator/signals_builder.py`
- Parser: `TutorDexAggregator/extractors/academic_requests.py`
- Subject matching: `TutorDexAggregator/extractors/subjects_matcher.py`
- Canonicalization: `TutorDexAggregator/canonicalization/academic.py`

Signals use `canonical_json.academic_display_text` when present; otherwise fallback to normalized/raw text.

## Feature flag

- `ENABLE_DETERMINISTIC_SIGNALS=0/1` (default `1`)
  - `1`: compute signals and store into `meta.signals` (never affects canonical JSON)
  - `0`: disable signals generation entirely

Signals generation is best-effort and never fails a job; failures are stored as `meta.signals.ok=false` with `meta.signals.error`.

## Schema (`meta.signals`)

```json
{
  "ok": true,
  "signals": {
    "schema_version": 1,
    "source": "academic_display_text|normalized_text|raw_text",
    "text_chars": 123,
    "subjects": ["English", "Maths"],
    "tutor_types": [
      {"canonical":"part-timer","original":"PT","agency":null,"confidence":0.9}
    ],
    "rate_breakdown": {
      "part-timer": {"min":15,"max":25,"currency":"$","unit":"hour","original_text":"$15-25/hr","confidence":0.9}
    },
    "levels": ["Primary"],
    "specific_student_levels": ["Primary 4", "Primary 6"],
    "streams": ["G3", "Express", "HL"],
    "academic_requests": [
      {
        "level": "Primary",
        "specific_student_level": "Primary 4",
        "stream": null,
        "subjects": ["English"]
      }
    ],
    "evidence": {
      "source_text_chars": 123,
      "tokens": [
        {"kind":"specific_level","value":"Primary 4","start":0,"end":2,"text":"P4"}
      ]
    },
    "confidence_flags": {
      "ambiguous_academic_mapping": false
    }
  },
  "summary": {
    "subjects": 2,
    "levels": 1,
    "academic_requests": 1,
    "ambiguous": false
  }
}
```

Notes:
- `academic_requests` is `null` when subjects cannot be safely associated to a level/stream context.
- `ambiguous_academic_mapping=true` indicates the parser found subjects without a valid context (no guessing).

## Examples

### `P4 English and P6 Math`
- Rollup:
  - `subjects=["English","Maths"]`
  - `levels=["Primary"]`
  - `specific_student_levels=["Primary 4","Primary 6"]`
- `academic_requests`:
  - `[{"specific_student_level":"Primary 4","subjects":["English"]},{"specific_student_level":"Primary 6","subjects":["Maths"]}]`

### `Sec 3 G3 English and G2 Math`
- `academic_requests` produces two entries (stream change starts a new request):
  - `Secondary 3, G3, English`
  - `Secondary 3, G2, Maths`

## Running tests

From repo root:

- `python3 -m unittest discover -s tests -p 'test_*.py' -q`

## A/B evaluation metrics (signals)

`TutorDexAggregator/utilities/ab_compare_extractions.py` supports extra metrics with:

- `AB_EXTRA_METRICS=1`

This includes (when available):
- coverage: `% with non-empty meta.signals.subjects`
- coverage: `% with non-null meta.signals.academic_requests`
- ambiguity rate: `% with meta.signals.confidence_flags.ambiguous_academic_mapping=true`

