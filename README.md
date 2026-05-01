# Trail Journal

A static site for sharing daily trail-journal entries, photos, and a route map. Built around Emily's 2026 PCT thru-hike, but the platform is generic — drop different notes/GPX/photos in and you have someone else's adventure.

## Stack

- [Astro](https://astro.build) static site generator
- Markdown content collections for daily journal entries
- [Leaflet](https://leafletjs.com) + OpenTopoMap for the trail page
- Python build scripts that turn raw notes/photos/GPX into typed site data

## Data flow

Raw input lives **outside the repo** in `Desktop\pct\` (see [WORKFLOW.md](./WORKFLOW.md)). The build pipeline:

```
Desktop\pct\notes\*.txt        ─┐
Desktop\pct\photos_geotagged\  ─┼─►  scripts/build_data.py  ─►  src/content/days/*.md
Desktop\pct\pct_trip.kml       ─┘                              src/data/route.json
                                                                src/data/photos.json
                                                                public/photos/*
                                                                       │
                                                                       ▼
                                                            npm run build  →  dist/
```

## Updating

When new content arrives from the trail:

```powershell
.\update.ps1
```

This geotags any new photos, regenerates all site data, and resizes images. Then refresh the dev server. See [WORKFLOW.md](./WORKFLOW.md) for the full flow including how new notes files and GPX get integrated.

## Local dev

```powershell
npm install
npm run dev          # http://localhost:4321
npm run build        # static output in dist/
```

## Deploy

Hosted on Cloudflare Pages. Pushes to `main` auto-deploy.
