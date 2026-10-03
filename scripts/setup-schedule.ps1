# One-time setup: registers a daily Windows Scheduled Task that runs
# refresh-and-deploy.ps1 automatically (crawl -> export -> build -> deploy).
# Run once, as the user who should own the task: powershell -File scripts\setup-schedule.ps1

$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts\refresh-and-deploy.ps1"
$taskName = "TakedownWatch-DailyRefresh"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Daily -At 3am   # low-traffic hour; change as you like

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Description "Takedown Watch: crawl, export, build, deploy. Does not review events (human-only)." `
    -Force

Write-Host "Scheduled task '$taskName' registered: runs daily at 3am." -ForegroundColor Green
Write-Host "View/edit: Task Scheduler app, or 'Get-ScheduledTask -TaskName $taskName'" -ForegroundColor Yellow
Write-Host "Remove it later with: Unregister-ScheduledTask -TaskName $taskName" -ForegroundColor Yellow
