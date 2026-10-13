# Start HERMESX — every half somewhere of its own, then the terminal on screen.
#
#   .\dev.ps1                 everything, skipping whatever is already up
#   .\dev.ps1 -Tabs           one Windows Terminal window, a tab per service
#   .\dev.ps1 -Force          start anyway (will fail on a port clash)
#   .\dev.ps1 -CollectorOnly  just the feeds — no Next.js, no browser
#   .\dev.ps1 -NoBrowser      start everything, but leave the browser alone
#   .\dev.ps1 -NoGexygen      skip the borrowed gamma levels entirely
#   .\dev.ps1 -Prod           the web half as a production build, not `next dev`
#
# It ends by opening http://localhost:3100, because starting servers and
# stopping there is not "running the app" — it is running the services. The
# desktop shortcut lands here (scripts\install-shortcut.ps1), and a double-click
# that lights up terminals and shows no terminal looks like it did nothing.
#
# A PLACE EACH, because they are different things to watch. The COLLECTOR is the
# live source feed: one row per source per refresh, with item counts and the age
# of the bytes. The WEB one is just Next.js. Whether those places are separate
# windows or tabs in one window is the only thing -Tabs decides — the desktop
# shortcut passes it, since three windows fanned across the desktop is the cost
# of a double-click, while typing `.\dev.ps1` in a terminal you already have
# open is not the same situation.
#
# IDEMPOTENT ON PURPOSE. Running this twice is the normal case — you come back
# to the project and do not remember which halves survived, and starting a
# second uvicorn on a bound port fails with an oblique WinError 10048. Each
# half is skipped if its port is already listening, which also makes "run the
# app" safe to ask for repeatedly. It is also how you get the browser tab back
# after closing it: click again, nothing restarts, the browser opens.
#
# PORTS ARE 8100/3100, NOT 8000/3000. GEXYGEN owns those, this terminal reads
# GEXYGEN's gamma levels, and the two are expected to be up at the same time.
#
# -PROD IS FOR READING, THE DEFAULT IS FOR CHANGING. `next dev` runs React's
# development build — every render checked twice over, every module compiled on
# first request — and a terminal left open all day pays for that all day
# (measured 2026-10-13: the board's renders cost several times what the same
# work does in production). -Prod builds once (`npm run prod`: `next build`,
# then `next start` on the same port) and serves the result. The build goes to
# `.next-prod`, never `.next`, so it cannot break a `next dev` that is serving
# from the other directory. The cost is the build itself, a minute or so, and
# that an edit to the code needs the web half restarted to show. Switching modes
# means stopping the web half first — like everything here, an already-bound
# 3100 is left alone.
param(
    [switch]$Force,
    [switch]$Tabs,
    [switch]$CollectorOnly,
    [switch]$NoBrowser,
    [switch]$NoGexygen,
    [switch]$Prod
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# The desktop shortcut runs this file WITHOUT -NoExit: what it spawns carries
# its own, and a leftover window that only ever says "Web app ->
# http://localhost:3100" is noise — doubly so under -Tabs, where the services
# are tidied into one window and this would be the one thing left outside it.
# That makes this window self-closing, so an error on the way out would flash
# past unread. Hold it instead.
function Stop-Here([string]$Message) {
    Write-Host $Message -ForegroundColor Red
    Write-Host "Press Enter to close." -ForegroundColor DarkGray
    # Swallowed: a non-interactive host (CI, a piped run) has no console to
    # read from, and the point of the pause is only to keep a human from
    # missing the message.
    try { [void](Read-Host) } catch {}
    exit 1
}
trap { Stop-Here $_ }

function Test-Port([int]$Port) {
    $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

# -Tabs needs Windows Terminal, which ships with Windows 11 but is not
# guaranteed — a machine without it gets told once and gets a window per service,
# because a launcher that refuses to launch over its own cosmetics is worse than
# one that looks untidy.
$WT_WINDOW = "hermesx"
$useTabs = $false
if ($Tabs) {
    if (Get-Command wt.exe -ErrorAction SilentlyContinue) {
        $useTabs = $true
    } else {
        Write-Host "Windows Terminal (wt.exe) not found - falling back to a window per service." -ForegroundColor Yellow
    }
}

# Whether the first tab's window has to be waited for. See Start-InWindow: a
# terminal that is ALREADY running is already the monarch, which is the common
# case here — with Windows Terminal as the default console, the window running
# this very script is one.
$script:wtUp = $null -ne (Get-Process WindowsTerminal -ErrorAction SilentlyContinue)

# Said out loud in the progress lines, so what you are told to go and look at
# matches what is actually on screen.
$place = if ($useTabs) { "tab" } else { "window" }

# One service, one place to watch it: a tab under -Tabs, a window otherwise.
#
# The parameter is $PsArgs, not $Args: `$Args` is a PowerShell automatic
# variable, so declaring it as a parameter silently binds nothing and launches
# a bare, scriptless window instead of the service.
#
# PATHS ARE QUOTED BY HAND, for both launchers. Neither -ArgumentList nor wt's
# own parser quotes anything on your behalf — the array is joined on spaces —
# so an unquoted path splits the moment this repo lives somewhere like
# "C:\My Projects\".
function Start-InWindow([string[]]$PsArgs, [string]$Title, [string]$WorkDir, [switch]$PinTitle) {
    $shell = @("-NoExit", "-NoProfile") + $PsArgs

    if (-not $useTabs) {
        if ($WorkDir) { Start-Process powershell -WorkingDirectory $WorkDir -ArgumentList $shell }
        else { Start-Process powershell -ArgumentList $shell }
        return
    }

    # -w names the window, which is what collects the services instead of
    # scattering them: the first call creates "hermesx", every later one — this
    # run or the next click — drops its tab into the same window. -d is the
    # tab's own working directory, so each half starts where it belongs.
    $wtArgs = @("-w", $WT_WINDOW, "new-tab", "--title", "`"$Title`"")
    if ($WorkDir) { $wtArgs += @("-d", "`"$WorkDir`"") }
    # --title IS ONLY A STARTING TITLE: anything running in the tab can rename
    # it, and the point of a tab strip is that you can tell the halves apart at a
    # glance. GEXYGEN's collector renames itself to "GEXYGEN collector (no
    # store)", which is better than what we passed and is left to win. Next.js
    # renames its tab to "next-server (v15.5.24)", which says nothing about which
    # app it is serving — so that one is pinned.
    if ($PinTitle) { $wtArgs += "--suppressApplicationTitle" }
    Start-Process wt -ArgumentList ($wtArgs + @("powershell") + $shell)

    # THE FIRST TAB'S WINDOW HAS TO EXIST BEFORE THE SECOND IS ASKED FOR.
    # `wt -w <name>` is a request to whichever Windows Terminal process is the
    # "monarch"; with none running, two requests fired back to back each decide
    # they are it, and the services end up split across two windows — precisely
    # what -Tabs exists to prevent. It is a narrow race and a real one: the
    # collector's start is followed by a port wait, but a run that only needs
    # gamma and the web app fires those two with nothing in between. Once ANY
    # terminal is up there is a monarch to answer, so this is waited for once
    # and then never again.
    if (-not $script:wtUp) {
        for ($i = 0; $i -lt 40 -and -not (Get-Process WindowsTerminal -ErrorAction SilentlyContinue); $i++) {
            Start-Sleep -Milliseconds 250
        }
        # The process existing is not the same as it having claimed the crown.
        Start-Sleep -Milliseconds 800
        $script:wtUp = $true
    }
}

# Env wins, then ..\.env.local, then the compiled default — the same precedence
# server\run.ps1 and server\newsterminal\config.py apply, so the launcher can
# never disagree with the service about where things are. That agreement is the
# whole point of reading the file rather than assuming 8000: a terminal pointed
# somewhere else must not have a local service started underneath it.
function Get-Setting([string]$Key, [string]$Default) {
    $fromEnv = [Environment]::GetEnvironmentVariable($Key)
    if ($null -ne $fromEnv) { return $fromEnv }
    $envFile = Join-Path $here ".env.local"
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            $t = $line.Trim()
            if ($t -and -not $t.StartsWith("#") -and $t.Contains("=")) {
                $k = $t.Substring(0, $t.IndexOf("=")).Trim()
                $v = $t.Substring($t.IndexOf("=") + 1).Trim().Trim('"')
                # Matching run.ps1, a key present but blank in the file is not
                # a setting — it never reaches the service's environment, so it
                # must not change this decision either.
                if ($k -eq $Key -and $v) { return $v }
            }
        }
    }
    return $Default
}

$collectorUp = Test-Port 8100
$webUp = Test-Port 3100

if ($collectorUp -and -not $Force) {
    Write-Host "Collector -> already running on 8100, leaving it alone" -ForegroundColor DarkGray
} else {
    Write-Host "Collector -> http://127.0.0.1:8100  (live source feed, $place of its own)" -ForegroundColor Green
    Start-InWindow @("-ExecutionPolicy", "Bypass", "-File", "`"$(Join-Path $here 'server\run.ps1')`"") `
        -Title "HERMESX collector" -WorkDir (Join-Path $here "server")

    # The terminal reads the collector on first paint, so give it a moment to
    # bind. Without this the first load lands on the offline banner and then
    # corrects itself on the next poll - alarming, and for no reason.
    for ($i = 0; $i -lt 24 -and -not (Test-Port 8100); $i++) { Start-Sleep -Milliseconds 500 }
    if (-not (Test-Port 8100)) {
        Write-Host "  (still binding - check the collector $place if the page shows the offline banner)" -ForegroundColor Yellow
    }
}

# ---------------------------------------------------------------------------
# GEXYGEN's collector — A CONVENIENCE, NOT A DEPENDENCY.
#
# The Levels panel borrows seven gamma numbers per asset from GEXYGEN's compute
# service on 8000 (sources\gex.py). Those two projects are separate and stay
# separate: HERMESX runs standalone, every other panel works with GEXYGEN gone,
# and the panel already has a designed offline state for exactly this. What was
# missing was only that starting the terminal meant remembering to go and click
# a second shortcut first.
#
# So this is LAUNCH-TIME CONVENIENCE and nothing more. It imports nothing, it
# waits on nothing, and every way it can fail — no GEXYGEN on this machine, a
# moved folder, a service that will not start — is a DarkGray note and a
# carry-on, never an error and never a stop. Nothing below this block reads its
# result. Delete GEXYGEN from the disk and the terminal still comes up.
#
# It starts the COLLECTOR ALONE, not GEXYGEN's own dev.ps1: levels.txt is the
# whole of what this terminal reads, and the dashboard on 3000 would be a second
# app and a second browser tab nobody asked for. -NoStore matches the owner's
# own GEXYGEN Collector shortcut — chart feed only, no Supabase writes.
# ---------------------------------------------------------------------------
if (-not $NoGexygen) {
    $gexApi = Get-Setting "NT_GEXYGEN_API" "http://127.0.0.1:8000"

    # THE PORT COMES OUT OF THE CONFIGURED URL, not a hardcoded 8000. 8000 is
    # only GEXYGEN's default; the one that matters is the one this terminal will
    # actually read, and checking a different port than the config names is how
    # you get "already running" printed over a service nobody is talking to.
    $gexHost = $null
    $gexPort = 0
    if ($gexApi) { try { $u = [uri]$gexApi; $gexHost = $u.Host; $gexPort = $u.Port } catch { } }

    # NT_GEXYGEN_HOME overrides; otherwise look beside this repo, which is where
    # it sits (both live on the Desktop). Test-Path is case-insensitive on
    # Windows, so one spelling covers GEXYGEN/Gexygen/gexygen.
    $gexRun = $null
    foreach ($dir in @($env:NT_GEXYGEN_HOME, (Join-Path (Split-Path -Parent $here) "Gexygen"))) {
        if ($dir) {
            $candidate = Join-Path $dir "server\run.ps1"
            if (Test-Path $candidate) { $gexRun = $candidate; break }
        }
    }

    # gex.py treats an EMPTY NT_GEXYGEN_API as "gamma off by configuration", so
    # this honours the same reading. Belt and braces on Windows, where a process
    # cannot really hold an empty variable — `$env:X = ''` DELETES it, and so
    # does `set X=`, which is why a blank line in .env.local disables nothing.
    # The switch that actually works from here is -NoGexygen.
    if (-not $gexApi) {
        Write-Host "Gamma     -> off (NT_GEXYGEN_API is empty), so the Levels panel will say so" -ForegroundColor DarkGray
    } elseif ($gexHost -notin @("127.0.0.1", "localhost", "::1")) {
        # Pointed at another machine — or at nothing parseable. Either way there
        # is nothing local to start, and starting a local one anyway would bind
        # a port the config is not reading and quietly mean nothing. This is
        # ahead of the port check on purpose: something else listening on 8000
        # must not be reported as "GEXYGEN, already up" when the terminal is
        # reading a different host entirely.
        Write-Host "Gamma     -> $gexApi is not local, so nothing to start here" -ForegroundColor DarkGray
    } elseif (Test-Port $gexPort) {
        Write-Host "Gamma     -> GEXYGEN already running on $gexPort, leaving it alone" -ForegroundColor DarkGray
    } elseif (-not $gexRun) {
        Write-Host "Gamma     -> no GEXYGEN found beside this repo; the Levels panel will say so" -ForegroundColor DarkGray
        Write-Host "             (set NT_GEXYGEN_HOME if it lives somewhere else)" -ForegroundColor DarkGray
    } else {
        Write-Host "Gamma     -> $gexApi  (GEXYGEN collector, no store, $place of its own)" -ForegroundColor Green
        # Best effort in the most literal sense. A GEXYGEN that will not start
        # is GEXYGEN's problem, shown in GEXYGEN's own tab; this terminal is not
        # entitled to fail over it, and $ErrorActionPreference = "Stop" would
        # otherwise make a missing powershell.exe or a locked profile do just
        # that.
        try {
            Start-InWindow @("-ExecutionPolicy", "Bypass", "-File", "`"$gexRun`"", "-NoStore") `
                -Title "GEXYGEN collector" -WorkDir (Split-Path -Parent $gexRun)
        } catch {
            Write-Host "             (could not start it: $($_.Exception.Message) - carrying on without gamma)" -ForegroundColor DarkGray
        }
        # DELIBERATELY NOT WAITED ON. The collector above polls GEXYGEN on its
        # own refresh cycle and shows a designed offline state until it answers,
        # so a few seconds of "not yet" costs a banner that was already built to
        # be seen. Blocking the terminal's own startup on a borrowed, optional
        # feed is the coupling this whole block exists to avoid.
    }
}

if ($CollectorOnly) {
    Write-Host ""
    Write-Host "Collectors only. Ctrl-C in a $place stops that one." -ForegroundColor DarkGray
    return
}

if (-not (Test-Path (Join-Path $here "node_modules"))) {
    Stop-Here "node_modules missing - run 'npm install' first."
}

if ($webUp -and -not $Force) {
    Write-Host "Web app   -> already running on 3100, leaving it alone" -ForegroundColor DarkGray
} else {
    $webCmd = if ($Prod) { "npm run prod" } else { "npm run dev" }
    $mode = if ($Prod) { "production build - a minute to build first" } else { "next dev" }
    Write-Host "Web app   -> http://localhost:3100  ($mode)" -ForegroundColor Green
    # A working directory rather than a `-Command "Set-Location X; npm run dev"`
    # chain: neither launcher quotes its array, so that chain reaches
    # powershell.exe unquoted, launches, serves one request and dies. Keeping
    # -Command to a single bare token avoids the whole question — and it has to
    # stay that way for wt too, whose parser would take the `;` for its own.
    # The build-then-start chain for -Prod lives in package.json for the same
    # reason.
    Start-InWindow @("-Command", $webCmd) -Title "HERMESX web" -WorkDir $here -PinTitle
}

# Open the terminal. This runs whether or not the web half was already up: you
# asked for the app, so the app belongs on screen either way, and a second click
# on the shortcut is how you get the tab back after closing it.
#
# next dev binds 3100 well before its first compile finishes, so the browser may
# sit on a blank tab for a few seconds. That is Next.js compiling, not a hang.
# The ceiling is generous because a cold start after a dependency change is
# slow; the loop exits the moment the port is listening.
if (-not $NoBrowser) {
    # -Prod binds only after the build, so it gets four minutes, not one.
    $waits = if ($Prod) { 480 } else { 120 }
    for ($i = 0; $i -lt $waits -and -not (Test-Port 3100); $i++) { Start-Sleep -Milliseconds 500 }
    if (Test-Port 3100) {
        # ?tab=terminal RATHER THAN THE BARE URL, and it has to be explicit: the
        # app remembers the tab you were last on, so a bare address reopens the
        # report or the settings pane if that is where you left off. Clicking a
        # thing called HERMESX asks for the terminal.
        Write-Host "Terminal  -> opening http://localhost:3100/?tab=terminal" -ForegroundColor Green
        Start-Process "http://localhost:3100/?tab=terminal"
    } else {
        Write-Host "Web app never bound port 3100 - check the web $place." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Ctrl-C in a $place stops that half." -ForegroundColor DarkGray
