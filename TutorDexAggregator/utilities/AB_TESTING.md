# TutorDexAggregator — A/B Testing (Models, Prompts, Examples)

This repo supports controlled A/B comparisons against identical raw inputs by using:
- `telegram_messages_raw` as the stable input log
- `telegram_extractions` as a versioned work/output queue keyed by `(raw_id, pipeline_version)`

## What you can compare

- **Models**: `LLM_API_URL`, `LLM_MODEL_NAME`
- **System prompts**: `LLM_SYSTEM_PROMPT_*`
- **Examples sets** (few-shot context): `LLM_INCLUDE_EXAMPLES`, `LLM_EXAMPLES_VARIANT`, `LLM_EXAMPLES_DIR`

The worker persists the configuration into `telegram_extractions.meta`:
- `meta.prompt` (sha256, chars, source)
- `meta.examples` (enabled, sha256, file/dir, etc.)

## One-click A/B runner (recommended)

Edit and run:
- `TutorDexAggregator/utilities/ab_experiment.py`

This runs:
1) enqueue-from-raw for Run A
2) drain worker for Run A (oneshot, no broadcast/DM)
3) repeat for Run B
4) generate reports (summary + CSV)

### Typical execution plan (model/prompt/examples A/B)

1) Pick a fixed evaluation window (recommended while iterating):
   - Example: last 7 days (`SINCE_ISO` / `UNTIL_ISO`)
2) Configure Run A + Run B in `ab_experiment.py`:
   - set `pipeline_version` for each run (must be unique)
   - set model and/or prompt and/or examples knobs per run
3) Run `ab_experiment.py` once.
4) Inspect:
   - `summary.json` for headline stats
   - `side_by_side.csv` for per-message diffs (filter by any `*_eq=0`)

### Required environment

Your environment (or `TutorDexAggregator/.env`) must include:
- `SUPABASE_ENABLED=1`
- `SUPABASE_URL_HOST=...` (host Python) and/or `SUPABASE_URL_DOCKER=...` (Docker), or `SUPABASE_URL=...` (fallback)
- `SUPABASE_SERVICE_ROLE_KEY=...`
- `SUPABASE_RAW_ENABLED=1` (so Mode 3 enqueue can read raw)
- `EXTRACTION_QUEUE_ENABLED=1`
- `LLM_API_URL=...`
- `LLM_MODEL_NAME=...` (optional if you set per run)

## Prompt switching options

Set exactly one (precedence top → bottom):
- `LLM_SYSTEM_PROMPT_TEXT="..."` (inline)
- `LLM_SYSTEM_PROMPT_FILE=prompts/system_prompt_live.txt`

Recommended workflow:
- Create two prompt files and point each run at its file via `system_prompt_file=...` in `ab_experiment.py`.

## Examples switching options

Examples are optional and are OFF by default in the worker pipeline.

- Enable examples:
  - `LLM_INCLUDE_EXAMPLES=1`
- Choose a variant folder:
  - Create `TutorDexAggregator/message_examples_variants/<variant>/`
  - Put `general.txt` and optionally `<agency>.txt` inside (same filenames as `message_examples/`)
  - Set `LLM_EXAMPLES_VARIANT=<variant>`

Recommended workflow:
- Create:
  - `TutorDexAggregator/message_examples_variants/A/general.txt`
  - `TutorDexAggregator/message_examples_variants/B/general.txt`
- For agency-specific overrides, also create e.g.:
  - `TutorDexAggregator/message_examples_variants/A/mindflex.txt`
  - `TutorDexAggregator/message_examples_variants/B/mindflex.txt`
- Set `include_examples=True` and `examples_variant="A"`/`"B"` in `ab_experiment.py`.
- Or choose an explicit directory:
  - `LLM_EXAMPLES_DIR=message_examples` (or any other folder)

## Reports

The A/B runner writes into a timestamped folder:
- `summary.json`: aggregate metrics (counts + field-level match/coverage)
- `side_by_side.csv`: per-raw_id field-by-field values for Run A vs Run B

If you want to generate reports for two existing pipeline versions only:
- Run `TutorDexAggregator/utilities/ab_compare_extractions.py` with env:
  - `AB_PIPELINE_A=...`
  - `AB_PIPELINE_B=...`
  - optional: `AB_SINCE_ISO=...`, `AB_UNTIL_ISO=...`, `AB_OUT_DIR=...`
