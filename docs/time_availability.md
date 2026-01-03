# Deterministic `time_availability` (Rule-Based)

This repo now supports replacing the LLM-provided `canonical_json.time_availability` with a deterministic parser (code), while keeping all other LLM fields (including rate) unchanged.

## Output Schema (unchanged)

The final `canonical_json.time_availability` must always be:

```json
{
  "explicit": {
    "monday": [], "tuesday": [], "wednesday": [],
    "thursday": [], "friday": [], "saturday": [], "sunday": []
  },
  "estimated": {
    "monday": [], "tuesday": [], "wednesday": [],
    "thursday": [], "friday": [], "saturday": [], "sunday": []
  },
  "note": "..." 
}
```

- Every day key must exist.
- Every day value must be a `list[str]`.
- All time windows must be `"HH:MM-HH:MM"` (24h, leading zeros, ASCII `-`).
- A single explicit time (e.g. “Tue at 7pm”) is represented as `start=end` (no duration inference).

## Semantics

### `explicit`
Only emitted when a **concrete day** and a **concrete time** are both explicitly present.

Examples:
- “Timing: Tuesday at 7pm” → `explicit.tuesday = ["19:00-19:00"]`
- “Thu 2pm-4pm” → `explicit.thursday = ["14:00-16:00"]`

### `estimated`
Only emitted for:
- relative rules: `after/from HH:MM`, `before HH:MM`
- fuzzy buckets: morning/afternoon/evening/night
- broad day sets: weekdays/weekends
- day ranges: “Mon-Fri”, “Tue to Thu” (treated as estimated even if paired with a concrete time)

Fixed estimated ranges:
- morning = `08:00-12:00`
- afternoon = `12:00-17:00`
- evening = `16:00-21:00`
- night = `19:00-23:00`
- weekdays (no time specified) = Mon–Fri `08:00-23:00`
- weekends (no time specified) = Sat–Sun `08:00-23:00`

Relative estimated rules:
- “after HH:MM” or “from HH:MM” with no end → `HH:MM-23:00`
- “before HH:MM” with no start → `08:00-HH:MM`

## Policy Decisions (intentional)

### 1) “weekdays at 7:30pm”
Stored as **estimated** for Mon–Fri with a single-time window:
- Mon–Fri: `"19:30-19:30"`

Rationale: “weekdays” is a broad set (not a concrete day), but it is still useful for matching.

### 2) Day ranges like “Mon-Fri”
Treated as **estimated** even if a concrete time is present.

Rationale: a range is closer to “broad availability” and tends to be used loosely; estimated is safer.

### 3) Negations like “No Sunday before 3pm”
The schema does not represent “unavailability”.

Current behavior:
- still emits the corresponding estimated window (e.g. Sunday `08:00-15:00`)
- adds `meta.time_deterministic.parse_warnings += ["negation_detected_near_time"]`

If you later add an “unavailable” schema, update this parser accordingly.

### 4) Day lists like “Mon / Thu / Fri - after 4pm”
If a line contains a list of multiple days but only a single time expression, the parser applies that time expression to **all** days in the list.

This also works across adjacent lines in a timing block, e.g.:
- `Timing:` (header)
- `Monday / Thursday / Friday` (days)
- `After 4pm` (time)

The carry-over behavior is recorded via `meta.time_deterministic.rules_fired` (e.g. `carry_days_to_next_line`).

## Implementation

- Parser: `TutorDexAggregator/extractors/time_availability.py`
  - Entry point: `extract_time_availability(raw_text, normalized_text)`
  - Returns `(time_availability_obj, meta)` where meta includes:
    - `matched_spans[]` with normalized indices and evidence substrings
    - `rules_fired[]`
    - `parse_warnings[]`

## Integration

- Worker integration: `TutorDexAggregator/workers/extract_worker.py`
  - Feature flag: `USE_DETERMINISTIC_TIME=0/1`
  - When enabled:
    - overwrites `payload["parsed"]["time_availability"]` before hard validation
    - stores debug meta at `telegram_extractions.meta.time_deterministic`

- Local runner: `TutorDexAggregator/utilities/run_sample_pipeline.py`
  - Flag: `--use-deterministic-time 0|1` (default `1`)

## Tests

- `tests/test_time_availability.py`
  - Covers explicit, estimated (relative rules), weekdays policy, note-only cases, and output-shape invariants.
