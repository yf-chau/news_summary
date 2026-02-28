# CLAUDE.md

## Project Overview

Automated Hong Kong news digest generator. Fetches articles from HK news RSS feeds, uses Google Gemini to identify topics, summarize, and sub-edit, then publishes a weekly newsletter to Substack via the `python-substack` API.

The output language is **Traditional Chinese** (繁體中文). All Gemini prompts enforce this.

## Architecture

The pipeline runs in `main.py` and follows this flow:

1. **Article Loading** — `load_articles()` reads accumulated articles from `data/articles.jsonl` (built by daily fetches); falls back to fresh RSS fetch if no JSONL exists
2. **Topic Generation** — `gemini.generate_topics()` identifies top N topics from headlines/summaries
3. **Article Grouping** — `gemini.generate_articles_list_by_topic()` assigns articles to topics by UUID
4. **Per-Topic Summary** — `gemini.topic_summary()` writes a 250–600 character Chinese summary per topic
5. **Sub-editing** — `gemini.subedit_summary()` enforces style consistency (titles, dates, character set)
6. **Best-of-N Evaluation** — `gemini.evaluate_output()` scores multiple runs and picks the best
7. **Publish** — `substack_api.publish_substack_post()` creates a draft, then publishes it and emails subscribers via the `python-substack` REST API

## Key Files

| File | Purpose |
|---|---|
| `main.py` | Pipeline orchestrator |
| `fetch_articles.py` | Daily RSS accumulator — deduplicates by URL, appends to JSONL, prunes >10 days |
| `gemini.py` | Gemini API client, all LLM prompts, retry logic (tenacity) |
| `utils.py` | RSS parsing, HTML→Markdown, article text/link formatting, JSON extraction |
| `response_model.py` | Pydantic models for structured Gemini output validation |
| `substack_api.py` | Substack post publishing via `python-substack` REST API (cookie or email/password auth) |
| `tests/verify_draft.py` | Dev-only Playwright script to verify drafts exist on Substack dashboard |
| `tests/rss_feed_test.py` | Standalone utility to test RSS feed URL validity |
| `deepseek_client.py` | Minimal DeepSeek API snippet (unused) |

## Environment Variables

Required in `.env`:
- `GEMINI_API_KEY` — Google Gemini API key
- `SUBSTACK_EMAIL` — Substack login email
- `SUBSTACK_PASSWORD` — Substack login password
- `SUBSTACK_URL` — Substack publication base URL (e.g. `https://hknewsdigest.substack.com`)

Optional:
- `SUBSTACK_SID` — Substack cookies as a JSON object string (preferred over email/password auth)
- `HEADLESS` — Playwright headless mode for `verify_draft.py` (`true`/`false`, default: `true`)

## Tech Stack

- **uv** — package manager (`uv run`, `uv add`, `uv sync`)
- **Python** — managed via `pyproject.toml` + `uv.lock`
- **Google Gemini** (`google-genai` SDK) — model: `gemini-2.5-pro-preview-03-25`
- **python-substack** — Substack REST API client (draft creation, publishing, auth)
- **Playwright** + `playwright-stealth` — dev dependency only, used by `tests/verify_draft.py`
- **feedparser** — RSS feed parsing
- **pandas** — article data handling (CSV intermediate storage)
- **Pydantic** — structured LLM response validation
- **tenacity** — retry with exponential backoff on Gemini and Substack API calls
- **Docker** — slim `python:3.12-slim` image with `uv`

## Conventions

- Accumulated articles are stored in `data/articles.jsonl` (one JSON object per line, gitignored, persisted between CI runs via `actions/cache`)
- Intermediate outputs are saved as numbered JSON files in `temp/` (01-topics.json, 02-articles_by_topic.json, etc.)
- All Gemini responses that need structure are validated against Pydantic models in `response_model.py`
- Gemini responses are expected inside markdown ```json code blocks; `utils.extract_json_to_dict()` handles extraction
- RSS feed sources are defined as a dict in `main.py` (`rss_feeds`)
- The newsletter covers the **past 7 days** of articles

## Running

```bash
# Install dependencies
uv sync

