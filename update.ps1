# Emily's PCT site — one-shot update script
#
# Drops new content from `Desktop\pct\photos_incoming\` and `Desktop\pct\notes\`
# into the site, then prints a summary. Re-runnable any time — already-tagged
# photos are preserved, and notes-file merges are idempotent.
#
# Usage:
#     .\update.ps1
# Or open PowerShell here and run the same command.

$ErrorActionPreference = "Stop"
$pctRoot = "$env:USERPROFILE\OneDrive - Soaren Management\Desktop\pct"
$siteRoot = $PSScriptRoot
$geotagScript = "$env:USERPROFILE\OneDrive - Soaren Management\Desktop\geotag_photos_from_gpx.py"

if (-not (Test-Path $pctRoot)) {
    Write-Error "Canonical PCT data folder not found: $pctRoot"
    exit 1
}

Write-Host "==> Emily's PCT site update"
Write-Host "    data root : $pctRoot"
Write-Host "    site root : $siteRoot"
Write-Host ""

# 1. Geotag any new photos in photos_incoming\
$incoming = Get-ChildItem "$pctRoot\photos_incoming" -File -Filter "*.jp*g" -ErrorAction SilentlyContinue
if ($incoming -and $incoming.Count -gt 0) {
    Write-Host "[1/2] Geotagging $($incoming.Count) incoming photo(s)..."
    python $geotagScript
    if ($LASTEXITCODE -ne 0) { Write-Error "geotag step failed"; exit 1 }
    Write-Host ""
    Write-Host "    Note: incoming files are still in photos_incoming\."
    Write-Host "    Once you're happy with the result, you can delete them."
} else {
    Write-Host "[1/2] No new photos in photos_incoming\ — skipping geotag."
}
Write-Host ""

# 2. Build site data (notes -> markdown, KML+notes -> geojson, photos -> public/photos)
Write-Host "[2/2] Building site data..."
Push-Location $siteRoot
try {
    python scripts\build_data.py
    if ($LASTEXITCODE -ne 0) { Write-Error "build_data step failed"; exit 1 }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done. If the dev server is running, refresh your browser."
Write-Host "If not, run:  npm run dev"
