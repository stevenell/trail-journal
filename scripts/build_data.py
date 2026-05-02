"""Build all derived data for the site from the source-of-truth inputs.

Inputs (paths configurable below):
  - pct_trip.kml             route lines + day stops
  - pct notes.txt            day-by-day journal
  - photos_geotagged/        JPEGs with GPS in EXIF

Outputs (relative to project root):
  - src/data/route.geojson         PCT line segments + day stops as features
  - src/data/photos.json           every photo: {file, lat, lon, day, taken_at}
  - src/content/days/day-NN.md     one Markdown file per day (frontmatter + body)
  - public/photos/<name>.jpg       1600 px downsized JPEGs
  - public/photos/thumb_<name>.jpg 480 px square thumbnails for grids

Usage:
    python scripts/build_data.py

Requirements:  pip install pillow piexif
"""

from __future__ import annotations

import io
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import piexif
    from PIL import Image, ImageOps
except ImportError as e:
    print(f"Missing dependency: {e.name}\n  pip install pillow piexif")
    sys.exit(1)

# ---------------- INPUT PATHS ----------------
PCT_DATA = Path(
    r"C:\Users\steven.ellingson\OneDrive - Soaren Management\Desktop\pct"
)
SOURCE_KML = PCT_DATA / "pct_trip.kml"
SOURCE_NOTES_DIR = PCT_DATA / "notes"  # all *.txt files merged in name order
SOURCE_PHOTOS = PCT_DATA / "photos_geotagged"
SOURCE_BACKGROUNDS = PCT_DATA / "backgrounds"  # optional bg images for the site

# ---------------- OUTPUT (relative to project root) ----------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
GEOJSON_OUT = PROJECT_ROOT / "src" / "data" / "route.json"
PHOTOS_JSON_OUT = PROJECT_ROOT / "src" / "data" / "photos.json"
BACKGROUNDS_JSON_OUT = PROJECT_ROOT / "src" / "data" / "backgrounds.json"
DAYS_DIR = PROJECT_ROOT / "src" / "content" / "days"
PHOTOS_PUBLIC = PROJECT_ROOT / "public" / "photos"
BACKGROUNDS_PUBLIC = PROJECT_ROOT / "public" / "bg"

# ---------------- KNOBS ----------------
DAY_ONE_DATE = date(2026, 4, 5)
PHOTO_TZ = ZoneInfo("America/Los_Angeles")

LARGE_MAX_PX = 1600
LARGE_QUALITY = 84
THUMB_PX = 480
THUMB_QUALITY = 78

KML_NS = "{http://www.opengis.net/kml/2.2}"


# ============================================================
# 1) KML -> route.geojson
# ============================================================

def kml_to_geojson(kml_path: Path) -> dict:
    tree = ET.parse(kml_path)
    features: list[dict] = []

    section_color = {
        "PCT Section A": "#e53935",
        "PCT Section B": "#43a047",
        "PCT Section C": "#1e88e5",
    }

    for pm in tree.iter(f"{KML_NS}Placemark"):
        name_el = pm.find(f"{KML_NS}name")
        name = name_el.text.strip() if (name_el is not None and name_el.text) else ""
        desc_el = pm.find(f"{KML_NS}description")
        desc = desc_el.text if desc_el is not None else None

        line = pm.find(f".//{KML_NS}LineString/{KML_NS}coordinates")
        point = pm.find(f".//{KML_NS}Point/{KML_NS}coordinates")

        if line is not None and line.text:
            coords = []
            for tok in line.text.strip().split():
                parts = tok.split(",")
                if len(parts) >= 2:
                    coords.append([float(parts[0]), float(parts[1])])
            color = next(
                (c for prefix, c in section_color.items() if name.startswith(prefix)),
                "#666",
            )
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {"kind": "route", "name": name, "color": color},
            })

        elif point is not None and point.text:
            parts = point.text.strip().split(",")
            if len(parts) >= 2:
                lon = float(parts[0])
                lat = float(parts[1])
                m = re.match(r"^Day\s+(\d+)\s*-\s*(.+)$", name, re.IGNORECASE)
                day_num = int(m.group(1)) if m else None
                stop_type = m.group(2) if m else "Stop"
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "kind": "stop",
                        "name": name,
                        "day": day_num,
                        "stop_type": stop_type,
                        "description": desc,
                    },
                })

    return {"type": "FeatureCollection", "features": features}