# Fetch and accumulate today's articles
uv run python fetch_articles.py

# Run the pipeline
uv run python main.py

# Run draft verification (dev only, requires Playwright)
uv run --dev python tests/verify_draft.py --title "February 25, 2026 香港每週新聞摘要"

# Run via Docker
docker build -t news-summary .
docker run --env-file .env news-summary
```

## Scheduling

Two workflows handle the weekly digest:

### Daily Article Fetch (Sun–Fri)

RSS feeds only retain ~1–2 days of articles. A daily fetch job accumulates articles throughout the week so Saturday's digest has full 7-day coverage.

- **Workflow file:** `.github/workflows/daily-fetch.yml`
- **Runner:** `ubuntu-latest` (GitHub-hosted — no secrets needed, only public RSS feeds)
- **Trigger:** `cron: "0 1 * * 0-5"` (Sun–Fri 01:00 UTC / 09:00 HKT) + manual `workflow_dispatch`
- **Storage:** `data/articles.jsonl` persisted between runs via `actions/cache` (shared across workflows on the same branch)

### Weekly Digest (Saturday)

- **Workflow file:** `.github/workflows/weekly-digest.yml`
- **Runner:** `self-hosted` (macOS, residential IP — required because Substack's Cloudflare bot protection blocks GitHub datacenter IPs)
- **Trigger:** `cron: "0 1 * * 6"` + manual `workflow_dispatch`
- **Flow:** Restores cached articles → runs a final fetch → runs the full pipeline
- **Manual run:** Go to **Actions** tab → **Weekly News Digest** → **Run workflow**
- **Scheduled wake:** `sudo pmset repeat wakeorpoweron WS 08:55:00` ensures the Mac wakes 5 minutes before the job (works with lid closed if power is connected)

### Self-Hosted Runner Setup

1. Go to repo **Settings > Actions > Runners > New self-hosted runner**
2. Select **macOS / ARM64**, follow the download & config instructions
3. Install as a persistent service: `./svc.sh install && ./svc.sh start`
4. The runner auto-starts on login/wake via `launchd`

### Required GitHub Repository Secrets

| Secret | Value |
|--------|-------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `SUBSTACK_EMAIL` | Substack login email |
| `SUBSTACK_PASSWORD` | Substack login password |
| `SUBSTACK_URL` | e.g. `https://hknewsdigest.substack.com` |
| `SUBSTACK_SID` | `substack.sid` cookie value from a browser session |

The workflow uses `uv` directly (via `astral-sh/setup-uv`) instead of Docker. `SUBSTACK_SID` is passed as an env var — the Python code parses it into cookie strings at runtime.

## Auth Resilience

The `SUBSTACK_SID` session cookie expires after ~90 days. There is no reliable way to auto-refresh it (Substack deploys CAPTCHA on datacenter IPs).

- **Preflight check** — `main.py` calls `substack_api.verify_auth()` before any Gemini API calls. If auth fails, the pipeline exits immediately with code 2 and a clear error message, avoiding wasted Gemini quota.
- **`SubstackAuthError`** — Custom exception in `substack_api.py`, raised when both cookie and email/password auth fail.
- **Mid-week auth check** — `.github/workflows/check-substack-auth.yml` runs every Wednesday (3 days before the Saturday digest) to verify the cookie is still valid. On failure, GitHub sends an email notification and writes to the job summary.
- **Failure alerts** — Both the digest and auth-check workflows write actionable messages to `$GITHUB_STEP_SUMMARY` on failure. Ensure **Settings > Notifications > Actions** is enabled in the GitHub repo to receive email alerts.

## Common Pitfalls

- Gemini may return invalid UUIDs when grouping articles; `generate_articles_list_by_topic()` has a retry loop for this
- Safety settings are set to OFF for all Gemini categories to avoid content blocks on news articles
- The `temp/` directory is auto-created and gitignored
- Substack may require CAPTCHA on email/password login; use cookie-based auth (`SUBSTACK_SID`) to avoid this — extract cookies manually from a browser session
- `python-substack`'s `from_markdown()` handles standard Markdown (headings, bold, links, bullets); complex elements may not render perfectly — use `tests/verify_draft.py` to check
