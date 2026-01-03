# Subjects Taxonomy v2 – Implementation Notes

## Goals

- Single source of truth for subject codes, labels, aliases, and mapping rules.
- Deterministic canonicalization (no guessing) across:
  - Telegram LLM ingestion (via deterministic parsing of `academic_display_text`)
  - TutorCity API ingestion (subject IDs -> labels -> canonicalization)
  - Website UI selections (canonical codes as API contracts)
- Drift guardrails so Aggregator/Backend/Website cannot silently diverge.

## Where things live

- Source of truth: `shared/taxonomy/subjects/subjects_taxonomy_v2.json`
- Validator + drift guard: `shared/taxonomy/subjects/validate_taxonomy.py`
- Sync command: `shared/taxonomy/subjects/sync_taxonomy_artifacts.py`
- Derived copies (generated; do not edit):
  - `TutorDexAggregator/taxonomy/subjects_taxonomy_v2.json`
  - `TutorDexWebsite/src/generated/subjects_taxonomy_v2.json`

## Runtime wiring (no drift)

- Aggregator:
  - Deterministic extraction: `TutorDexAggregator/extractors/academic_requests.py`
  - Canonicalization wrapper: `TutorDexAggregator/taxonomy/canonicalize_subjects.py`
  - Persistence: `TutorDexAggregator/supabase_persist.py` writes:
    - `subjects_canonical[]`
    - `subjects_general[]`
    - `canonicalization_version`
    - `canonicalization_debug` (only when `SUBJECT_TAXONOMY_DEBUG=1`)
- Backend:
  - `/assignments` and `/assignments/facets` support `subject_general` + `subject_canonical`.
- Website:
  - Filter options + labels derived from taxonomy JSON via `TutorDexWebsite/src/taxonomy/subjectsTaxonomyV2.js`.
  - Tutor profile stores canonical subject codes in `subjects[]`.

## Database migration

- Apply: `TutorDexAggregator/supabase sqls/2026-01-03_subjects_taxonomy_v2.sql`
- Backfill: `python3 TutorDexAggregator/utilities/backfill_subjects_taxonomy_v2.py --status open --limit 2000`

## Adding a new subject safely

1. Add a new `canonical_subjects[]` entry with a new `code` (never rename existing codes).
2. Ensure its `general_category_code` exists in `general_categories[]`.
3. Add a `subject_aliases` entry (or several) mapping real-world strings to a `subject_key`.
4. Add/update `mappings.by_level_subject_key` for the relevant level(s) (or `ANY`).
5. If the subject should appear in deterministic signals display, add a `subject_key_display_labels` entry.
6. Run:
   - `python3 shared/taxonomy/subjects/validate_taxonomy.py --check-sync`
   - `python3 shared/taxonomy/subjects/sync_taxonomy_artifacts.py`

## Adding a new agency mapping safely

If the agency provides subject *IDs*:
- Add a stable `ID -> label` map in the agency fetcher.
- Feed the resulting labels into canonicalization (do not map IDs directly to codes).
- Store raw IDs/labels in `meta.source_mapped` for provenance.

If the agency provides subject *labels*:
- Add those raw labels to `subject_aliases` (as-is) pointing to the right `subject_key`.

