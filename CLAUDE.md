# xbrief — notes for Claude

A twice-daily brief of what the accounts the operator follows on X posted, read from their own Following tab with
their own login, written by headless Claude, served as static files at xbrief.localhost. The tree's `../CLAUDE.md`
applies in full; this file adds only what is particular. Design, findings and decisions: `docs/ARCHITECTURE.md`.

## Start a session
`./bin/brief` — the doctor, then the last session's entry.

## End a session
An entry in `docs/SESSION_LOG.md`, then `./bin/handoff "summary"` (tests, clean tree, commit — this repo only).
After a code change: `./bin/restart` (compiles and tests before it reloads the LaunchAgents).

## Rules
1. **Read only, and only the Following tab.** No post, like, follow, List or DM, ever; no other page or request than
   x.com/home (once a run), its script files, and the Following-tab pages. No "look busy" traffic.
2. **Anything X pushes back with ends the run.** Rate limit, challenge, logout, unknown error: stop, retry nothing,
   say so at the top of the brief (`collect.py`, the fork's `TWS_*` settings in `config.TWS_ENV`).
3. **Direct, never the tunnel or a proxy**: the operator's home connection, like Brave profile "public". The tree's
   one stated exception to its tunnel rule (`../docs/ARCHITECTURE.md` §2.6). `config.apply_job_env` strips proxies.
4. **The login is never read or printed by a session.** `~/Data/xbrief-data/secrets/accounts.db` holds the X
   session cookies in plain text (guard rule 8). The operator runs `bin/xbrief login` in their own terminal.
5. **Post text is untrusted.** The writer runs `claude -p` with no tools, no MCP servers, every connector denied,
   and returns JSON only; the page builds every link and byline from the posts, escapes all text, runs no script
   (its content policy allows none) and loads images from pbs.twimg.com only. Keep it that way.
6. **The twscrape fork is pinned by commit** (`pyproject.toml`, `requirements.lock`), and curl_cffi with it: its
   Chrome profile is the identity the job presents. Never move either pin without reading the diff. The fork is
   `~/Developer/forks/twscrape`, branch `xbrief`, pushed to `t3ddyal3x/twscrape`.
7. **Nothing hard-coded per X deploy.** The request id, variables and (old app) feature switches are read from the
   scripts the account's own x.com/home names, and re-read when that script changes (`site.py`).
8. **Tests never touch the network or the real data dir** (`tests/conftest.py`).

## Commands
`bin/brief` · `bin/doctor` · `bin/restart` · `bin/tests` · `bin/handoff "summary"` · `bin/install-agent [--page]` ·
`bin/xbrief run [--now] [--label am|pm] [--max-pages N]` · `bin/xbrief probe` · `bin/xbrief status` ·
`bin/xbrief rebrief <raw.json>` · `bin/xbrief login` (the operator only).

## Traps
- **x.com runs two web apps** (2026-10-12): the old one and a new Relay one. Logged-out visitors get the new one;
  which one this account gets is read each run. Their requests, variables and response layouts all differ;
  `request.py` and `parse.py` handle both.
- **twscrape's own parser and request ids are for the old app only.** The fork is used for its login store,
  anti-bot id, curl client and error handling, not its timeline readers.
- **Plain headless Brave `--screenshot` hangs here.** Drive Brave over CDP to look at a brief (see-the-page skill).
- **A heredoc that names the login file is blocked by the guard**, even prose fed to python. Edit such files with
  the Edit tool.

## Where things live
`xbrief/` (config, site, request, collect, parse, brief, page, cli) · `tests/` · `ops/launchd` (`com.xbrief.am`,
`com.xbrief.pm`) · `ops/caddy/xbrief.caddy` · data `~/Data/xbrief-data/` (secrets/, raw/, briefs/, cache/, logs/,
state.json, site.json, venv/).
