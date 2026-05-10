"""
Module 1 — Question Scraper
Scrapes RBI Grade B Phase 1 General Awareness questions for 2023, 2024, 2025
from EduTap (PDF + web), AffairsCloud, and Oliveboard.
"""

import json
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import pdfplumber
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    AFFAIRSCLOUD_BASE,
    EDUTAP_GA_PDF_URL,
    EDUTAP_YEAR_URLS,
    FUZZY_THRESHOLD,
    OLIVEBOARD_BLOG_BASE,
)

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_PDF_PATH = BASE_DIR / "data" / "raw" / "edutap_ga.pdf"
RAW_Q_DIR = BASE_DIR / "data" / "questions" / "raw"
FINAL_OUTPUT = BASE_DIR / "data" / "questions" / "all_ga.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

YEARS = [2023, 2024, 2025]

# Exact PDF page ranges (1-indexed) discovered by inspection.
# Each year's section has question pages and separate answer-key pages.
YEAR_PAGE_RANGES = {
    2023: {"questions": (46, 66), "answers": (67, 68)},
    2024: {"questions": (70, 89), "answers": (90, 91)},
    2025: {"questions": (93, 111), "answers": (112, 113)},
}

# Patterns to strip from extracted page text before parsing
_STRIP_RE = re.compile(
    r"^(?:RBI Grade B 20\d\d General Awareness - Recollected Questions.*|General Awareness)$",
    re.MULTILINE,
)
# Options start with a single capital letter followed by ". "
_OPT_RE = re.compile(r"^([A-E])\.\s+(.+)", re.IGNORECASE)
# Questions start with Q<number>.
_Q_SPLIT_RE = re.compile(r"\n(?=Q\d+\.)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 20) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  [WARN] GET {url} failed: {e}")
        return None


def _normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_duplicate(q_text: str, existing: list[dict], threshold: float = FUZZY_THRESHOLD) -> bool:
    for item in existing:
        ratio = SequenceMatcher(None, q_text.lower(), item["question"].lower()).ratio()
        if ratio >= threshold:
            return True
    return False


def _make_question(year, question, options, answer, source, source_url) -> dict:
    return {
        "year": year,
        "question": _normalize_question(question),
        "options": [o.strip() for o in options],
        "answer": answer,
        "source": source,
        "source_url": source_url,
    }


def _save_raw(source: str, year: int, questions: list[dict]) -> None:
    RAW_Q_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_Q_DIR / f"{source}_{year}.json"
    with open(path, "w") as f:
        json.dump(questions, f, indent=2)
    print(f"  Saved {len(questions)} questions → {path}")


# ---------------------------------------------------------------------------
# Strategy A — Download PDF and parse
# ---------------------------------------------------------------------------

def download_pdf() -> bool:
    RAW_PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
    if RAW_PDF_PATH.exists():
        print(f"  PDF already exists at {RAW_PDF_PATH}, skipping download.")
        return True
    print(f"  Downloading EduTap GA PDF from {EDUTAP_GA_PDF_URL} ...")
    r = _get(EDUTAP_GA_PDF_URL, timeout=60)
    if r is None:
        return False
    with open(RAW_PDF_PATH, "wb") as f:
        f.write(r.content)
    print(f"  PDF saved ({len(r.content)//1024} KB)")
    return True


def _pages_text(pdf, start_page: int, end_page: int) -> str:
    """Concatenate text from PDF pages [start_page, end_page] (1-indexed)."""
    parts = []
    for i in range(start_page - 1, end_page):
        t = pdf.pages[i].extract_text() or ""
        t = _STRIP_RE.sub("", t)
        parts.append(t)
    return "\n".join(parts)


def _parse_answer_key(text: str) -> dict[int, str]:
    """Parse the answer key table into {question_number: answer_letter}.

    The table format per line is: '1 E  21 C  41 A  61 C'
    """
    answers: dict[int, str] = {}
    pair_re = re.compile(r"\b(\d{1,2})\s+([A-E])\b")
    for line in text.split("\n"):
        for num_str, letter in pair_re.findall(line):
            answers[int(num_str)] = letter
    return answers


