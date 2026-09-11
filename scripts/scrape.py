"""
Scrapes the Singapore travel knowledge-base sources and saves each as a
clean markdown file (with title/url/scraped_at frontmatter) into
data/raw/, ready for chunking by scripts/ingest.py.

Usage:
    python scripts/scrape.py
"""

import datetime
import re
import sys
from pathlib import Path

import trafilatura
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# visitsingapore.com renders its content inside Shadow DOM web components,
# so static HTML / trafilatura only see nav + cookie banner. Category/detail
# sub-pages (rather than the thin card-index landing pages) have real body
# text reachable via Playwright's inner_text (which pierces shadow roots).
SOURCES = [
    {
        "title": "Wikivoyage - Singapore Travel Guide",
        "url": "https://en.wikivoyage.org/wiki/Singapore",
    },
    {
        "title": "Visit Singapore - Essential Travel Information",
        "url": "https://www.visitsingapore.com/travel-tips/essential-travel-information/",
    },
    {
        "title": "Visit Singapore - 4 Day Itinerary",
        "url": "https://www.visitsingapore.com/travel-tips/travelling-to-singapore/itineraries/4-days-in-singapore/",
    },
    {
        "title": "Visit Singapore - 7 Day Itinerary",
        "url": "https://www.visitsingapore.com/travel-tips/travelling-to-singapore/itineraries/7-days-in-singapore/",
    },
    {
        "title": "Visit Singapore - Things to Do - City in Nature",
        "url": "https://www.visitsingapore.com/things-to-do/top-things-to-do/city-in-nature/",
    },
    {
        "title": "Visit Singapore - Things to Do - Culture and Heritage",
        "url": "https://www.visitsingapore.com/things-to-do/top-things-to-do/culture-heritage/",
    },
    {
        "title": "Visit Singapore - Things to Do - Family Fun",
        "url": "https://www.visitsingapore.com/things-to-do/top-things-to-do/family-fun/",
    },
]

MIN_CONTENT_LEN = 200

# Exact-match lines that are site chrome (nav bar / breadcrumb glue), stripped
# out of the Playwright inner_text() fallback before saving.
NAV_JUNK_LINES = {
    "What's Happening",
    "Neighbourhoods",
    "Things To Do",
    "Travel Tips",
    "GET RECOMMENDATIONS",
    "Global",
    "Home",
    "/",
}
COOKIE_BANNER_MARKER = "We use optional cookies"


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def extract_markdown(html: str) -> str | None:
    return trafilatura.extract(
        html,
        output_format="markdown",
        include_links=False,
        include_images=False,
        include_tables=True,
        favor_recall=True,
    )


def clean_rendered_text(text: str) -> str:
    cutoff = text.find(COOKIE_BANNER_MARKER)
    if cutoff != -1:
        text = text[:cutoff]

    lines = [line for line in text.splitlines() if line.strip() not in NAV_JUNK_LINES]
    # collapse 3+ blank lines down to 1
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return cleaned.strip()


def render_with_browser(url: str) -> str | None:
    """Fallback for JS-rendered pages whose content lives in Shadow DOM."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 2000})
            page.goto(url, wait_until="networkidle", timeout=30000)
            # trigger any scroll-based lazy loading
            for _ in range(15):
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(300)
            text = page.inner_text("body")
            browser.close()
            return clean_rendered_text(text)
    except Exception as e:
        print(f"  Playwright render failed: {e}")
        return None


def scrape_source(source: dict) -> bool:
    title, url = source["title"], source["url"]
    print(f"Fetching: {title} ({url})")

    downloaded = trafilatura.fetch_url(url)
    content = extract_markdown(downloaded) if downloaded else None

    if not content or len(content.strip()) < MIN_CONTENT_LEN:
        print("  Static extraction too thin, retrying with headless browser render...")
        content = render_with_browser(url)

    if not content or len(content.strip()) < MIN_CONTENT_LEN:
        print(f"  FAILED to extract meaningful content from {url}")
        return False

    frontmatter = (
        "---\n"
        f"title: {title}\n"
        f"source_url: {url}\n"
        f"scraped_at: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n"
        "---\n\n"
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{slugify(title)}.md"
    out_path.write_text(frontmatter + content, encoding="utf-8")
    print(f"  Saved -> {out_path.relative_to(OUTPUT_DIR.parent.parent)} ({len(content)} chars)")
    return True


def main():
    results = [scrape_source(source) for source in SOURCES]
    succeeded = sum(results)
    print(f"\n{succeeded}/{len(SOURCES)} sources scraped successfully.")
    if succeeded == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
