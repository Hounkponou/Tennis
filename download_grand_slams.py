"""
Download Grand Slam match data from tennis-data.co.uk.

The site publishes one Excel file per season:
    ATP (men):   http://www.tennis-data.co.uk/{year}/{year}.xlsx
    WTA (women): http://www.tennis-data.co.uk/{year}w/{year}.xlsx

Older seasons are served in the legacy .xls format; recent ones are .xlsx.
Each file contains every tour match for the season. Grand Slam matches are
the rows where the category column == "Grand Slam". That column is called
"Series" in the ATP files and "Tier" in the WTA files (Australian Open,
French Open, Wimbledon, US Open).

The server is a bit flaky and rate-limits aggressive clients (it returns an
HTML "temporarily unavailable" page instead of the file), so this script
retries with backoff and caches raw downloads locally. Re-running only
fetches the years it is still missing.

Outputs (under ./data):
  raw/                  full season files as downloaded
  grand_slams/          per-year/tour CSVs of just the Grand Slam matches
  grand_slams_all.csv   everything combined into one file
"""

import io
import time
from pathlib import Path

import pandas as pd
import requests

BASE = "http://www.tennis-data.co.uk"
OUT = Path(__file__).parent / "data"
RAW_DIR = OUT / "raw"
GS_DIR = OUT / "grand_slams"

# Data availability on the site: ATP from 2000, WTA from 2007.
ATP_START = 2000
WTA_START = 2007
END_YEAR = 2026  # inclusive; bump this as new seasons are published

TOURS = {"ATP": "", "WTA": "w"}  # url suffix for the year folder
CATEGORY_COLS = ("Series", "Tier")  # ATP uses "Series", WTA uses "Tier"
GRAND_SLAM = "Grand Slam"

HEADERS = {"User-Agent": "Mozilla/5.0 (grand-slam-data-downloader)"}
PAUSE = 1.5        # base seconds between requests, to be polite
TIMEOUT = 60       # per-request read timeout
MAX_RETRIES = 4    # attempts per file before giving up


def season_urls(year: int, tour_suffix: str) -> list[str]:
    # Try both extensions; older seasons only exist as .xls, newer as .xlsx.
    stem = f"{BASE}/{year}{tour_suffix}/{year}"
    return [f"{stem}.xlsx", f"{stem}.xls"]


def looks_like_excel(content: bytes) -> bool:
    # xlsx files start with the ZIP magic "PK"; xls files start with the OLE
    # magic D0 CF 11 E0. The server's error page starts with "<html>".
    return content[:2] == b"PK" or content[:4] == b"\xd0\xcf\x11\xe0"


def fetch_bytes(year: int, tour: str, suffix: str) -> bytes | None:
    """Fetch a valid Excel file for the season, with retries. Returns raw bytes."""
    for attempt in range(1, MAX_RETRIES + 1):
        for url in season_urls(year, suffix):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            except requests.RequestException as exc:
                print(f"  [{tour} {year}] attempt {attempt} error: {exc}")
                continue
            if resp.status_code == 200 and looks_like_excel(resp.content):
                return resp.content
        # Neither extension gave a valid file this round; back off and retry.
        time.sleep(PAUSE * attempt)
    print(f"  [{tour} {year}] gave up after {MAX_RETRIES} attempts")
    return None


def load_season(year: int, tour: str, suffix: str) -> bytes | None:
    """Return season file bytes, using the local cache when available."""
    cached = RAW_DIR / f"{tour}_{year}.xlsx"
    if cached.exists() and looks_like_excel(cached.read_bytes()):
        return cached.read_bytes()

    content = fetch_bytes(year, tour, suffix)
    if content is None:
        return None
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(content)
    return content


def extract_grand_slams(content: bytes, year: int, tour: str) -> pd.DataFrame | None:
    try:
        df = pd.read_excel(io.BytesIO(content))  # engine auto-detected (xls/xlsx)
    except Exception as exc:  # noqa: BLE001 - report and skip unreadable files
        print(f"  [{tour} {year}] could not parse Excel: {exc}")
        return None

    col = next((c for c in CATEGORY_COLS if c in df.columns), None)
    if col is None:
        print(f"  [{tour} {year}] no category column {CATEGORY_COLS}, skipping")
        return None

    gs = df[df[col] == GRAND_SLAM].copy()
    if gs.empty:
        print(f"  [{tour} {year}] 0 Grand Slam matches")
        return None

    gs.insert(0, "Tour", tour)
    gs.insert(1, "Year", year)
    slams = ", ".join(sorted(gs["Tournament"].dropna().unique()))
    print(f"  [{tour} {year}] {len(gs):>4} Grand Slam matches ({slams})")
    return gs


def main() -> None:
    import warnings
    warnings.filterwarnings("ignore")  # silence openpyxl "unknown extension" noise

    GS_DIR.mkdir(parents=True, exist_ok=True)
    all_frames: list[pd.DataFrame] = []

    for tour, suffix in TOURS.items():
        start = ATP_START if tour == "ATP" else WTA_START
        print(f"\n=== {tour} ({start}-{END_YEAR}) ===")
        for year in range(start, END_YEAR + 1):
            content = load_season(year, tour, suffix)
            if content is None:
                continue
            gs = extract_grand_slams(content, year, tour)
            if gs is not None:
                gs.to_csv(GS_DIR / f"{tour}_{year}_grand_slam.csv", index=False)
                all_frames.append(gs)
            time.sleep(PAUSE)

    if not all_frames:
        print("\nNo data downloaded.")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    combined_path = OUT / "grand_slams_all.csv"
    combined.to_csv(combined_path, index=False)
    print(f"\nDone. {len(combined)} total Grand Slam matches across "
          f"{len(all_frames)} season files -> {combined_path}")


if __name__ == "__main__":
    main()
