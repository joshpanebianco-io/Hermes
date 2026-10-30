# Start the HERMES collector.
#   .\server\run.ps1
#
# The window this opens IS the feed: one row per source per refresh, with the
# item count, the age of the bytes and whether they came from the network or
# the cache. Anything degraded gets its own `└─` line underneath, so a dead
# publisher cannot hide between healthy rows.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $here ".venv\Scripts\python.exe"

# Load ..\.env.local so there is ONE place to put configuration. The service
# reads os.environ and has no dotenv dependency (it is stdlib-only bar
# fastapi/uvicorn/tzdata), which would otherwise leave the Python half needing
# hand-exported shell variables while the web half read a file.
#
# Existing environment wins, so a deliberately exported variable is never
# silently overridden by a stale file — but that rule has teeth: `Set-Item env:`
# writes to the PROCESS, so values set by an earlier run of this script outlive
# it inside the same terminal. Warn on DIVERGENCE rather than on a mere skip.
$envFile = Join-Path (Split-Path -Parent $here) ".env.local"

# RESTART IN PLACE (owner, 2026-10-14: "make sure all the seperate terminal
# windows are in one terminal window but with mutliple tabs"). With the halves
# as tabs, a restart that killed this window and opened a fresh one left a dead
# "[process exited with code 1]" tab behind every time. So `dev.ps1 -Restart`
# drops a marker beside this script and stops the uvicorn process; finding the
# marker when uvicorn returns, this goes round again in the SAME tab. No marker
# — Ctrl-C, or a crash — and it stops as it always did, traceback on screen.
$restartFlag = Join-Path $here ".restart"
# What the last pass took from .env.local, so the next one rereads the FILE: a
# restart is how an edit to it (a new model, a new key) is picked up, and the
# existing-environment-wins rule would otherwise keep the old value and call it
# "IGNORED".
$fromFile = @()
while ($true) {
    foreach ($k in $fromFile) { Remove-Item -Path "env:$k" -ErrorAction SilentlyContinue }
    $fromFile = @()
    if (Test-Path $envFile) {
        $stale = @()
        Get-Content $envFile | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
                $k = $line.Substring(0, $line.IndexOf("=")).Trim()
                $v = $line.Substring($line.IndexOf("=") + 1).Trim().Trim('"')
                if ($k -and $v) {
                    $cur = [Environment]::GetEnvironmentVariable($k)
                    if ($null -eq $cur) { Set-Item -Path "env:$k" -Value $v; $fromFile += $k }
                    elseif ($cur -cne $v) { $stale += $k }
                }
            }
        }
        if ($stale.Count) {
            Write-Host "IGNORED - already set in this shell and DIFFERENT from .env.local:" -ForegroundColor Red
            Write-Host "  $($stale -join ', ')  <- your file edit is NOT in effect" -ForegroundColor Red
            Write-Host "  Remove-Item env:<NAME> then re-run, or open a new terminal." -ForegroundColor Red
        }
        Write-Host "Loaded .env.local" -ForegroundColor Cyan
    }

    if (-not (Test-Path $py)) {
        Write-Host "Creating venv..." -ForegroundColor Cyan
        py -m venv (Join-Path $here ".venv")
        & $py -m pip install --disable-pip-version-check -q -r (Join-Path $here "requirements.txt")
    }

    $gex = if ($env:NT_GEXYGEN_API) { $env:NT_GEXYGEN_API } else { "http://127.0.0.1:8000" }
    $port = if ($env:NT_PORT) { $env:NT_PORT } else { "8100" }

    Write-Host "HERMES collector -> http://127.0.0.1:$port" -ForegroundColor Green
    Write-Host "Gamma levels from       $gex  (GEXYGEN; panel says so if it is down)" -ForegroundColor DarkGray
    Write-Host "PERSONAL USE ONLY - Yahoo quotes and publisher RSS are not redistributable." -ForegroundColor Yellow
    Write-Host "Ctrl-C to stop. One row per source per refresh below." -ForegroundColor DarkGray

    # --no-access-log: the terminal polls every 20s and one uvicorn access line per
    # poll would bury the source table this window exists to show. Startup,
    # warnings and tracebacks still print; only the routine 200s go.
    & $py -m uvicorn newsterminal.api:app --host 127.0.0.1 --port $port --app-dir $here --no-access-log

    if (-not (Test-Path $restartFlag)) { break }
    Remove-Item $restartFlag -Force -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "---- restarting (dev.ps1 -Restart) $(Get-Date -Format 'HH:mm:ss') ----" -ForegroundColor Cyan
}