# ============================================================
# 2) notes.txt -> Markdown files per day
# ============================================================

DAY_HEADER_RE = re.compile(r"^Day\s*#?(\d+)\s*[:\-]?\s*(.*)$", re.IGNORECASE)
GPS_RE = re.compile(r"\[\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*\]")
KV_RE = re.compile(
    r"^(Goal|Miles Hiked Today|Total miles Hiked on the PCT|"
    r"Total miles Hiked \(on & off trail\)|Miles to go)\s*[=:]\s*(.+)$",
    re.IGNORECASE,
)

# Conservative typo fixes — only obvious mechanical errors, never style/voice.
TYPO_FIXES: list[tuple[str, str]] = [
    (r"\bTooka\b", "Took a"),
    (r"\bto to trailhead\b", "to the trailhead"),
    (r"\bHikered\b", "Hiked"),
]

# For days where Emily wrote a street address instead of GPS coords.
# (lat, lon, stop_type) — coords are approximate from the address.
ADDRESS_OVERRIDES: dict[int, tuple[float, float, str]] = {
    # 914 Robinhood Blvd, Big Bear City, CA 92314
    20: (34.24890, -116.84726, "Airbnb"),
    21: (34.24890, -116.84726, "Airbnb"),
    22: (34.24890, -116.84726, "Airbnb"),
}

# Lines that mark the day's lodging — strip from body regardless of GPS presence.
LODGING_LINE_RE = re.compile(
    r"^\s*(camping here|stay here|staying here|here)\s*[:\-]",
    re.IGNORECASE,
)


def apply_typo_fixes(text: str) -> str:
    for pat, repl in TYPO_FIXES:
        text = re.sub(pat, repl, text)
    return text


def format_body_markdown(body: str) -> str:
    """Convert raw bullet-style notes into Markdown.

    Each blank-line-separated block becomes a paragraph; within a paragraph,
    each source line becomes a hard <br>. This preserves the "list of short
    thoughts" feel of phone-typed trail notes.
    """
    blocks = re.split(r"\n{2,}", body)
    out_blocks: list[str] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if len(lines) == 1:
            out_blocks.append(lines[0])
        else:
            # Markdown hard break: trailing two spaces before newline.
            out_blocks.append("  \n".join(lines))
    return "\n\n".join(out_blocks)


def merge_day_entries(*entry_lists: list[dict]) -> list[dict]:
    """Merge per-day entries from multiple notes files.

    For each `day` number, the entry with the longer body wins (so a stub
    gets replaced by the full version). Within the winning entry, fields
    that are None are filled in from the loser. The result is sorted by day.
    """
    by_day: dict[int, dict] = {}
    for entries in entry_lists:
        for entry in entries:
            d = entry["day"]
            existing = by_day.get(d)
            if existing is None:
                by_day[d] = entry
                continue
            new_len = len(entry.get("body") or "")
            old_len = len(existing.get("body") or "")
            winner, loser = (entry, existing) if new_len >= old_len else (existing, entry)
            for k, v in loser.items():
                if winner.get(k) in (None, "") and v not in (None, ""):
                    winner[k] = v
            by_day[d] = winner
    return [by_day[d] for d in sorted(by_day)]


def parse_notes_dir(notes_dir: Path) -> list[dict]:
    """Parse every *.txt in notes_dir (sorted by name) and merge by day."""
    if not notes_dir.exists():
        raise FileNotFoundError(f"Notes directory does not exist: {notes_dir}")
    files = sorted(notes_dir.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"No .txt files in {notes_dir}")
    print(f"      reading {len(files)} notes file(s):")
    parsed: list[list[dict]] = []
    for f in files:
        entries = parse_notes_file(f.read_text(encoding="utf-8"))
        print(f"        {f.name:<20} {len(entries):>3} day entries")
        parsed.append(entries)
    return merge_day_entries(*parsed)


