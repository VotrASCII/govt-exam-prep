# Govt Exams — GA Prep Tool

Automated scraper and AI study assistant for the General Awareness papers of
India's top government exams. Built first for **RBI Grade B Phase 1** and now a
**multi-exam** platform — RBI Grade B and UPSC / Banking are live, with SEBI Grade A
and NABARD Grade A scaffolded.

**Live site:** https://votrascii.github.io/govt-exam-prep/

## What it does

1. **Scrapes past GA questions** (2023–2025) from EduTap, AffairsCloud, and Oliveboard
2. **Scrapes each exam's own sources** — PIB press releases and RBI circulars for RBI
   Grade B; broad all-ministry PIB and the Economic Survey for UPSC / Banking — with
   local caching
3. **Generates AI summaries + practice MCQs** for weekly or monthly periods using Ollama,
   with the topic and question-type mix tuned per exam (see *Multi-exam architecture*)
4. **Schedules itself** — every **Monday 00:00** it ingests the just-completed week
   (Mon–Sun) for **all active exams**, then pushes so GitHub Pages redeploys; the news
   digest refreshes **daily at 00:00**
5. **Publishes a minimalist website** ([live here](https://votrascii.github.io/govt-exam-prep/))
   **categorised by exam**, each with descriptive summaries and an in-browser practice quiz
6. **Curates exam-relevant news** from ET / Mint / Hindustan Times / Business Standard
   (via RSS), tagged by exam and shown as self-contained summaries — the headline list
   is today + yesterday, with the rest of the week tucked into a collapsible *In this week*

## Multi-exam architecture

Every exam is declared once in `config.py` under the `EXAMS` registry — its display
name, the **sources** it draws on, its **taxonomy** file, and an `active` flag. The
pipeline, prompt builder, and website all read this registry, so adding an exam means
appending an entry (plus its scraper and taxonomy) rather than editing the pipeline.

| Exam | Status | Sources | Taxonomy |
|------|--------|---------|----------|
| RBI Grade B | **Active** | PIB + RBI circulars | `data/patterns/rbi-grade-b.json` |
| UPSC / Banking | **Active (content in progress)** | all-ministry PIB (weekly) + Economic Survey (reference) | `data/patterns/upsc-banking.json` |
| SEBI Grade A | Scaffolded | SEBI + PIB + RBI | `data/patterns/sebi-grade-a.json` |
| NABARD Grade A | Scaffolded | NABARD + PIB + RBI | `data/patterns/nabard-grade-a.json` |

**Per-exam GA weightage (#question pattern).** Each taxonomy carries a `prompt_profile`
that drives the summary sections and the **topic + question-style distribution** for
that exam. RBI Grade B uses 5 options (A–E) and is current-affairs/banking heavy; UPSC
uses 4 options (A–D) and is dominated by "Consider the following statements" items. The
weightage is derived empirically from each exam's previous-year GA papers:

```bash
# Tally PYQ topics → recompute the exam's topic distribution in its taxonomy
python scripts/derive_weightage.py --exam rbi-grade-b --dry-run
python scripts/derive_weightage.py --exam upsc-banking
```

Drop an exam's previous-year GA papers (as `{"question","options",...}` JSON) into
`data/questions/pyq/<exam-slug>/` and re-run `derive_weightage.py` to refresh its mix.
Until that is done, an exam uses the documented research-default weightage in its taxonomy.

### Reference sources — Economic Survey (yearly)

The Economic Survey is foundational, self-contained, exam-critical reading, so it is
kept **separate** from the weekly current-affairs papers: it gets its **own stored
section-wise summary and its own dedicated quiz**, rendered as a standalone section on
the exam page (`docs/static/<exam>/economic-survey-<year>.html`). Weekly papers are
built from that week's material only — Economic Survey facts never mix into them — so
"what I learned this week" stays cleanly distinct from foundational ES knowledge.

These PDFs are **downloaded, text-extracted (pdfplumber), and summarised + quizzed
automatically** — and the scheduler keeps them current with no manual step:

```bash
# One command: download + extract + summarise the latest Economic Survey and the
# current month's Yojana for an exam (idempotent — skips editions already done).
python pipeline/static_fetch.py --exam upsc-banking

# Specific editions:
python pipeline/static_fetch.py --exam upsc-banking --economic-survey 2025
python pipeline/static_fetch.py --exam upsc-banking --yojana 2026-06
```

`run.py` runs this on startup and **daily at 05:30**, so a new Economic Survey (yearly)
or Yojana issue (monthly) is picked up on its own; failed downloads simply retry the
next day until the PDF is reachable.

**If a download fails** (gov sites are flaky/JS-heavy), just drop the PDF into
`data/static/<exam>/pdfs/` named so the edition is recognisable (e.g.
`econsurvey-2025.pdf`, `yojana-2026-06.pdf`) and re-run with `--extract-only` — the
extractor ingests whatever is there:

```bash
python pipeline/static_fetch.py --exam upsc-banking --extract-only
```

Under the hood the extracted text is handed to `static_runner.py`. The Economic Survey
(700+ pages) is summarised **section-wise** — each of the standard thematic chapters
(`ECON_SURVEY_SECTIONS`) gets its own independent summary pass, then a **dedicated quiz
of N MCQs per section** (default 30 → ~360 total; `--questions N` to change). You can
also run it directly on a text file via `--from-file`. Output is stored under
`data/static/<exam>/`: a section-wise `.md` summary and a `.quiz.json` of the MCQs
(each tagged with its section, so the site groups them).
The site builder (`load_static_sources` → `render_static_page`) then publishes each
source as its own page with the summary + quiz, linked under **Reference sources** on
the exam page. Re-running is idempotent (it overwrites that edition's files).

### Study cycles & archive

The site shows one **study cycle** at a time. A cycle starts on the **last Monday of
December** (29 Dec 2025 = Week 1 of the 2025–26 cycle) and runs ~52 weeks. Weeks before
the current cycle move into a per-exam **Archive** section, grouped by cycle. This
recurs automatically: when the next cycle begins each December, the previous cycle rolls
into the archive with no manual migration (`config.current_cycle_start` /
`cycle_start_for` / `cycle_label`).

### Repository security

`main` is protected: every change requires a pull request with an approving review from
the code owner (`.github/CODEOWNERS` → the repo owner), stale reviews are dismissed, and
force-pushes/deletions are blocked. The repo is owner-only (no other collaborators), so
no other account can push; any future collaborator must open a PR the owner approves.

## Setup

### 1. Install Ollama and pull the models

The pipeline calls a strong primary model and falls back to small local models if it
is unavailable (see `OLLAMA_MODELS` in `config.py`). Defaults:

```bash
# Install from https://ollama.com
ollama pull gpt-oss:20b-cloud   # primary (Ollama Cloud) — summaries + MCQs
ollama pull qwen3.5:2b           # local fallback
ollama pull qwen3.5:0.8b         # last-resort fallback
```

Cloud models (`*-cloud`) run via Ollama's hosted tier and don't need to appear in
`ollama list` to work. Swap in any installed model by editing `OLLAMA_MODELS` or
setting the `OLLAMA_MODELS` env var (see *Configuration*).

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browser

```bash
playwright install chromium
```

## Usage

### Step 1 — Scrape past GA questions (do this once)

```bash
python scrapers/question_scraper.py
```

This will:
- Download the EduTap GA PDF and extract MCQs
- Fall back to web scraping if the PDF yields fewer than 30 questions
- Scrape AffairsCloud and Oliveboard as additional sources
- Deduplicate and save everything to `data/questions/all_ga.json`

### Step 2 — Run the pipeline

**Auto mode** — catches up any missed weeks + refreshes news now, then schedules the
**weekly run (Mon 00:00, all exams)** and the **daily news refresh (00:00)**, pushing
after each so the live site redeploys:

```bash
python run.py
```

**Manual weekly mode**:

```bash
python pipeline/daily_runner.py --week 28 --all-exams          # every active exam
python pipeline/daily_runner.py --week 28                      # RBI Grade B (default)
python pipeline/daily_runner.py --week 28 --exam upsc-banking  # one exam
```

`--all-exams` runs each active exam independently with **retry + skip-on-failure**: a
transient failure is retried a few times, and if an exam still fails it is logged and
skipped so the rest of the pipeline continues. For a week that's thin on one source
(e.g. few PIB items), questions are built from whatever source(s) *do* have content —
generation is only refused when every source is title-only.

`--exam` selects which exam's pipeline to run (weekly mode only). Each exam pulls
its own sources (see *Multi-exam architecture*), uses its own GA weightage, and
writes to `data/summaries/<exam-slug>/` and `data/questions/generated/<exam-slug>/`,
which the site then renders on that exam's page. The default exam (`rbi-grade-b`)
keeps the original flat output layout. Run `scripts/build_site.py` afterwards to
publish the new content.

To generate an exam's **reference sources** (e.g. the Economic Survey) — a standalone
summary + dedicated quiz, separate from the weekly papers — see *Reference sources*
above (`python pipeline/static_fetch.py --exam upsc-banking`).

**Backfill missing weekly outputs from available cached content**:

Use this when the strict weekly runner skipped a week because one source did
not have enough detail coverage, but there are still usable PIB/RBI detail
items in `data/scraped/`.

```bash
python scripts/backfill_available_weeks.py --all-missing
python scripts/backfill_available_weeks.py --week 12 --week 16
python scripts/backfill_available_weeks.py --all-missing --dry-run
```

The backfill script writes to the same weekly summary/question paths, but it
filters out title-only or weak-content items and asks the model to generate
questions only from the facts available in the remaining detail content.

**Manual monthly mode**:

```bash
python pipeline/daily_runner.py --day 1
```

**Force-run a slot immediately** (without waiting for the schedule):

```bash
python run.py --run-now    # process the current completed week now (all exams) + publish
python run.py --news-now   # refresh + publish the news digest now
```

## Week numbering — two systems, one source of truth

There are two week numbers and it's worth keeping them straight:

- **Pipeline index (`--week N`)** — a simple 1-based counter of 7-day blocks from
  `WEEK_RANGE_START` (`2025-12-01`). So `--week 1` = 1–7 Dec 2025, `--week 28` =
  8–14 Jun 2026. This is what you pass on the command line and what the scheduler
  tracks in `data/state.json`. It is open-ended: leave `WEEK_RANGE_END = ""` (the
  default) for a rolling schedule, or set a date (e.g. `"2026-05-31"`) to cap it.
- **Display number (study cycle)** — what the **site** shows. Weeks are regrouped
  into a yearly **study cycle** that starts on the **last Monday of December** and
  renumbered from Week 1 within that cycle, so **Week 1 of the 2025–26 cycle is the
  week of 29 Dec 2025**. Weeks before the current cycle roll into each exam's
  **Archive** automatically, and a fresh Week 1 begins every December with no manual
  migration (`config.current_cycle_start` / `cycle_start_for` / `cycle_label`).

The pipeline index and the dates are the durable identity (files are keyed by date
range, e.g. `2026-06-08_to_2026-06-14`); the display number is derived at build time.

The scheduler only advances after a week is complete. It catches any backlog up at
startup, then waits for the **Monday 00:00** trigger to process the week that just
ended. If every exam fails for a week (e.g. a network outage), it stays on that week
and retries on the next trigger rather than skipping it.

## Output files

All outputs live under `data/` (gitignored — only the rendered `docs/` site is
committed). The **default exam** (`rbi-grade-b`) keeps the original flat layout; every
other exam is namespaced under its `<exam-slug>`.

| Path | Contents |
|------|----------|
| `data/questions/all_ga.json` | All scraped GA MCQs (deduplicated) |
| `data/questions/pyq/<exam-slug>/` | Previous-year GA papers used to derive per-exam weightage |
| **Weekly (default exam)** | |
| `data/summaries/YYYY-MM-DD_to_YYYY-MM-DD.md` | Weekly GA summary (markdown) |
| `data/questions/generated/YYYY-MM-DD_to_YYYY-MM-DD-qs.json` | AI-generated weekly MCQs |
| `data/summaries/pdf/…-summary.pdf`, `data/questions/pdf/…-qs.pdf` | Shareable weekly PDFs |
| **Weekly (other exams)** | |
| `data/summaries/<exam-slug>/<key>.md` | Per-exam weekly summary |
| `data/questions/generated/<exam-slug>/<key>-qs.json` | Per-exam weekly MCQs |
| **Reference sources (Economic Survey)** | |
| `data/static/<exam-slug>/pdfs/` | Downloaded/dropped source PDFs |
| `data/static/<exam-slug>/sources/<kind>-<key>.txt` | Extracted PDF text |
| `data/static/<exam-slug>/<kind>-<key>.md` | Section-wise summary |
| `data/static/<exam-slug>/<kind>-<key>.json` | Topic-tagged segments |
| `data/static/<exam-slug>/<kind>-<key>.quiz.json` | Dedicated quiz MCQs |
| **Monthly mode (`--day`)** | |
| `data/summaries/YYYY-MM.md`, `data/questions/generated/YYYY-MM-qs.json` | Monthly summary + MCQs |
| **Caches & state** | |
| `data/scraped/<period>/…` , `data/scraped/<exam-slug>/<key>/…` | Cached source scrapes |
| `data/chunk_notes/<period-key>/chunk-NNN.json` | Cached condensed notes for oversized periods |
| `data/llm_raw/<key>-*.md` | Raw Ollama responses (for debugging/recovery) |
| `data/raw/edutap_ga.pdf` | Downloaded EduTap GA PDF |
| `data/news/latest.json`, `data/news/YYYY-MM-DD.json` | News digest + dated snapshots |
| `data/news/seen.json` | Dedup ledger — items already summarised, so daily runs only LLM new ones |
| `data/state.json` | Scheduler state (current pipeline week) |

The daily runner checks the relevant `data/scraped/` cache before scraping. If cached source data exists, it skips that scraper and goes straight to prompt building and Ollama. To force a fresh scrape:

```bash
python pipeline/daily_runner.py --week 1 --refresh-cache
```

If the scraped period is too large for the model context, the runner automatically splits the source material into chunks, summarizes each chunk into exam-focused notes, caches those notes in `data/chunk_notes/`, and builds the final summary/MCQ prompt from the condensed notes. This lets large periods use the whole scrape without silently truncating the tail.

### Optional: email the PDFs (manual only)

> Emailing is **no longer part of the scheduled pipeline** — the live site is the
> delivery mechanism now. The code and CLI flags remain for ad-hoc manual use; the
> scheduler never emails (it runs with no recipients).

To email the generated summary and question PDFs after a *manual* run, copy `.env.example` to `.env` and fill in your SMTP credentials:

```bash
cp .env.example .env
```

Then edit `.env`:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_16_character_gmail_app_password
SMTP_FROM=your_email@gmail.com
QUESTIONS_EMAIL_TO=recipient@example.com
```

Run normally to use `QUESTIONS_EMAIL_TO`, or override recipients with `--email-to`. Use commas for multiple recipients. The email includes both PDFs as attachments:

```bash
python pipeline/daily_runner.py --week 1
python pipeline/daily_runner.py --week 1 --email-to "one@example.com,two@example.com"
```

To email already-generated PDFs without rerunning scraping or Ollama:

```bash
python pipeline/daily_runner.py --week 1 --email-existing
python pipeline/daily_runner.py --week 1 --email-existing --email-to "one@example.com,two@example.com"
```

## News pipeline (In the news)

A second, parallel pipeline ingests **exam-relevant business/economy news** and
publishes it as an "In the news" page on the site, with cited sources and per-exam
relevance tags.

- **Sources:** Economic Times, Mint, Hindustan Times — read via their public **RSS
  feeds** — plus **Business Standard**, whose own RSS is Akamai-blocked (403) so it is
  ingested via a Google-News site-restricted feed that links back to the original BS
  article.
- **What is stored:** only RSS metadata — headline, source, date, and a short blurb.
  Full copyrighted article bodies are **never** scraped or republished.
- **Self-contained summaries:** Ollama rewrites each item into an original 2–3
  sentence, exam-focused summary shown inline on the site (no outbound links) and
  credited to the originating outlet. Without Ollama, the RSS blurb is used as-is.
- **Headline window + weekly fold:** the digest fetches a rolling week
  (`NEWS_LOOKBACK_DAYS = 7`), but the site shows only the last
  `NEWS_HEADLINE_DAYS + 1` days (today + yesterday) in the main list; the rest of the
  week sits in a collapsible **In this week** section. So anything that missed
  yesterday's list surfaces today, stale items roll off, and nothing within the week is
  lost. Widen the fetch with `--days` for a one-off catch-up.
- **Exam tagging:** each item is screened for relevance to **RBI Grade B, SEBI
  Grade A, NABARD Grade A, and UPSC / Banking**. A keyword heuristic provides the
  baseline; Ollama refines the tags and topic when reachable.
- **Runs daily, no wasted effort:** the news refresh fires every day at 00:00, but a
  dedup ledger (`data/news/seen.json`, keyed by URL) remembers items already
  summarised, so each run spends the LLM **only on genuinely new articles** — the same
  story isn't re-summarised day after day. The ledger is pruned to the lookback window.

Run it:

```bash
python pipeline/news_runner.py            # fetch, tag (LLM if available), save
python pipeline/news_runner.py --no-llm   # heuristic tagging only (fast, no Ollama)
python pipeline/news_runner.py --days 14  # widen the lookback window
```

Output:

| Path | Contents |
|------|----------|
| `data/news/latest.json` | Current digest consumed by the site build |
| `data/news/YYYY-MM-DD.json` | Dated snapshot for history |

The site build renders `data/news/latest.json` into `docs/news.html` (filterable by
exam; the filter applies to both the headline list and *In this week*). `run.py`
refreshes the news digest automatically after each weekly cycle; use
`python run.py --build-only --with-news` to refresh it on demand. Configure feeds,
exams, and windows in `config.py` (`NEWS_FEEDS`, `NEWS_EXAMS`, `NEWS_LOOKBACK_DAYS`,
`NEWS_HEADLINE_DAYS`).

## Website

The weekly summaries and MCQs are published as a minimalist static site in `docs/`,
served by GitHub Pages. The site reads directly from `data/summaries/*_to_*.md` and
`data/questions/generated/*-qs.json` — no database, no framework, stdlib Python only.

Build it from existing data:

```bash
python scripts/build_site.py
# or, equivalently, via the scheduler entrypoint:
python run.py --build-only
```

This writes a fast, fully-static site to `docs/`:

| Path | Contents |
|------|----------|
| `docs/index.html` | Overview landing page with an exam card per active exam |
| `docs/exams/<exam-slug>.html` | Per-exam page: current cycle's weeks, **Reference sources**, and an **Archive** of past cycles |
| `docs/weeks/<exam-slug>/<key>.html` | Per-week page: descriptive summary + interactive MCQ quiz |
| `docs/static/<exam-slug>/<kind>-<key>.html` | Reference-source page (e.g. Economic Survey): summary + its own dedicated quiz |
| `docs/news.html` | "In the news" digest (filterable by exam) |
| `docs/assets/style.css`, `docs/assets/app.js` | Minimalist styling + quiz logic |

A persistent top nav links every active exam plus News, so you can switch exams from
any page. The overview page shows an exam card each (RBI Grade B, UPSC / Banking, …);
an exam with no published weeks yet shows a "coming soon" panel. Each week page renders
the summary with topic sections, highlighted figures/dates, ⭐ priority markers, and a
proper table when the model emits one — followed by an in-browser practice quiz (pick an
option to see the correct answer, with a running score). Reference-source pages reuse the
same summary + quiz layout but are listed separately so foundational material stays
distinct from the weekly papers.

The site reads each exam's weekly content from `data/summaries/<exam-slug>/` and
`data/questions/generated/<exam-slug>/`, and its reference sources from
`data/static/<exam-slug>/` (RBI Grade B keeps the original flat layout for backward
compatibility).

### Automatic publishing

In **auto mode** (`python run.py`), every weekly run (Mon 00:00) and every daily news
refresh (00:00) rebuilds `docs/` and **commits + pushes** automatically, so GitHub
Pages redeploys without any manual step — pushing is always on in auto mode. (For the
manual `--run-now` / `--news-now` triggers, add `--publish` to also push.)

```bash
python run.py                      # auto: weekly Mon 00:00 + daily news 00:00, both push
python run.py --run-now --publish  # process the current week now, then push
python run.py --news-now --publish # refresh news now, then push
```

Raw scraped content in `data/` stays gitignored (private); only the rendered `docs/`
site is committed.

### Hosting (GitHub Pages)

The site is already live at **https://votrascii.github.io/govt-exam-prep/**, served by
GitHub Pages from `docs/`. The included `.github/workflows/pages.yml` redeploys it
automatically on every push that touches `docs/`.

Pages is configured with **Source: GitHub Actions** (`build_type: workflow`). This
was a one-time setup; you only need to redo it if you recreate the repo:

- **Public repo:** Pages is free. Enable it via **Settings → Pages → Build and
  deployment → Source: GitHub Actions**, or once with the API:
  `gh api -X POST /repos/<user>/<repo>/pages -f build_type=workflow`.
- **Private repo:** GitHub Pages requires a paid plan (GitHub Pro). Either upgrade,
  make the repo public, or deploy `docs/` to an external static host
  (Cloudflare Pages / Netlify support private repos for free — set the output
  directory to `docs/` with no build command).

> Note: the Actions token cannot *create* a Pages site (it returns 403), so Pages
> must be enabled by a repo admin once before the workflow can deploy. After that
> the workflow just publishes the existing site.

## Configuration

Edit `config.py` to change:
- Ollama URL / model names (`OLLAMA_MODEL_PRIMARY`, `OLLAMA_MODEL_FALLBACK`) and the
  `OLLAMA_MODELS` fallback order, context window, and read timeout
- Large-period chunking via `CHUNK_CONTENT_WORDS` and `CHUNK_SUMMARY_WORDS`
- Source-material budget via `MAX_CONTENT_WORDS` (raised to **90,000** so far more
  source text reaches the model before any truncation → richer, fuller summaries)
- The exam registry via `EXAMS` / `DEFAULT_EXAM` (see *Multi-exam architecture*)
- Weekly range via `WEEK_RANGE_START` and `WEEK_RANGE_END` (the auto schedule itself is
  fixed: weekly Mon 00:00, news daily 00:00 — see *Automatic publishing*)
- News feeds and windows via `NEWS_FEEDS`, `NEWS_EXAMS`, `NEWS_LOOKBACK_DAYS`,
  `NEWS_HEADLINE_DAYS`
- Reference-source (Economic Survey) extraction caps via `STATIC_MAX_WORDS`,
  `STATIC_MAX_PAGES_PER_PDF`, and the source URLs (`ECON_SURVEY_*`)
- Fuzzy dedup threshold (`FUZZY_THRESHOLD`)

You can also override the model order without editing files:

```bash
OLLAMA_MODELS="gpt-oss:20b-cloud,qwen3.5:2b" python pipeline/daily_runner.py --week 28
```
