# TutorDex Subjects Taxonomy (v2) – Mapping Rules

This document describes the deterministic, drift-resistant rules used to convert noisy subject strings (LLM outputs, TutorCity API labels, website selections) into stable `subjects_canonical[]` and `subjects_general[]` codes.

## Inputs

- `level`: optional string (may be noisy; e.g. `"O Level"`, `"IB / IGCSE"`, `"Secondary"`)
- `subjects[]`: list of subject labels (may include punctuation variants; e.g. `"Physics/Chem"`, `"Physics / Chemistry"`)

## Outputs

- `subjects_canonical[]`: stable subject codes (API contract)
- `subjects_general[]`: general category rollups derived *only* from taxonomy parent refs
- `canonicalization_version`: equals taxonomy `version` (currently `2`)
- `canonicalization_debug` (optional): diagnostics and provenance (never used for filtering)

## Deterministic canonicalization pipeline

1. **Normalize** each subject label:
   - case-insensitive
   - collapse whitespace
   - treat punctuation/separators (`/`, `&`, `.`, `-`, `(`, `)`) as non-semantic
2. **Alias lookup**:
   - exact match on the normalized label against the taxonomy `subject_aliases` index
   - no fuzzy matching beyond normalization
3. **Level-aware mapping**:
   - resolve `level` via taxonomy `level_aliases` to a canonical `level_code`
   - map `(level_code, subject_key)` using `mappings.by_level_subject_key[level_code]`
   - if missing, try `mappings.by_level_subject_key["ANY"]`
4. **No guessing**:
   - never infer tracks like IB Math AA vs AI unless explicitly present upstream
   - if the subject is too ambiguous, map to a safe `*_UNKNOWN` canonical code where available
5. **Derive `subjects_general[]`**:
   - for every canonical code, add its `general_category_code`
   - do not compute categories from strings; categories come only from validated taxonomy references

## Stability rules

- **Never rename codes.** If a code becomes undesirable, mark it deprecated and create a replacement.
- **Version bump** (`version` integer) whenever mappings or codes change in a way that would alter `subjects_canonical[]`.
- **Backfill** existing rows when bumping the version.

