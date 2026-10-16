# xbrief — notes for Claude

A twice-daily brief of what the accounts the operator follows on X posted. The operator's own Brave, on a profile
kept for the job, reads their Following tab in a background window, driven over the DevTools protocol; headless
Claude writes the brief; the app (`server.py`, port 8795, xbrief.localhost) shows it, keeps every brief and post
for history and search, starts a run from its Brief now button, and runs the schedule set on its History page.
Its Sites tab (`sites.py`) reads the public sites in `config.SITES` once a day and summarises each new post.
The tree's `../CLAUDE.md` applies in full; this file adds only what is particular. Design, findings and decisions: `docs/ARCHITECTURE.md`.

## Start a session
`./bin/brief` — the doctor, then the last session's entry.

## End a session
An entry in `docs/SESSION_LOG.md`, then `./bin/handoff "summary"` (tests, clean tree, commit — this repo only).
After a code change: `./bin/restart` (compiles and tests before it restarts the app; a run going is left to
finish). After a change to `browser.py` or `collect.py`, also `bin/tests --browser` (the real Brave against a fake x.com, about a minute).

## Rules
1. **Read only: the Following tab, then each new Article's post.** The job opens x.com/home, closes a Premium offer
   with Escape, clicks Following, and turns the mouse wheel. After a read that ended on its own terms it opens the
   page of each post in the brief that carries an X Article (newest first, at most `config.MAX_ARTICLES`, a few
   seconds each) and keeps what that page fetches, so the writer reads every Article whole (operator, 2026-10-15).
   It never posts, likes, follows, replies, accepts a notice or terms, or opens any other page. No "look busy" activity.
2. **Nothing runs inside the page.** Only the Page, Network, DOM and Input domains; no Runtime, no injected script,
   no request the page did not make itself.
3. **Anything X pushes back with ends the run**: an error status on the feed or a post's page, a login or challenge
   page, a feed that stops loading, a notice in the way. Stop, retry nothing, say so at the top of the brief (`collect.py`).
4. **Direct, never the tunnel or a proxy**: the job's profile has no extension and the Mac no system proxy. The
   tree's one stated exception to its tunnel rule (`../docs/ARCHITECTURE.md` §2.6).
5. **The login is never read or printed by a session.** `~/Data/xbrief-data/secrets/` holds the job's Brave
   profile (guard rule 8). The operator logs in through `bin/xbrief login`.
6. **The window never takes the front.** Brave starts with no window, opens one in the background and parks it at
   the right edge of the rightmost screen (40 px showing). Never hide or minimise it: a hidden page reports itself
   hidden and stops drawing (`browser.py`; `test_browser_live.py` checks visible, active, never in front).
7. **Post text is untrusted.** The writer runs `claude -p` with no tools, no MCP servers, every connector denied, and
   returns JSON only; the page builds every link and byline from the posts, escapes all text, runs only its own
   `static/app.js` (the server's CSP: `script-src 'self'`, no inline script or style) and loads images from
   pbs.twimg.com only.
8. **Offline tests never touch the network or the real data dir** (`tests/conftest.py`); the server is tested
   through a fake socket.
9. **One run at a time, whoever starts it**: `xbrief run` holds an flock on `run.lock` for its life (`runner.py`).
   The app starts a run as its own process (own session; the agent has `AbandonProcessGroup`), so restarting the app
   never cuts a read off with its Brave open.
10. **Nothing outside loopback can start a read**: the app refuses a non-loopback `Host` or `Origin`, and its
    writes (`/api/run`, `/api/settings`, `/api/sites`) take a JSON body only, which a cross-site form cannot send.
11. **The schedule is set on the page and lives in the store** (`store.settings`, `runner.due`), not in launchd.
    It starts off; a window slept through runs on waking, two due at once run only the later, and a slot within an
    hour of another run is skipped.
12. **The Sites tab reads public pages only, direct, and only on each source's own host** (`sites.same_host`): a
    plain GET of its RSS feed or sitemap and of each new post, no browser, no login. A source's first check only
    learns its list and reads the newest post. Page text is untrusted like post text (rule 7); its summariser is
    Opus (`config.SITE_MODEL`), never Sonnet. One check at a time (`sites.lock`), once a day after
    `config.SITES_AFTER`, on by default (the page's switch). A source's people (`x`, their handles) are shown from
    posts already kept from the Following tab (`sites.people_posts`); their profiles are never read (rule 1).
    Each write-up keeps its article's text (`text`), so the tab's search reaches the article, not only the summary.
    Unsearched, the people's column holds only posts naming one of their write-ups' `topics` (`sites.people_posts`).

13. **Long videos are read from their words, never their picture** (`videos.py`): a video of `config.VIDEO_MIN_S`
    or longer in a brief's posts (X's own, or a YouTube link) is transcribed and summarised before the writer runs.
    An X video: X's own captions where X made them, else Whisper large-v3 (MLX, local) on its audio track alone. A
    YouTube video: Whisper on its audio (yt-dlp), since YouTube refuses captions to scripts here. Public files,
    direct, outside the browser; the audio is deleted once transcribed. The summariser is `config.SITE_MODEL`
    (Opus, never Sonnet); the writer gets the summary, the page and search the whole transcript (`/video/<key>`).
    Transcripts are untrusted like posts (rule 7). Each is kept in `videos/` by key, so a rebrief never redoes one.

## Commands
`bin/brief` · `bin/doctor` · `bin/restart` · `bin/tests [--browser]` · `bin/handoff "summary"` ·
`bin/install-agent` · `bin/xbrief serve` · `bin/xbrief run [--now] [--label am|pm] [--hours H] [--max-pages N]` · `bin/xbrief probe` ·
`bin/xbrief status` · `bin/xbrief rebrief <raw.json.gz>` · `bin/xbrief articles <raw.json.gz>` (read a saved run's Articles, then rebrief) · `bin/xbrief login` (opens a window for the operator) ·
`bin/xbrief sites` (check the sites now).

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
`xbrief/` (config, browser, collect, parse, brief, cli, sites, videos, whisper; the app: server, page, store, runner, static/) · `tests/`
(`fake_x.py`, `test_browser_live.py`, `test_app.py`, `test_sites.py`) · `ops/launchd/com.xbrief.app.plist` · `ops/caddy/xbrief.caddy`
· data `~/Data/xbrief-data/` (secrets/brave, raw/, videos/, xbrief.db, run.lock, sites.lock, progress.json, logs/, state.json, venv/).