def parse_notes_file(text: str) -> list[dict]:
    """Return [{day, date, title, miles_today, total_pct, total_all, miles_to_go,
                goal, lat, lon, stop_type, body}] for each day."""
    chunks = re.split(r"_{5,}", text)
    out: list[dict] = []
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        day_num = None
        first_line = None
        for ln in chunk.splitlines():
            m = DAY_HEADER_RE.match(ln.strip())
            if m:
                day_num = int(m.group(1))
                first_line = ln.strip()
                break
        if day_num is None:
            continue

        info = {
            "day": day_num,
            "date": (DAY_ONE_DATE + timedelta(days=day_num - 1)).isoformat(),
            "title": first_line,
            "miles_today": None,
            "total_pct": None,
            "total_all": None,
            "miles_to_go": None,
            "goal": None,
            "lat": None,
            "lon": None,
            "stop_type": None,
        }

        # extract structured fields and strip metadata lines from body
        body_lines: list[str] = []
        for ln in chunk.splitlines():
            stripped = ln.strip()
            m = KV_RE.match(stripped)
            if m:
                key = m.group(1).lower()
                val = m.group(2).strip()
                if "miles hiked today" in key:
                    info["miles_today"] = val
                elif "total miles hiked on the pct" in key:
                    info["total_pct"] = val
                elif "total miles hiked (on & off trail)" in key:
                    info["total_all"] = val
                elif "miles to go" in key:
                    info["miles_to_go"] = val
                elif "goal" in key:
                    info["goal"] = val
                continue
            # strip the day header itself wherever it appears
            if DAY_HEADER_RE.match(stripped):
                continue
            # strip lodging-tag lines (with or without GPS coords)
            if LODGING_LINE_RE.match(stripped):
                continue
            body_lines.append(ln)

        # last GPS in chunk = camp/lodging
        coords = list(GPS_RE.finditer(chunk))
        if coords:
            last = coords[-1]
            info["lat"] = float(last.group(1))
            info["lon"] = float(last.group(2))
            for ln in chunk.splitlines():
                if last.group(0) in ln:
                    low = ln.lower()
                    if "airbnb" in low:
                        info["stop_type"] = "Airbnb"
                    elif "hostel" in low:
                        info["stop_type"] = "Hostel"
                    elif "camp" in low or "stay here" in low:
                        info["stop_type"] = "Camp"
                    break

        # Fallback 1: keyword-based stop_type from any "Staying here: ..." line
        # (catches address-only entries with no GPS coords).
        if info["stop_type"] is None:
            for ln in chunk.splitlines():
                if not LODGING_LINE_RE.match(ln.strip()):
                    continue
                low = ln.lower()
                if "airbnb" in low:
                    info["stop_type"] = "Airbnb"
                elif "hostel" in low:
                    info["stop_type"] = "Hostel"
                elif "motel" in low or "hotel" in low:
                    info["stop_type"] = "Motel"
                elif "camp" in low:
                    info["stop_type"] = "Camp"
                if info["stop_type"]:
                    break

        # Fallback 2: explicit per-day overrides (geocoded street addresses).
        if day_num in ADDRESS_OVERRIDES:
            ov_lat, ov_lon, ov_type = ADDRESS_OVERRIDES[day_num]
            if info["lat"] is None:
                info["lat"] = ov_lat
            if info["lon"] is None:
                info["lon"] = ov_lon
            if info["stop_type"] is None:
                info["stop_type"] = ov_type

        # collapse runs of >2 blank lines, trim, fix typos, transform to Markdown
        body = "\n".join(body_lines)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        body = apply_typo_fixes(body)
        body = format_body_markdown(body)
        info["body"] = body
        out.append(info)
    return out


