# Subjects Taxonomy v2 (Single Source of Truth)

This directory is the canonical (authoritative) source for TutorDex subject taxonomy v2.

## What lives here

- `subjects_taxonomy_v2.json`: stable codes + categories + aliases + mapping table
- `MAPPING_RULES_v2.md`: human rules (must match implementation)
- `validate_taxonomy.py`: validator + drift guard entrypoint
- `sync_taxonomy_artifacts.py`: copies v2 JSON into app-local derived artifacts
- `implementation_v2.md`: wiring notes + safe update playbook

Derived copies may exist in other apps (e.g. website bundle inputs) but must match this source exactly.
