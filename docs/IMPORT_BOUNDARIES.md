# Import Boundaries and Architecture Rules

This repo enforces architectural boundaries via `import-linter` to prevent cross-component coupling and circular import risks.

## Rules

### 1) Component independence

- `TutorDexBackend` must not import from `TutorDexAggregator`
- `TutorDexAggregator` must not import from `TutorDexBackend`

### 2) Shared module purity

- `shared/` must not import from any application code (`TutorDexBackend`, `TutorDexAggregator`)

### 3) Layered architecture (no circular imports)

Backend layers (higher can import lower, not reverse):
1. `TutorDexBackend.routes`
2. `TutorDexBackend.services`
3. `TutorDexBackend.utils`

Aggregator layers (higher can import lower, not reverse):
1. `TutorDexAggregator.workers`
2. `TutorDexAggregator.services`
3. `TutorDexAggregator.extractors`
4. `TutorDexAggregator.utils`

## Run locally

```bash
lint-imports
lint-imports --contract backend-independence
```
