Build a Python project called `grade_b_prep` with the following structure:
Module 1 — Question Scraper (`scrapers/question_scraper.py`)
Scrape RBI Grade B Phase 1 General Awareness questions for 2023, 2024, and 2025 from the following sources. For each source, only extract GA/General Awareness questions — skip Quant, Reasoning, and English.
Source 1 — EduTap (primary, two strategies):

Strategy A: Download the GA PDF directly from `https://edutap.in/wp-content/uploads/2026/04/RBI-Grade-B-Phase-1-PYQs-2021-2025-Genera-Awareness-book.pdf`, save to `data/raw/edutap_ga.pdf`, then extract text using `pdfplumber` and parse MCQ questions (look for numbered questions with A/B/C/D or a/b/c/d options).
Strategy B: Scrape the individual year pages using `requests` + `BeautifulSoup`:

2023: `https://edutap.in/rbi-grade-b/previous-year-questions/rbi-grade-b-2023-ga-pyqs/`
2024: `https://edutap.in/rbi-grade-b/previous-year-questions/rbi-grade-b-2024-pyqs/` (find the GA section on the page)
2025: `https://edutap.in/rbi-grade-b/previous-year-questions/rbi-grade-b-2025-pyqs/` (if it exists)
Extract all question blocks containing the question text and options A–E from the article body.


Run Strategy A first; if the PDF has fewer than 30 parseable questions, also run Strategy B and merge results.

Source 2 — AffairsCloud (fallback):

Search and scrape `https://affairscloud.com` for pages matching "RBI Grade B 2023 GA questions", "RBI Grade B 2024 GA questions", "RBI Grade B 2025 GA questions" using `requests` + `BeautifulSoup`. Extract question blocks with options.

Source 3 — Oliveboard blog (fallback):

Search and scrape `https://www.oliveboard.in/blog/` for pages matching "RBI Grade B General Awareness questions 2023/2024/2025". Extract question text and options.

After scraping all sources, deduplicate by fuzzy-matching question text (use `difflib.SequenceMatcher`, threshold 0.85). Normalize each question to this schema:
```
json{
  "year": 2024,
  "question": "...",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "answer": "B",
  "source": "edutap",
  "source_url": "..."
}
```
Save raw per-source results to `data/questions/raw/{source}_{year}.json`. Save the final merged + deduped output to `data/questions/all_ga.json`. Print a summary: total questions per year per source, total after dedup.
Module 2 — PIB Scraper (`scrapers/pib_scraper.py`)
Scrape `https://www.pib.gov.in/AllRelease.aspx?MenuId=286&reg=6&lang=1` for a given month and year. Filter press releases by date. For each release, fetch the full text from its detail page (`PressReleseDetail.aspx?PRID=XXXXX`). Return a list of dicts: `{title, date, url, content}`. Accept `year` (int) and `month` (int) as arguments. Add a 1-second delay between detail page fetches. Use a browser-like User-Agent header.
Module 3 — RBI Scraper (`scrapers/rbi_scraper.py`)
Scrape RBI circulars for a given month and year using two approaches:

Primary: Use `playwright` (async, headless Chromium) to navigate `https://www.rbi.org.in/scripts/bs_circularindexdisplay.aspx`, click the correct year accordion, then click the correct month link, and extract the resulting table rows: `{circular_number, date, department, subject, url}`.
Also scrape RBI press releases from `https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx` for the same month by fetching and parsing the HTML table.
Merge both into one list. Accept year (int) and month (int) as arguments.

Module 4 — Daily Pipeline (pipeline/daily_runner.py)
Accept --day N argument (1–12). Use this day-to-month mapping:
```
python
DAY_MAP = {
    1: (2025, 5),   2: (2025, 6),   3: (2025, 7),   4: (2025, 8),
    5: (2025, 9),   6: (2025, 10),  7: (2025, 11),  8: (2025, 12),
    9: (2026, 1),  10: (2026, 2),  11: (2026, 3),  12: (2026, 4)
}
```
Steps:

1. Resolve `(year, month)` from day number.
2. Run PIB and RBI scrapers in parallel using `concurrent.futures.ThreadPoolExecutor`.
3. Merge all content into a single text blob, truncated to 12,000 words if needed.
4. Call Ollama at `http://localhost:11434/api/generate` with model `qwen3.5:cloud` (fallback to `qwen3.5:9b` if the first fails). Use `stream: false`. Send this prompt:
```
System: You are an expert assistant helping a student prepare for the RBI Grade B Phase 1 General Awareness exam. Be concise and exam-focused.

User: Here is raw content from PIB press releases and RBI circulars for {month_name} {year}. Do two things:

PART 1 - MONTHLY SUMMARY:
Write a structured markdown summary of the most GA-relevant events, policies, schemes, economic data, appointments, awards, and RBI actions from this month. Use sections: ## RBI & Monetary Policy, ## Government Schemes & Policies, ## Economy & Markets, ## Appointments & Awards, ## International. Keep each section to 5-8 bullet points max.

PART 2 - PRACTICE QUESTIONS:
Generate exactly 15 MCQ questions in RBI Grade B Phase 1 style based on this month's content. Each question must have 4 options (A-D) and the correct answer. Format strictly as:
Q1. [question]
A. [option] B. [option] C. [option] D. [option]
Answer: [letter]

Raw content:
{content}
```
5. Split the Ollama response into Part 1 (summary) and Part 2 (questions) by looking for "PART 2" in the response.
6. Save summary to `data/summaries/YYYY-MM.md` with a header showing the date and month processed.
7. Parse the 15 questions and save to `data/questions/generated/YYYY-MM-qs.json` as a list of `{question, options, answer}` dicts.
8. Print a clean log of the entire run with timings.

Module 5 — Scheduler (`run.py`)
Read `data/state.json` (create if missing, default `{"current_day": 1}`). On each run, get `current_day`, run `daily_runner.py --day {current_day}` as a subprocess, increment `current_day` in state.json, then `schedule` the next run using the schedule library to fire at 3:00 PM the following day. Stop after day 12 and print "All 12 months processed. Happy studying! 🎉". Include a `--run-now` flag to skip the scheduler and immediately run today's day for testing.
Also create:

- `requirements.txt`: `requests`, `beautifulsoup4`, `playwright`, `pdfplumber`, `schedule`, `ollama`
- `config.py`: Ollama URL, model name, DAY_MAP, and source URLs as constants
- `README.md` with: install Ollama → `ollama pull qwen3.5:cloud` → `pip install -r requirements.txt` → `playwright install chromium` → run `python scrapers/question_scraper.py` first → then `python run.py` for auto mode or `python pipeline/daily_runner.py --day 1` for manual