# Put a HERMES shortcut on the desktop.
#
#   .\scripts\install-shortcut.ps1              # or: npm run shortcut
#   .\scripts\install-shortcut.ps1 -Collector   # or: npm run shortcut:collector
#
# The default is the APP. Double-clicking it runs dev.ps1 -Tabs: the collector
# and Next.js start as TABS IN ONE Windows Terminal window, GEXYGEN's collector
# joins them in a third if it is on this machine, and the terminal then opens in
# the browser. Every half is skipped if already up, so a second click is safe,
# adds only the tabs that are missing to the same window, and is also how to get
# the browser tab back after closing it.
#
# Tabs are dev.ps1's default now (owner, 2026-10-14: every service in one
# window), so -Tabs here changes nothing; it stays so a shortcut made before
# and one made now run exactly the same command. `dev.ps1 -Windows` is the old
# window-per-service arrangement.
#
# -Collector installs the feed-only launcher under its own name, so the two sit
# side by side on the desktop. That one opens the collector ALONE: the live
# source table and the JSON on 8100, no Next.js, no browser.
#
# Re-running replaces the shortcut in place, which is also how to repair it if
# the repo moves. The icon is public\hermes.ico, made by scripts\make-icon.mjs.
param(
    [switch]$Collector,
    [string]$Name
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$icon = Join-Path $root "public\hermes.ico"
if (-not (Test-Path $icon)) { throw "Missing $icon - run: npm run icon" }

if ($Collector) {
    $target = Join-Path $root "server\run.ps1"
    # -NoExit so a service that dies at startup leaves its traceback on screen
    # instead of a window that flashes and vanishes. This window IS the feed.
    $flags = @("-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$target`"")
    $defaultName = "HERMES Collector"
    $description = "HERMES collector - the live source feed on http://127.0.0.1:8100. No web app, no browser."
} else {
    $target = Join-Path $root "dev.ps1"
    # No -NoExit here: dev.ps1 only dispatches, and the windows it opens carry
    # their own. Leaving a third window behind that says nothing but "Web app ->
    # http://localhost:3100" is clutter, so this one reports progress and
    # closes. dev.ps1 pauses itself on an error path so a failure still stays
    # readable.
    $flags = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$target`"", "-Tabs")
    $defaultName = "HERMES"
    $description = "HERMES - starts the collector, the web app and GEXYGEN's gamma collector if present as tabs in one window, then opens http://localhost:3100."
}
if (-not $Name) { $Name = $defaultName }
if (-not (Test-Path $target)) { throw "Missing $target" }

$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "$Name.lnk"
$powershell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut($lnkPath)
$lnk.TargetPath = $powershell
$lnk.Arguments = $flags -join " "
$lnk.WorkingDirectory = Split-Path -Parent $target
$lnk.IconLocation = "$icon,0"
$lnk.Description = $description
$lnk.WindowStyle = 1
$lnk.Save()

Write-Host "Shortcut -> $lnkPath" -ForegroundColor Green
Write-Host "Runs     -> powershell $($lnk.Arguments)" -ForegroundColor DarkGray
