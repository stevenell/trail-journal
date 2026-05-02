"""Pull new day entries from Emily's Google Doc into the notes archive.

How it works
------------
1. Reads a published-to-web Google Doc URL from `Desktop\\pct\\.gdoc-url`.
2. Fetches the doc as plain text.
3. Parses every "Day #N" entry, separated by the standard underscore line.
4. Dedupes against everything already in `Desktop\\pct\\notes\\notes-*.txt`.
5. Appends only the genuinely-new days to a dated archive file
   (`notes-gdoc-YYYY-MM-DD.txt`).

This is idempotent: re-running with no new content is a no-op. You can
keep adding days to the Doc indefinitely; only days not yet in the
archive get pulled. (You can clear old entries from the Doc whenever
you like - the local archive already has them.)

One-time setup (in Google Docs)
-------------------------------
1. File -> Share -> Publish to web -> "Plain text" tab -> Publish.
2. Copy the URL Google gives you. It looks like:
       https://docs.google.com/document/d/e/2PACX-.../pub?output=txt
3. Save that single line into:
       C:\\Users\\<you>\\OneDrive - Soaren Management\\Desktop\\pct\\.gdoc-url
4. From now on, just edit the Doc and run `update.ps1` - this script
   runs as the first step and pulls anything new.
"""
from __future__ import annotations

import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

PCT_DATA = Path(r"C:\Users\steven.ellingson\OneDrive - Soaren Management\Desktop\pct")
NOTES_DIR = PCT_DATA / "notes"
URL_FILE = PCT_DATA / ".gdoc-url"

DAY_RE = re.compile(r"^Day\s*#?(\d+)\b", re.MULTILINE)
ENTRY_SEP_RE = re.compile(r"^_{20,}\s*$", re.MULTILINE)


def fetch_doc_text(url: str) -> str:
    print(f"  fetching: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 pct-site"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    text = raw.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def parse_day_entries(text: str) -> dict[int, str]:
    """Return {day_num: full_entry_text} for each Day #N block in `text`."""
    chunks = ENTRY_SEP_RE.split(text)
    entries: dict[int, str] = {}
    for chunk in chunks:
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        m = DAY_RE.search(chunk)
        if not m:
            continue
        day = int(m.group(1))
        # Last entry wins if a day appears twice (Emily edited it).
        entries[day] = chunk
    return entries


def existing_archive_days() -> set[int]:
    """Days already captured anywhere in `notes/notes-*.txt`."""
    days: set[int] = set()
    if not NOTES_DIR.exists():
        return days
    for f in sorted(NOTES_DIR.glob("notes-*.txt")):
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = f.read_text(encoding="utf-8", errors="replace")
        for m in DAY_RE.finditer(text):
            days.add(int(m.group(1)))
    return days


def main() -> int:
    if not URL_FILE.exists():
        print("[gdoc] no .gdoc-url configured - skipping (set up later via WORKFLOW.md)")
        return 0
    url = URL_FILE.read_text(encoding="utf-8").strip()
    if not url:
        print("[gdoc] .gdoc-url is empty - skipping")
        return 0
    if not url.startswith("http"):
        print(f"[gdoc] .gdoc-url doesn't look like a URL: {url[:60]!r} - skipping")
        return 0

    print("[gdoc] checking Google Doc for new day entries...")

    try:
        text = fetch_doc_text(url)
    except Exception as e:
        print(f"[gdoc] failed to fetch doc: {e}")
        return 1

    entries = parse_day_entries(text)
    if not entries:
        print("[gdoc] no 'Day #N' entries found in the doc.")
        return 0

    have = existing_archive_days()
    new_days = sorted(d for d in entries if d not in have)

    print(f"  doc has {len(entries)} day entr(ies); archive already has {len(have)}.")
    if not new_days:
        print("[gdoc] nothing new to add.")
        return 0

    # Build the appended block.
    out_blocks: list[str] = []
    for day in new_days:
        out_blocks.append("_______________________________________________\n")
        out_blocks.append("\n")
        out_blocks.append(entries[day].rstrip() + "\n")
        out_blocks.append("\n")
    appended = "".join(out_blocks)

    # All-in-one file per pull date. If we pull twice in one day, append.
    target = NOTES_DIR / f"notes-gdoc-{date.today().isoformat()}.txt"
    if target.exists():
        prev = target.read_text(encoding="utf-8")
        target.write_text(prev.rstrip() + "\n\n" + appended, encoding="utf-8")
        print(f"[gdoc] appended day(s) {new_days} to existing {target.name}")
    else:
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        target.write_text(appended, encoding="utf-8")
        print(f"[gdoc] wrote day(s) {new_days} to new {target.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
