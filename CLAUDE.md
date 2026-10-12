# xbrief — notes for Claude

A twice-daily brief of what the accounts the operator follows on X posted. The operator's own Brave, on a profile
kept for the job, reads their Following tab in a background window, driven over the DevTools protocol; headless
Claude writes the brief; Caddy serves it as static files at xbrief.localhost. The tree's `../CLAUDE.md` applies in
full; this file adds only what is particular. Design, findings and decisions: `docs/ARCHITECTURE.md`.

## Start a session
`./bin/brief` — the doctor, then the last session's entry.

## End a session
An entry in `docs/SESSION_LOG.md`, then `./bin/handoff "summary"` (tests, clean tree, commit — this repo only).
After a code change: `./bin/restart` (compiles and tests before it reloads the LaunchAgents). After a change to
`browser.py` or `collect.py`, also `bin/tests --browser` (the real Brave against a fake x.com, about a minute).

## Rules
1. **Read only, and only the Following tab.** The job opens x.com/home, closes a Premium offer with Escape, clicks
   Following, and turns the mouse wheel. It never posts, likes, follows, replies, accepts a notice or terms, or opens
   another page. No "look busy" activity.
2. **Nothing runs inside the page.** Only the Page, Network, DOM and Input domains; no Runtime, no injected script,
   no request the page did not make itself.
3. **Anything X pushes back with ends the run**: an error status on the feed, a login or challenge page, a feed that
   stops loading, a notice in the way. Stop, retry nothing, say so at the top of the brief (`collect.py`).
4. **Direct, never the tunnel or a proxy**: the job's profile has no extension and the Mac no system proxy. The
   tree's one stated exception to its tunnel rule (`../docs/ARCHITECTURE.md` §2.6).
5. **The login is never read or printed by a session.** `~/Data/xbrief-data/secrets/` holds the job's Brave
   profile (guard rule 8). The operator logs in through `bin/xbrief login`.
6. **The window never takes the front.** Brave starts with no window, opens one in the background and parks it at
   the right edge of the rightmost screen (40 px showing). Never hide or minimise it: a hidden page reports itself
   hidden and stops drawing (`browser.py`; `test_browser_live.py` checks visible, active, never in front).
7. **Post text is untrusted.** The writer runs `claude -p` with no tools, no MCP servers, every connector denied, and
   returns JSON only; the page builds every link and byline from the posts, escapes all text, runs no script and
   loads images from pbs.twimg.com only.
8. **Offline tests never touch the network or the real data dir** (`tests/conftest.py`).

## Commands
`bin/brief` · `bin/doctor` · `bin/restart` · `bin/tests [--browser]` · `bin/handoff "summary"` ·
`bin/install-agent [--page]` · `bin/xbrief run [--now] [--label am|pm] [--hours H] [--max-pages N]` · `bin/xbrief probe` ·
`bin/xbrief status` · `bin/xbrief rebrief <raw.json.gz>` · `bin/xbrief login` (opens a window for the operator).

## Traps
- **x.com runs two web apps** (2026-10-12): the old one (feed at x.com/i/api/graphql/…/HomeLatestTimeline) and a
  new Relay one (api.x.com/graphql/…/HomeLatestTimelineQuery). The operator's account got the old one. Their post
  layouts differ; `parse.py` reads both; `collect.TIMELINE` matches both.
- **A fresh profile's Following tab is in Popular order** (`enableRanking: true`), which mixes old posts in. The
  job switches it to Recent through the tab's menu; the raw file's `ranked` says which order a run read.
- **X's first Recent page holds ~100 posts.** Stalls are judged at the page's end (`browser.at_bottom`), never by a
  plain count of wheel turns.
- **Chromium refuses remote control of a browser's everyday profile**, hence the job's own profile.
- **`open -g` alone does not keep Brave in the background**: it activates itself when its first window opens.
  `--no-startup-window` plus a background window from `Target.createTarget` does.
- **macOS keeps 40 px of any window on screen**, and the operator's laptop screen sits left of the main display, so
  "off-screen" is 40 px at the right edge of the rightmost screen (`browser.park_left`).
- **Plain headless Brave `--screenshot` hangs here.** Drive Brave over CDP to look at a brief.
- **A heredoc that names a file under `secrets/` is blocked by the guard**, even prose fed to python. Use the Edit tool.

## Where things live
`xbrief/` (config, browser, collect, parse, brief, page, cli) · `tests/` (`fake_x.py`, `test_browser_live.py`) ·
`ops/launchd` (`com.xbrief.am`, `com.xbrief.pm`) · `ops/caddy/xbrief.caddy` · data `~/Data/xbrief-data/`
(secrets/brave, raw/, briefs/, logs/, state.json, venv/).
