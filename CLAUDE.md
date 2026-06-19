# CLAUDE.md

Guidance for working in this repo. Keep it accurate and terse — it loads every session.

## What this is

Multi-exam **General Awareness** study tool for Indian government exams. It scrapes
official sources, uses an LLM (Ollama) to produce **weekly summaries + practice MCQs**
per exam, and publishes a **pure-stdlib static site** to GitHub Pages. Live exams: RBI
Grade B (default), UPSC / Banking. Scaffolded: SEBI Grade A, NABARD Grade A.

No web framework, no database. Python standard library + a few scrapers. The LLM is
**Ollama** (`gpt-oss:120b-cloud` primary, small `qwen3.5` fallbacks). Cloud models run
on-demand even if absent from `ollama list`.

## Architecture (data-driven by `config.py`)

Everything is keyed off the `EXAMS` registry in `config.py` (name, `sources`, `taxonomy`
path, `active`). The pipeline, prompt builder, and site builder all read it, so **adding
an exam = a registry entry + a taxonomy JSON**, not pipeline edits.

Each exam's taxonomy lives in `data/patterns/<exam>.json` with a `prompt_profile`
(summary sections, topic/style distribution, `options_count`, examples). Weightage is
derived empirically from PYQs via `scripts/derive_weightage.py`.

### Key files
- `config.py` — `EXAMS`/`DEFAULT_EXAM`, Ollama/news/static settings, week+cycle helpers,
  chunk/word budgets.
- `pipeline/daily_runner.py` — weekly/monthly generation. **Two paths:** the original RBI
  default (PIB+RBI) and the additive generic multi-exam path. Scrape caching, map-reduce
  condensation, `--all-exams` with retry.
- `pipeline/prompt_builder.py` — builds the LLM prompt from a taxonomy (data-driven).
- `pipeline/news_runner.py` — news digest with a dedup ledger.
- `pipeline/static_runner.py` / `static_fetch.py` / `static_sources.py` — Economic Survey
  (yearly reference source): download → extract → map-reduce summary + **its own quiz**.
- `scrapers/` — `pib_scraper`, `rbi_scraper`, `econsurvey_scraper`, `news_scraper`,
  `question_scraper`.
- `scripts/build_site.py` (+ `_site_assets.py` CSS/JS) — renders `docs/`.
- `run.py` — scheduler + publisher.

## Flow

1. **Scrape** sources for the week → cache `data/scraped/<period>/<canonical-source>.json`
   (exam-independent — see Optimizations).
2. **Assemble content** per exam: build blocks per source; large sources are **map-reduced**
   into condensed notes cached at `data/chunk_notes/<period>/src-<source>.json` (shared).
3. **Generate**: `build_prompt` (taxonomy-driven) → Ollama → split into summary + MCQs.
4. **Save**: `data/summaries/<exam>/<key>.md` + `data/questions/generated/<exam>/<key>-qs.json`.
   The default exam (`rbi-grade-b`) keeps the original **flat** layout; others are namespaced.
5. **Build** `scripts/build_site.py` → `docs/` (`index.html`, `exams/<slug>.html`,
   `weeks/<slug>/<key>.html`, `static/<slug>/<source>.html`, `news.html`).
6. **Publish**: commit + push `docs/` → `.github/workflows/pages.yml` redeploys.

**Economic Survey** is a *separate* reference section (own summary + own quiz), never mixed
into weekly papers. **News** = RSS (ET/Mint/HT + Business Standard via Google News) →
dedup ledger → only new items are LLM-summarised → today+yesterday headline list +
collapsible "In this week".

### Scheduler (`run.py`, auto mode)
- **Weekly** — Mon 00:00: ingest the just-completed week (Mon–Sun) for **all active exams**,
  rebuild, push.
- **News** — daily 00:00: refresh digest, rebuild, push.
- Catches up missed weeks at startup; auto mode always publishes.

## Conventions & constraints

- `data/` is gitignored — **only `docs/` is committed**. `data/patterns/` (taxonomy) is the
  one hand-edited part of `data/`.
- **Never store full copyrighted article bodies** — RSS metadata only.
- **RBI default path is proven; keep changes additive.** New exams use the generic path.
- Two week numberings: pipeline `--week N` (from `WEEK_RANGE_START`, 1 Dec 2025) vs the
  **display** cycle number (Week 1 = last Mon of December). Files key on the date range.
- `main` is branch-protected (CODEOWNERS; owner-only approver). Commit messages end with
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
- Email code is kept but **not triggered by the pipeline** (manual `--email-to` only).
- `.claudeignore` controls only what Claude loads; Ollama/the pipeline read `data/` from
  disk regardless. Don't "fix" the pipeline by un-ignoring data.

## Resource optimization — minimize, never at the cost of quality

Default to the least tokens / memory / compute that still produces a **fully correct,
high-quality result**. Saving resources must **never** degrade the summaries, the MCQs, the
site, or correctness. When the two conflict, quality wins — note the cost instead of cutting
the corner.

Already in place (preserve these):
- **Scrape once, share across exams** — sources canonicalize (`pib` & `pib_all` → `pib`) to
  one exam-independent cache; an in-run guard prevents re-scraping even with `--refresh-cache`.
- **Condense shared sources once** — map-reduce notes cached per canonical source; identical
  block formatting across exams makes the content-hash cache actually hit. Only the per-exam
  final summary + questions differ.
- **News dedup ledger** (`data/news/seen.json`) — LLM runs only on genuinely new articles.
- **Content-hash chunk caching** everywhere → idempotent, cheap re-runs.
- **Renderer-side fixes** (e.g. markdown tables) — fix in `build_site.py` once, applies to all
  pages on rebuild; no regeneration.

When editing in-session (token discipline):
- Read only the file ranges you need; prefer targeted `Edit`s; don't re-read a file you just
  edited. Use `Grep`/`Glob` to locate, not full-file reads.
- Keep generation **sequential per exam** so the shared scrape/condensation cache is warm for
  the next exam (parallelizing would re-do shared work — a false economy).

Worth considering later (don't block on these):
- Per-exam scheduler state (currently a single global `current_week`).
- Yojana as a monthly reference source (deferred; mechanism is generic).

## Gotchas
- A full weekly run is genuinely heavy (~30 min/exam): PIB can be ~190k words → ~15 map-reduce
  chunks. The 740-page Economic Survey is slow to extract (pdfplumber) and map-reduce. This is
  expected; don't truncate to "speed it up" — that's what regressed the ES summary before.
- `gpt-oss:120b-cloud` is the primary even though it's a cloud model not shown by `ollama list`.

## Common commands
```bash
python pipeline/daily_runner.py --week N --all-exams      # generate all active exams
python pipeline/daily_runner.py --week N --exam <slug>    # one exam
python pipeline/static_fetch.py --exam upsc-banking --economic-survey 2025 [--extract-only]
python pipeline/news_runner.py [--no-llm]                 # refresh news
python scripts/build_site.py                              # rebuild docs/
python run.py                                             # scheduler (weekly + news, auto-publish)
```
