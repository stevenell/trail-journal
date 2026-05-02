# Trail-journal site - one-shot update script
#
# Drops new content from `Desktop\pct\photos_incoming\` and `Desktop\pct\notes\`
# into the site, then commits and pushes - Cloudflare auto-deploys on push.
#
# Usage:
#     .\update.ps1                     # full flow (geotag, build, commit, push)
#     .\update.ps1 -NoPush             # build only - no git commit/push
#     .\update.ps1 -Message "day 27"   # custom commit message
#
# Re-runnable any time - already-tagged photos are preserved, notes merges
# are idempotent, and an empty diff just prints "nothing to commit" and exits.

[CmdletBinding()]
param(
    [switch]$NoPush,
    [string]$Message
)

$ErrorActionPreference = "Stop"
$pctRoot = "$env:USERPROFILE\OneDrive - Soaren Management\Desktop\pct"
$siteRoot = $PSScriptRoot
$geotagScript = "$env:USERPROFILE\OneDrive - Soaren Management\Desktop\geotag_photos_from_gpx.py"

if (-not (Test-Path $pctRoot)) {
    Write-Error "Canonical PCT data folder not found: $pctRoot"
    exit 1
}

Write-Host "==> Trail-journal site update"
Write-Host "    data root : $pctRoot"
Write-Host "    site root : $siteRoot"
Write-Host ""

# 1. Pull any new day entries from the Google Doc into the notes archive.
#    (No-op if .gdoc-url isn't configured yet - see WORKFLOW.md.)
Write-Host "[1/4] Pulling new notes from Google Doc..."
Push-Location $siteRoot
try {
    python scripts\pull_notes_from_gdoc.py
    if ($LASTEXITCODE -ne 0) { Write-Error "pull_notes step failed"; exit 1 }
} finally {
    Pop-Location
}
Write-Host ""

# 2. Geotag any new photos in photos_incoming\
$incoming = Get-ChildItem "$pctRoot\photos_incoming" -File -Filter "*.jp*g" -ErrorAction SilentlyContinue
if ($incoming -and $incoming.Count -gt 0) {
    Write-Host "[2/4] Geotagging $($incoming.Count) incoming photo(s)..."
    python $geotagScript
    if ($LASTEXITCODE -ne 0) { Write-Error "geotag step failed"; exit 1 }
    Write-Host ""
    Write-Host "    Note: incoming files are still in photos_incoming\."
    Write-Host "    Once you're happy with the result, you can delete them."
} else {
    Write-Host "[2/4] No new photos in photos_incoming\ - skipping geotag."
}
Write-Host ""

# 3. Build site data (notes -> markdown, KML+notes -> geojson, photos -> public/photos)
Write-Host "[3/4] Building site data..."
Push-Location $siteRoot
try {
    python scripts\build_data.py
    if ($LASTEXITCODE -ne 0) { Write-Error "build_data step failed"; exit 1 }
} finally {
    Pop-Location
}
Write-Host ""

# 4. Commit and push (skipped if -NoPush, or if there is nothing to commit)
Push-Location $siteRoot
try {
    if ($NoPush) {
        Write-Host "[4/4] -NoPush set - skipping git commit/push."
        Write-Host ""
        Write-Host "Done. Refresh your browser, or run 'npm run dev' if it isn't running."
        return
    }

    Write-Host "[4/4] Committing and pushing..."
    git add . | Out-Null
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    Nothing changed since last push - skipping commit."
        Write-Host ""
        Write-Host "Done."
        return
    }

    if (-not $Message) {
        $Message = "update " + (Get-Date -Format "yyyy-MM-dd")
    }
    git commit -m $Message
    if ($LASTEXITCODE -ne 0) { Write-Error "git commit failed"; exit 1 }

    git push
    if ($LASTEXITCODE -ne 0) { Write-Error "git push failed"; exit 1 }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done. Cloudflare will rebuild within a few seconds."
Write-Host 'Live deploys: https://dash.cloudflare.com  (Workers and Pages > trail-journal)'