def write_day_markdown(day: dict, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fname = f"day-{day['day']:02d}.md"
    title = day["title"] or f"Day {day['day']}"

    def yamlstr(s: str) -> str:
        # Keep emoji + non-ASCII intact in YAML frontmatter
        return json.dumps(s, ensure_ascii=False)

    fm_lines = [
        "---",
        f"day: {day['day']}",
        f'date: "{day["date"]}"',
        f"title: {yamlstr(title)}",
    ]
    for k in ("goal", "miles_today", "total_pct", "total_all", "miles_to_go",
              "stop_type"):
        if day.get(k):
            fm_lines.append(f"{k}: {yamlstr(day[k])}")
    if day["lat"] is not None and day["lon"] is not None:
        fm_lines.append(f"lat: {day['lat']}")
        fm_lines.append(f"lon: {day['lon']}")
    fm_lines.append("---")

    content = "\n".join(fm_lines) + "\n\n" + (day["body"] or "") + "\n"
    (outdir / fname).write_text(content, encoding="utf-8")


# ============================================================
# 3) Photos -> public/photos/ + photos.json
# ============================================================

def read_exif_gps(exif_dict: dict) -> tuple[float, float] | None:
    gps = exif_dict.get("GPS") or {}
    lat_rat = gps.get(piexif.GPSIFD.GPSLatitude)
    lon_rat = gps.get(piexif.GPSIFD.GPSLongitude)
    lat_ref = gps.get(piexif.GPSIFD.GPSLatitudeRef)
    lon_ref = gps.get(piexif.GPSIFD.GPSLongitudeRef)
    if not (lat_rat and lon_rat and lat_ref and lon_ref):
        return None

    def to_deg(rat):
        d, m, s = (r[0] / r[1] for r in rat)
        return d + m / 60 + s / 3600

    lat = to_deg(lat_rat)
    lon = to_deg(lon_rat)
    if lat_ref in (b"S", "S"):
        lat = -lat
    if lon_ref in (b"W", "W"):
        lon = -lon
    return lat, lon


def read_exif_local_dt(exif_dict: dict) -> datetime | None:
    raw = (exif_dict.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
           or exif_dict.get("Exif", {}).get(piexif.ExifIFD.DateTimeDigitized)
           or exif_dict.get("0th", {}).get(piexif.ImageIFD.DateTime))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="ignore")
    raw = raw.split("\x00")[0].strip()
    try:
        return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def resize_to_jpeg(src: Path, dst: Path, max_px: int, quality: int,
                   square: bool = False) -> None:
    img = Image.open(src)
    img = ImageOps.exif_transpose(img)
    if square:
        img = ImageOps.fit(img, (max_px, max_px), method=Image.LANCZOS)
    else:
        img.thumbnail((max_px, max_px), Image.LANCZOS)
    if img.mode != "RGB":
        img = img.convert("RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst, format="JPEG", quality=quality, optimize=True, progressive=True)


def safe_name(stem: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", stem) + ".jpg"


def build_photos(src_dir: Path, public_dir: Path) -> list[dict]:
    # Don't rmtree the whole folder — Astro's dev server can hold file
    # locks on /public/photos/ assets and that triggers WinError 145.
    # Instead, remove just the .jpg files we manage so the dir keeps its
    # handle open while individual files are unlinked.
    public_dir.mkdir(parents=True, exist_ok=True)
    if public_dir.exists():
        for f in public_dir.iterdir():
            if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg"}:
                try:
                    f.unlink()
                except PermissionError:
                    pass  # dev server has it open; will be overwritten below

    photos = sorted(p for p in src_dir.rglob("*") if p.suffix.lower() in {".jpg", ".jpeg"})
    out: list[dict] = []
    for i, src in enumerate(photos, 1):
        if i % 25 == 0 or i == len(photos):
            print(f"    photo {i}/{len(photos)}")
        try:
            img = Image.open(src)
            exif = piexif.load(img.info.get("exif", b""))
        except Exception as e:
            print(f"    [warn] {src.name}: cannot read exif ({e})")
            continue
        gps = read_exif_gps(exif)
        if gps is None:
            continue  # photos without GPS aren't placeable
        lat, lon = gps
        local_dt = read_exif_local_dt(exif)
        taken_at = local_dt.isoformat(timespec="seconds") if local_dt else None
        day = None
        if local_dt:
            d = local_dt.date()
            day = (d - DAY_ONE_DATE).days + 1
            if day < 1:
                day = None  # pre-trip

        outname = safe_name(src.stem)
        large_path = public_dir / outname
        thumb_path = public_dir / f"thumb_{outname}"
        resize_to_jpeg(src, large_path, LARGE_MAX_PX, LARGE_QUALITY)
        resize_to_jpeg(src, thumb_path, THUMB_PX, THUMB_QUALITY, square=True)

        out.append({
            "file": outname,
            "thumb": f"thumb_{outname}",
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "taken_at": taken_at,
            "day": day,
            "width": LARGE_MAX_PX,
        })
    return out


# ============================================================
# main
# ============================================================

def augment_route_with_day_stops(geo: dict, days: list[dict]) -> None:
    """Add day-stop Point features for any day with lat/lon that isn't already
    represented as a Point in the KML-derived GeoJSON. Modifies geo in place."""
    existing_days = {
        f["properties"].get("day")
        for f in geo["features"]
        if f["geometry"]["type"] == "Point" and f["properties"].get("day") is not None
    }
    added = 0
    for d in days:
        if d["day"] in existing_days:
            continue
        if d.get("lat") is None or d.get("lon") is None:
            continue
        stop_type = d.get("stop_type") or "Stop"
        geo["features"].append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [d["lon"], d["lat"]]},
            "properties": {
                "kind": "stop",
                "name": f"Day {d['day']} - {stop_type}",
                "day": d["day"],
                "stop_type": stop_type,
                "description": None,
            },
        })
        added += 1
    if added:
        print(f"      added {added} day-stop pin(s) from notes (not in KML)")


