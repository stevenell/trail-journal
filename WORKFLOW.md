# Update workflow

All canonical trip data lives in **`%USERPROFILE%\OneDrive - Soaren Management\Desktop\pct\`** (call it `<PCT>` below):

```
<PCT>\
  .gdoc-url        (optional) one line: published-to-web URL of Emily's notes Google Doc
  notes\           one or more notes-NN.txt files (any names work)
  photos\          ALL geotagged photos — the build reads from here
  best_photos\     small curated subset; one of these is used as the homepage OG image
  backgrounds\     optional background images for the site
  gpx\             Garmin GPX files (kept for reference; no longer used by the build)
  pct_trip.kml     KML route + day stops (used for map lines)
```

Photos arrive **pre-geotagged from the phone** now (location services baked into EXIF), so there is no separate geotag step. Just drop new photos into `<PCT>\photos\` and run the update.

## Google Doc → notes archive (the easiest way to keep notes in sync)

One-time setup:

1. Open Emily's notes doc in Google Docs.
2. **File → Share → Publish to web** → click **Publish**.
3. Copy the URL Google gives you. It looks like:
   ```
   https://docs.google.com/document/d/e/2PACX-.../pub
   ```
4. Paste that single line into a new file at `<PCT>\.gdoc-url`.

Going forward:

- Edit the Doc whenever Emily sends new content. Keep the existing format (`Day #N:` header, stats, body, `Camping here: GPS:[lat, lon]`).
- The first step of `update.ps1` calls `scripts\pull_notes_from_gdoc.py`, which fetches the Doc and writes a snapshot to `<PCT>\notes\notes-gdoc-latest.txt` containing every day in the Doc.
- The build merges all `notes\*.txt` by day number, preferring the longest body — so older static `notes-NN.txt` files keep providing days that have rolled out of the Doc, and updated body content from the Doc wins for days where Emily later filled in details.

## When Emily sends a new batch

1. **Notes**: usually you don't need to do anything — they're in the Doc. If she sent a separate text file, drop it into `<PCT>\notes\` with any name (e.g. `notes-03.txt`).

2. **Photos**: drop them straight into `<PCT>\photos\`. They already have GPS from the phone. If a particular photo doesn't appear on the map, its EXIF doesn't have GPS — easiest fix is to retag it on the phone.

3. **Best photos** (optional): pick 3–6 of your favorite shots and copy them into `<PCT>\best_photos\` using the **same filename** as in `photos\`. The first one (alphabetically) becomes the homepage OG image / link preview. To rotate to a different photo, rename it so it sorts first, or just put exactly one photo in the folder.

4. **GPX**: only relevant if you ever need to retroactively geotag a non-phone photo via `Desktop\geotag_photos_from_gpx.py`. Not part of the normal flow.

5. **Run** `update.ps1` from the site root:

   ```powershell
   cd c:\Users\steven.ellingson\projects\pct-site
   .\update.ps1
   ```

   This:
   - Pulls the latest Google Doc content into `notes\notes-gdoc-latest.txt`.
   - Re-runs `scripts\build_data.py`, which:
     - parses every `notes\*.txt` and merges into `src\content\days\day-NN.md`
     - rebuilds `src\data\route.json` (KML route lines + day-stop pins, augmented with any new days from notes that aren't yet in the KML)
     - rebuilds `src\data\photos.json` (every photo from `<PCT>\photos\`, with `best: true` flagged for any whose filename also appears in `<PCT>\best_photos\`) and re-resizes into `public\photos\`
     - syncs `<PCT>\backgrounds\` to `public\bg\`
   - Commits and pushes to GitHub. Cloudflare auto-deploys.

6. **Refresh the browser**. If the dev server isn't running:

   ```powershell
   npm run dev
   ```

## Curated link-preview photo (homepage OG)

When you share `https://dustandstars.space/` on Facebook / iMessage / Slack, the link preview uses the first photo (alphabetically by filename) in `<PCT>\best_photos\`. To swap it:

- **Replace**: drop a different photo into `<PCT>\best_photos\` (and remove the previous one).
- **Force a specific one**: leave only one file in `<PCT>\best_photos\`.
- **Rotate**: keep several files in `<PCT>\best_photos\`. The build picks the first one alphabetically — Facebook caches the OG image for ~30 days, so you should expect a noticeable preview change every time you swap the lead photo, not on every push.

For per-day links (e.g. `dustandstars.space/posts/day-25/`), the OG image is picked deterministically from that day's photos using the day number as a seed — so each day's link gets a different photo, but the same photo every time you visit.

## Manual geotag (only needed for old photos)

`Desktop\geotag_photos_from_gpx.py` is the legacy tagger. It still works but isn't run by `update.ps1` anymore. Use it only if you ever need to retroactively tag a photo that doesn't have phone GPS. Defaults read from `photos_incoming\` (which we no longer maintain) and write to `photos\`. Adjust paths via CLI flags if needed.
