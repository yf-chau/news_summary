# 香港每週新聞摘要

每週六自動發佈的香港新聞摘要，由 AI 閱讀數百篇文章，提煉出最重要的議題，以繁體中文撰寫精簡摘要。

## 緣起

自從離開香港後忙於外地的生活，即使想留意香港的新聞有時也感覺有心無力，尤其是現在可說是香港的媒體寒冬，多個獨立媒體努力做報導，但要綜合各媒體的報導作一個較全面的理解並不容易。

我在轉職成數據科學家前從事新聞公關工作，為主要官員撰寫新聞摘要可說是家常便飯。現時人工智能發展迅速，這個 side project 嘗試用大語言模型 (Large Language Model, LLM) 將之前寫作新聞摘要的流程交給人工智能完成。成果還算見得人，那就姑且公開讓人參考。

## 新聞來源

本摘要涵蓋以下媒體的報道：

- [集誌社](https://thecollectivehk.com/)
- [法庭線](https://thewitnesshk.com/)
- [庭刊](https://hkcourtnews.com/)
- [獨立媒體](https://www.inmediahk.net/)
- [Yahoo 港聞](https://hk.news.yahoo.com/hong-kong/)
- [Yahoo 財經](https://hk.news.yahoo.com/business/)

## 運作方式

每週六早上，系統自動從上述媒體抓取過去七天的新聞文章，透過 Google Gemini AI 分析數百篇報道，歸納出本週最重要的五大議題，並為每個議題撰寫簡明摘要，最後自動發佈到 Substack。

## 訂閱

免費訂閱，每週六收到新聞摘要：

**[https://hknewsdigest.substack.com](https://hknewsdigest.substack.com)**

---

# HK Weekly News Digest

An AI-powered weekly Hong Kong news digest, published every Saturday on Substack.

## Background

Since leaving Hong Kong, keeping up with the news back home has been difficult amid the demands of life abroad. Hong Kong is in something of a media winter — several independent outlets are doing important reporting, but synthesising coverage across multiple sources into a coherent picture is no easy task.

Before becoming a data scientist I worked in news and public relations, where writing news digests for senior officials was part of the daily routine. With the rapid advances in AI, this side project tries to hand that same editorial workflow to a large language model (LLM). The results have been decent enough to share publicly.

## News Sources

The digest draws from the following outlets:

- [The Collective HK (集誌社)](https://thecollectivehk.com/)
- [The Witness (法庭線)](https://thewitnesshk.com/)
- [HK Court News (庭刊)](https://hkcourtnews.com/)
- [InMedia (獨立媒體)](https://www.inmediahk.net/)
- [Yahoo HK News (Yahoo 港聞)](https://hk.news.yahoo.com/hong-kong/)
- [Yahoo HK Finance (Yahoo 財經)](https://hk.news.yahoo.com/business/)

## How It Works

Every Saturday morning the system fetches the past week's articles from the sources above, uses Google Gemini to analyse hundreds of articles, identify the top five topics, and write concise summaries in Traditional Chinese. The finished digest is then automatically published to Substack.

## Subscribe

Free — delivered to your inbox every Saturday:

**[https://hknewsdigest.substack.com](https://hknewsdigest.substack.com)**

## Architecture

The pipeline runs in `main.py` and follows this flow:

1. **RSS Fetch** — Pull articles from 6 HK news feeds via `feedparser`
2. **Topic Generation** — Gemini identifies top N topics from headlines/summaries
3. **Article Grouping** — Gemini assigns articles to topics by UUID
4. **Per-Topic Summary** — Gemini writes a 250–600 character Traditional Chinese summary per topic
5. **Sub-editing** — Gemini enforces style consistency (titles, dates, character set)
6. **Best-of-N Evaluation** — Gemini scores multiple runs and picks the best
7. **Publish** — Create and publish the post on Substack via the `python-substack` REST API

## Key Files

| File | Purpose |
|---|---|
| `main.py` | Pipeline orchestrator |
| `gemini.py` | Gemini API client, all LLM prompts, retry logic (tenacity) |
| `utils.py` | RSS parsing, HTML-to-Markdown, article text/link formatting, JSON extraction |
| `response_model.py` | Pydantic models for structured Gemini output validation |
| `substack_api.py` | Substack post publishing via `python-substack` REST API |
| `tests/rss_feed_test.py` | Standalone utility to test RSS feed URL validity |

## Environment Variables

### Required

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key |
| `SUBSTACK_EMAIL` | Substack login email |
| `SUBSTACK_PASSWORD` | Substack login password |
| `SUBSTACK_URL` | Substack publication base URL (e.g. `https://hknewsdigest.substack.com`) |

### Optional

| Variable | Description |
|---|---|
| `SUBSTACK_SID` | Substack `substack.sid` cookie value (preferred over email/password auth) |

## Tech Stack

- **[uv](https://docs.astral.sh/uv/)** — Package manager (`uv run`, `uv sync`)
- **Python 3.12**
- **[Google Gemini](https://ai.google.dev/)** (`google-genai` SDK) — `gemini-2.5-pro-preview-03-25`
- **[python-substack](https://github.com/hamelsmu/python-substack)** — Substack REST API client
- **[feedparser](https://feedparser.readthedocs.io/)** — RSS feed parsing
- **[pandas](https://pandas.pydata.org/)** — Article data handling
- **[Pydantic](https://docs.pydantic.dev/)** — Structured LLM response validation
- **[tenacity](https://tenacity.readthedocs.io/)** — Retry with exponential backoff
- **Docker** — `python:3.12-slim` image with `uv`

## Setup & Running

```bash
# Install dependencies
uv sync

# Run the pipeline
uv run python main.py

# Run via Docker
docker build -t news-summary .
docker run --env-file .env news-summary
```

## Common Pitfalls

- Gemini may return invalid UUIDs when grouping articles — `generate_articles_list_by_topic()` has a retry loop for this
- Safety settings are set to OFF for all Gemini categories to avoid content blocks on news articles
- The `SUBSTACK_SID` cookie expires after ~90 days and must be manually rotated from a browser session