def main() -> None:
    print("Building site data\n")

    print(f"[1/3] notes -> {DAYS_DIR.relative_to(PROJECT_ROOT)}")
    days = parse_notes_dir(SOURCE_NOTES_DIR)
    DAYS_DIR.mkdir(parents=True, exist_ok=True)
    # Clear stale per-day files (the dir itself stays — Astro's dev server
    # holds a watch handle on it and rmtree fails on Windows).
    for old in DAYS_DIR.glob("day-*.md"):
        old.unlink()
    for d in days:
        write_day_markdown(d, DAYS_DIR)
    print(f"      {len(days)} day files\n")

    print(f"[2/3] KML -> {GEOJSON_OUT.relative_to(PROJECT_ROOT)}")
    geo = kml_to_geojson(SOURCE_KML)
    augment_route_with_day_stops(geo, days)
    GEOJSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    GEOJSON_OUT.write_text(json.dumps(geo, indent=2), encoding="utf-8")
    n_lines = sum(1 for f in geo["features"] if f["geometry"]["type"] == "LineString")
    n_pts = sum(1 for f in geo["features"] if f["geometry"]["type"] == "Point")
    print(f"      {n_lines} route segments, {n_pts} day stops total\n")

    print(f"[3/3] photos -> {PHOTOS_PUBLIC.relative_to(PROJECT_ROOT)}/")
    photos = build_photos(SOURCE_PHOTOS, PHOTOS_PUBLIC)
    PHOTOS_JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    PHOTOS_JSON_OUT.write_text(json.dumps(photos, indent=2), encoding="utf-8")
    print(f"      {len(photos)} photos written\n")

    sync_backgrounds()

    print("Done.")


def sync_backgrounds() -> None:
    """Copy any candidate background images from <PCT>/backgrounds/ into
    public/bg/. Files that aren't in the source any more are pruned (except
    README.md and the canonical "space.jpg" if no candidates are present).

    Also writes the list of candidate filenames to src/data/backgrounds.json
    so BaseLayout.astro can import it without needing node:fs at build time
    (which doesn't work on Cloudflare's prerender Worker).
    """
    BACKGROUNDS_PUBLIC.mkdir(parents=True, exist_ok=True)
    BACKGROUNDS_JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    exts = {".jpg", ".jpeg", ".png", ".webp"}

    if not SOURCE_BACKGROUNDS.exists():
        # No source folder -> publish whatever's already in public/bg/.
        present = sorted(
            p.name for p in BACKGROUNDS_PUBLIC.iterdir()
            if p.is_file() and p.suffix.lower() in exts
        )
        BACKGROUNDS_JSON_OUT.write_text(
            json.dumps(present, indent=2), encoding="utf-8"
        )
        print(f"[bg]   no source dir, listed {len(present)} existing image(s)")
        return

    candidates = sorted(
        p for p in SOURCE_BACKGROUNDS.iterdir()
        if p.is_file() and p.suffix.lower() in exts
    )

    print(
        f"[bg]   {len(candidates)} candidate(s) "
        f"in {SOURCE_BACKGROUNDS.relative_to(PCT_DATA.parent)}/"
    )

    # Copy candidates over (same name, replace if present).
    keep_names = set()
    for src in candidates:
        dst = BACKGROUNDS_PUBLIC / src.name
        keep_names.add(src.name)
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime and dst.stat().st_size == src.stat().st_size:
            continue
        shutil.copy2(src, dst)
        print(f"  [bg] copy {src.name} -> public/bg/")

    # Prune images in public/bg/ that aren't candidates any more, but
    # leave README.md and any non-image files alone.
    for existing in BACKGROUNDS_PUBLIC.iterdir():
        if not existing.is_file():
            continue
        if existing.suffix.lower() not in exts:
            continue
        if existing.name not in keep_names:
            existing.unlink()

    # Write the list to src/data/backgrounds.json (committed to git).
    bg_list = sorted(keep_names)
    BACKGROUNDS_JSON_OUT.write_text(
        json.dumps(bg_list, indent=2), encoding="utf-8"
    )
    print(f"[bg]   wrote {len(bg_list)} entries -> {BACKGROUNDS_JSON_OUT.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