def _parse_questions_from_text(
    text: str, year: int, answer_map: dict[int, str], source_url: str
) -> list[dict]:
    """Parse all Q\d+. blocks from concatenated page text."""
    questions = []
    blocks = _Q_SPLIT_RE.split(text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        m = re.match(r"^Q(\d+)\.\s*(.+)", block, re.DOTALL)
        if not m:
            continue

        q_num = int(m.group(1))
        body = m.group(2)

        lines = [ln.strip() for ln in body.split("\n") if ln.strip()]

        q_lines: list[str] = []
        options: list[str] = []
        cur_letter: str | None = None
        cur_opt: list[str] = []

        for line in lines:
            om = _OPT_RE.match(line)
            if om:
                if cur_letter:
                    options.append(f"{cur_letter}. {' '.join(cur_opt)}")
                cur_letter = om.group(1).upper()
                cur_opt = [om.group(2).strip()]
            elif cur_letter:
                # continuation line of the current option
                cur_opt.append(line)
            else:
                q_lines.append(line)

        if cur_letter:
            options.append(f"{cur_letter}. {' '.join(cur_opt)}")

        question_text = " ".join(q_lines).strip()
        answer = answer_map.get(q_num, "")

        if question_text and len(options) >= 2:
            questions.append(
                _make_question(year, question_text, options, answer, "edutap_pdf", source_url)
            )

    return questions


def parse_pdf_questions() -> list[dict]:
    if not RAW_PDF_PATH.exists():
        return []

    print("  Parsing PDF with pdfplumber ...")
    all_questions: list[dict] = []
    try:
        with pdfplumber.open(RAW_PDF_PATH) as pdf:
            for year, ranges in YEAR_PAGE_RANGES.items():
                q_start, q_end = ranges["questions"]
                a_start, a_end = ranges["answers"]

                q_text = _pages_text(pdf, q_start, q_end)
                a_text = _pages_text(pdf, a_start, a_end)
                answer_map = _parse_answer_key(a_text)

                qs = _parse_questions_from_text(q_text, year, answer_map, str(EDUTAP_GA_PDF_URL))
                print(f"    {year}: {len(qs)} questions parsed (answer map: {len(answer_map)} entries)")
                all_questions.extend(qs)
    except Exception as e:
        print(f"  [ERROR] PDF parse failed: {e}")
        return []

    print(f"  Total parsed from PDF: {len(all_questions)}")
    return all_questions


# ---------------------------------------------------------------------------
# Strategy B — Scrape EduTap year pages
# ---------------------------------------------------------------------------

def _extract_mcqs_from_soup(soup: BeautifulSoup, year: int, source_url: str) -> list[dict]:
    questions = []
    article = soup.find("article") or soup.find("div", class_=re.compile(r"entry|content|post", re.I))
    if article is None:
        article = soup

    # Find all paragraphs / divs containing question patterns
    all_text = article.get_text("\n")
    blocks = re.split(r"\n(?=Q?\d{1,3}[.)]\s)", all_text)

    opt_re = re.compile(r"^([A-Ea-e])[.)]\s*(.+)", re.IGNORECASE)
    for block in blocks:
        lines = [l.strip() for l in block.strip().split("\n") if l.strip()]
        if not lines:
            continue
        first = lines[0]
        q_match = re.match(r"^Q?\d{1,3}[.)]\s*(.+)", first)
        if not q_match:
            continue

        q_text = q_match.group(1).strip()
        options = []
        answer = ""
        q_extra = []

        for ln in lines[1:]:
            om = opt_re.match(ln)
            if om:
                options.append(f"{om.group(1).upper()}. {om.group(2).strip()}")
            elif re.match(r"(?:Ans(?:wer)?|Correct)[:\s]+([A-Ea-e])", ln, re.I):
                am = re.search(r"[A-Ea-e]", ln, re.I)
                if am:
                    answer = am.group(0).upper()
            elif not options:
                q_extra.append(ln)

        if q_extra:
            q_text = q_text + " " + " ".join(q_extra)

        if q_text and len(options) >= 2:
            questions.append(
                _make_question(year, q_text, options, answer, "edutap_web", source_url)
            )

    return questions


def scrape_edutap_web() -> dict[int, list[dict]]:
    results: dict[int, list[dict]] = {}
    for year, url in EDUTAP_YEAR_URLS.items():
        print(f"  Scraping EduTap web for {year}: {url}")
        r = _get(url)
        if r is None:
            results[year] = []
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        qs = _extract_mcqs_from_soup(soup, year, url)
        print(f"    Found {len(qs)} questions for {year}")
        results[year] = qs
    return results


def scrape_edutap() -> dict[int, list[dict]]:
    """Run Strategy A; if < 30 questions total, also run Strategy B and merge."""
    all_results: dict[int, list[dict]] = {y: [] for y in YEARS}

    ok = download_pdf()
    pdf_qs = parse_pdf_questions() if ok else []

    # Group PDF questions by year
    for q in pdf_qs:
        yr = q["year"]
        if yr in all_results:
            all_results[yr].append(q)

    total_pdf = sum(len(v) for v in all_results.values())
    print(f"  Strategy A total: {total_pdf} questions")

    if total_pdf < 30:
        print("  Strategy A insufficient — running Strategy B (web scrape)...")
        web_results = scrape_edutap_web()
        for yr, qs in web_results.items():
            for q in qs:
                if not _is_duplicate(q["question"], all_results[yr]):
                    all_results[yr].append(q)

    return all_results


# ---------------------------------------------------------------------------
# Source 2 — AffairsCloud
# ---------------------------------------------------------------------------

def _search_affairscloud(query: str) -> list[str]:
    """Return candidate page URLs from AffairsCloud for a query."""
    search_url = f"{AFFAIRSCLOUD_BASE}/?s={requests.utils.quote(query)}"
    r = _get(search_url)
    if r is None:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    urls = []
    for a in soup.select("h2 a, h3 a, .entry-title a"):
        href = a.get("href", "")
        if href and "affairscloud.com" in href:
            urls.append(href)
    return urls[:5]


def scrape_affairscloud() -> dict[int, list[dict]]:
    results: dict[int, list[dict]] = {y: [] for y in YEARS}
    for year in YEARS:
        query = f"RBI Grade B {year} GA questions"
        print(f"  Searching AffairsCloud: '{query}'")
        urls = _search_affairscloud(query)
        if not urls:
            print(f"    No results found for {year}")
            continue
        for url in urls:
            print(f"    Fetching {url}")
            r = _get(url)
            if r is None:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            qs = _extract_mcqs_from_soup(soup, year, url)
            print(f"      Found {len(qs)} questions")
            for q in qs:
                q["source"] = "affairscloud"
                if not _is_duplicate(q["question"], results[year]):
                    results[year].append(q)
            time.sleep(1)
    return results


# ---------------------------------------------------------------------------
# Source 3 — Oliveboard
# ---------------------------------------------------------------------------

def _search_oliveboard(query: str) -> list[str]:
    search_url = f"{OLIVEBOARD_BLOG_BASE}?s={requests.utils.quote(query)}"
    r = _get(search_url)
    if r is None:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    urls = []
    for a in soup.select("h2 a, h3 a, .entry-title a, article a"):
        href = a.get("href", "")
        if href and "oliveboard.in" in href and href not in urls:
            urls.append(href)
    return urls[:5]


def scrape_oliveboard() -> dict[int, list[dict]]:
    results: dict[int, list[dict]] = {y: [] for y in YEARS}
    for year in YEARS:
        query = f"RBI Grade B General Awareness questions {year}"
        print(f"  Searching Oliveboard: '{query}'")
        urls = _search_oliveboard(query)
        if not urls:
            print(f"    No results found for {year}")
            continue
        for url in urls:
            print(f"    Fetching {url}")
            r = _get(url)
            if r is None:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            qs = _extract_mcqs_from_soup(soup, year, url)
            print(f"      Found {len(qs)} questions")
            for q in qs:
                q["source"] = "oliveboard"
                if not _is_duplicate(q["question"], results[year]):
                    results[year].append(q)
            time.sleep(1)
    return results


# ---------------------------------------------------------------------------
# Merge + dedup across all sources
# ---------------------------------------------------------------------------

def merge_and_dedup(*source_maps: dict[int, list[dict]]) -> list[dict]:
    merged: list[dict] = []
    for source_map in source_maps:
        for year_qs in source_map.values():
            for q in year_qs:
                if not _is_duplicate(q["question"], merged):
                    merged.append(q)
    return merged


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("RBI Grade B GA Question Scraper")
    print("=" * 60)

    print("\n[1/3] EduTap ...")
    edutap_results = scrape_edutap()
    for year, qs in edutap_results.items():
        _save_raw("edutap", year, qs)

    print("\n[2/3] AffairsCloud ...")
    ac_results = scrape_affairscloud()
    for year, qs in ac_results.items():
        _save_raw("affairscloud", year, qs)

    print("\n[3/3] Oliveboard ...")
    ob_results = scrape_oliveboard()
    for year, qs in ob_results.items():
        _save_raw("oliveboard", year, qs)

    print("\n[Merging & deduplicating] ...")
    all_qs = merge_and_dedup(edutap_results, ac_results, ob_results)

    FINAL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(FINAL_OUTPUT, "w") as f:
        json.dump(all_qs, f, indent=2)

    print(f"\nFinal output: {FINAL_OUTPUT}")
    print("\n--- Summary ---")
    for year in YEARS:
        year_qs = [q for q in all_qs if q["year"] == year]
        et = sum(1 for q in year_qs if "edutap" in q["source"])
        ac = sum(1 for q in year_qs if q["source"] == "affairscloud")
        ob = sum(1 for q in year_qs if q["source"] == "oliveboard")
        print(f"  {year}: EduTap={et}  AffairsCloud={ac}  Oliveboard={ob}  Total={len(year_qs)}")
    print(f"  TOTAL after dedup: {len(all_qs)}")


if __name__ == "__main__":
    main()
