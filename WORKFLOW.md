# Update workflow

All canonical trip data lives in **`%USERPROFILE%\OneDrive - Soaren Management\Desktop\pct\`** (call it `<PCT>` below):

```
<PCT>\
  .gdoc-url               (optional) one line: published-to-web URL of Emily's notes Google Doc
  notes\                  one or more notes-NN.txt files (any names work)
  photos_geotagged\       all geotagged photos — the build reads from here
  photos_incoming\        DROP NEW UNTAGGED PHOTOS HERE
  gpx\                    Garmin GPX files (used by geotag fallback)
  pct_trip.kml            KML route + day stops (used for map lines)
```

## Google Doc → notes archive (the easiest way to keep notes in sync)

One-time setup:

1. Open Emily's notes doc in Google Docs.
2. **File → Share → Publish to web**.
3. In the dialog, switch the format dropdown to **"Plain text"** and click **Publish**.
4. Copy the URL Google gives you. It looks like:
   ```
   https://docs.google.com/document/d/e/2PACX-.../pub?output=txt
   ```
5. Paste that single line into a new file at `<PCT>\.gdoc-url`.

Going forward:

- Edit the Doc whenever Emily sends new content. Just keep the existing format (`Day #N:` header, stats, body, `Camping here: GPS:[lat, lon]`).
- The first step of `update.ps1` calls `scripts\pull_notes_from_gdoc.py`, which:
  - Fetches the Doc's plain-text dump
  - Parses every `Day #N` block
  - Skips any day already in `<PCT>\notes\notes-*.txt`
  - Appends only new days into a dated archive file: `notes-gdoc-YYYY-MM-DD.txt`
- It's idempotent — re-running is a no-op until you add a new day to the Doc.
- Once a day is in the archive locally, you're free to delete it from the Doc to keep things tidy. The archive is the source of truth.

## When Emily sends a new batch (manual fallback)

1. **Notes**: copy the new text file into `<PCT>\notes\` with any name (e.g. `notes-03.txt`). The build merges all `*.txt` files by day number — when two files have the same day, the longer body wins, and missing fields are filled in from the other.

2. **Photos**:
   - Photos that **already have GPS** in their EXIF (e.g. from a phone with working GPS) → drop straight into `<PCT>\photos_geotagged\`. They go to the site as-is.
   - Photos **without GPS** (older Garmin-tagged batch, broken-GPS phone batch) → drop into `<PCT>\photos_incoming\`. The geotag step handles them.

3. **GPX**: any new `.gpx` files from Emily's Garmin go into `<PCT>\gpx\` (used to tag photos by timestamp).

4. **Run** `update.ps1` from the site root:

   ```powershell
   cd c:\Users\steven.ellingson\projects\pct-site
   .\update.ps1
   ```

   This:
   - Geotags everything in `photos_incoming\` (skipping any that already have GPS), writing tagged copies into `photos_geotagged\`.
   - Re-runs `scripts\build_data.py`, which:
     - parses every `notes\*.txt` file and merges into `src\content\days\day-NN.md`
     - rebuilds `src\data\route.json` (KML route lines + day-stop pins, augmented with any new days from notes that aren't yet in the KML)
     - rebuilds `src\data\photos.json` and re-resizes everything in `public\photos\`

5. **Refresh the browser**. If the dev server isn't running:

   ```powershell
   npm run dev
   ```

## Notes on the geotag step

`Desktop\geotag_photos_from_gpx.py` is the tagger. Defaults are wired to read from `<PCT>\photos_incoming\` and write to `<PCT>\photos_geotagged\`. It will:

- **Skip** any photo that already has EXIF GPS (so re-running is safe — never overwrites real coords).
- **Match** photos by EXIF timestamp against all GPX points in `<PCT>\gpx\` (within 15 min).
- **Fall back** to the day's camp/lodging coord — first looking in `pct_trip.kml`, then in `<PCT>\notes\*.txt`. Notes wins on conflicts, so any new days that aren't in the KML yet still get a fallback.

## After re-running

The originals from Emily's drops are still in `photos_incoming\`. They're harmless — re-running the update is a no-op once the geotagged copies are written. Clean them out manually whenever you want; nothing depends on them sticking around.
