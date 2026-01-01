# Prompts

This folder holds system prompt files used by the extractor.

Recommended:
- Use `LLM_SYSTEM_PROMPT_FILE=prompts/system_prompt_live.txt` in `TutorDexAggregator/.env` for production.
- For A/B testing, create variants like `system_prompt_A.txt`, `system_prompt_B.txt` and set `LLM_SYSTEM_PROMPT_VARIANT=A|B`.

Notes:
- `prompts/system_prompt_live.txt` is what the production worker reads (via `LLM_SYSTEM_PROMPT_FILE`).
- After changing prompts, restart the long-running containers (`collector-tail`, `aggregator-worker`) to pick up the new file contents.
