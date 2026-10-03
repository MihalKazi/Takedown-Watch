# Takedown Watch: automated crawl -> export -> build -> deploy.
# Does NOT touch review/annotation (tw review / tw annotate) - that stays human-only,
# per CLAUDE.md invariant 1. New events just accumulate in the internal dashboard
# until a person reviews them.
#
# Run manually: powershell -File scripts\refresh-and-deploy.ps1
# Or via the scheduled task set up alongside this script (see setup-schedule.ps1).

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Step($name, $block) {
    Write-Host "== $name ==" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "$name failed with exit code $LASTEXITCODE"
    }
}

Step "crawl" {
    Set-Location "$root\pipeline"
    python -m uv run tw crawl --max-articles 200
}

Step "export (public dataset)" {
    Set-Location "$root\pipeline"
    python -m uv run tw export
}

Step "export-internal (dashboard data)" {
    Set-Location "$root\pipeline"
    python -m uv run tw export-internal
}

Step "build site" {
    Set-Location $root
    npm --prefix web run build
}

Step "deploy to Cloudflare Pages" {
    Set-Location "$root\web"
    npx wrangler pages deploy dist --project-name takedown-watch --branch main --commit-dirty=true
}

Set-Location $root
Write-Host "Done. Internal dashboard: https://takedown-watch.pages.dev/internal/events/" -ForegroundColor Green
Write-Host "New events still need a human: tw review / tw annotate before anything reaches the public site." -ForegroundColor Yellow
