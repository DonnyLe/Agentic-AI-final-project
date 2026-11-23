# Free model comparison (intake role, structured output)

Run with `uv run python -m kangaroo.scripts.compare_models --trials 5 --models ...` on 2026-11-15, OpenRouter free tier. "Tool call" means a valid `IntakeResult` function call on the first try; "Error" means the provider returned an error (rate limit or unavailable).

| Model | Tool call | Text JSON | Fail | Error | Avg time |
|---|---|---|---|---|---|
| nvidia/nemotron-3.5-lightning:free | 5/5 | 0 | 0 | 0 | 2.4s |
| nvidia/nemotron-3-ultra-550b-a55b:free | 5/5 | 0 | 0 | 0 | 8.8s |
| nvidia/nemotron-3.5-super-vl:free | 5/5 | 0 | 0 | 0 | 6.4s |
| google/gemma-4-31b-it:free | 0/5 | 0 | 0 | 5 | 0.7s |
| inclusionai/ling-3.2-flash:free | 2/5 | 0 | 0 | 3 | 14.9s |

Default for every role: `nvidia/nemotron-3.5-lightning:free`.
