# xbrief — how it works, what was found, what was decided

The plan it was built from is `../../docs/plans/2026-10-12_x-follows-brief.md`. Its decision 2 (twscrape) was
replaced the same day by the plan's own fallback, a real browser (operator, 2026-10-12: "real browser with the
devtools update"). This file records what the build found and where it differs from the plan.

## One run
1. launchd fires at the start of the window; `cli.jitter_seconds` waits a random part of it (never past the window
   end minus 15 minutes; a late wake runs at once).
2. `browser.Browser.start`: a separate Brave instance on `~/Data/xbrief-data/secrets/brave`, started with no
   window (`open -n -g … --no-startup-window`), one window opened in the background over the DevTools protocol and
   parked at the right edge of the rightmost screen. Flags keep a covered window from being throttled.
3. `collect.run`: open x.com/home; stop if the page lands on a login, landing or challenge path; close a Premium
   offer with Escape (a person would); wait a few seconds; click Following unless X already shows it (its own feed
   request says so). **If the feed request asks for Popular order** (`enableRanking: true`, which a fresh profile
   gets), choose **Recent** in the tab's own menu (click the selected tab, click Recent), as the operator's browser
   is set; the Popular pages read before the switch are dropped. If the menu is not there, read on in Popular order:
   the stop rule then waits for a whole page with nothing newer, the brief leaves out posts older than the last
   brief, and the brief says X is sorting by Popular. Then turn the mouse wheel at a reading pace (`wheel_pause`: about a second, now and then a long
   stop; `wheel_delta`: mostly down, now and then a glance back up). Every feed response the page downloads is kept
   (`Network.getResponseBody`).
4. Stop when a page reaches the newest post of the previous run (by post id, the newest in each entry, promoted
   posts ignored); or at the end of the feed, 15 wheel turns **at the end of the page** (`Page.getLayoutMetrics`,
   no script) without a new page, `MAX_PAGES` or `MAX_MINUTES`, each of which is a **gap** the brief names. X's
   first Recent page holds ~100 posts, so a plain count of turns called a stall too early (2026-10-12). Any error status, failed request, non-feed answer or blocked page ends the
   run at once. Brave is always closed, and killed if it does not close.
5. The pages are saved raw (`raw/`, one gzip a run, 30 days: a feed page is ~0.4 MB of JSON and compresses 7×); `brief.write` asks Claude; `page.render` writes the page and
   `index.html`; old raw files are pruned.

## Why a real browser
The first build used a pinned fork of twscrape and had to imitate the browser: headers, their order, the TLS
handshake, the anti-bot id, the request ids and variables of whichever web app X served. Reviewing and running it
found three things it got wrong or imitated imperfectly (below), and X changed under it twice in one day. In the
operator's own Brave, all of that is produced by Brave and x.com's own code: the identity is Brave 154 on this Mac
(checked: `Chrome/154.0.0.0` user agent, the operator's own build), the page's own requests, its own visibility
state (`visible`, so X's `x-twitter-active-user` is `yes`, checked on a fake x.com), and a deploy of x.com is
followed the way any browser follows it. What remains detectable is the remote-control channel itself; the job
uses no Runtime domain and runs no script in the page, which is where automation is usually noticed.

## What x.com is (read from its own code, 2026-10-12)
x.com is moving from its old web app (abs.twimg.com/responsive-web, requests to x.com/i/api/graphql with a features
block) to a new Relay one (abs.twimg.com/x-web, persisted queries to api.x.com/graphql, a new post layout:
`details.full_text`, `url_entities`, `media_entities2`, `entry_id` …). Logged out, x.com was the new app; the
operator's account was served the old one, whose Following-tab request (`NmDBT3APtNxDpMqIEauu7A/
HomeLatestTimeline`) is defined in a mapped chunk (`shared~bundle.Compose~bundle.HomeTimeline~bundle.LoggedInMain`),
not in main.js. `parse.py` reads both layouts.

## The twscrape fork (retired the same day, kept)
`t3ddyal3x/twscrape`, branch `xbrief` (0897080, one commit on v0.20.1), at `~/Developer/forks/twscrape`. Reviewing
v0.20.1 found that it loaded **x.com/tesla** with the account's cookies every run to compute the anti-bot id, that
its API calls carried **page-load headers** (`sec-fetch-mode: navigate`, `accept: text/html…`) instead of a page's
fetch() headers, and that it **retried on its own** in four places. The fork fixes all three behind settings. It is
no longer used; it stays for reference.

## The writer
`claude -p --tools "" --strict-mcp-config --mcp-config '{"mcpServers":{}}' --disallowedTools "mcp__*"`, run in the
data dir. Checked 2026-10-12: asked to list its tools, it answered NONE. `--bare` is not usable (it ignores the
subscription login). On made-up posts including an injection attempt, it summarised the attempt rather than obeying it,
and placed every post. A writer failure still publishes every post, unsummarised, with the reason.

## Decisions
- **The job's own Brave profile**, logged in once by the operator: Chromium does not allow remote control of an
  everyday profile, and the job must not touch the operator's open browser.
- **Parked, not hidden**: hiding the app (cmd+H) or minimising the window makes the page report itself hidden (X's
  `x-twitter-active-user: no`) and stop drawing, so the feed does not load (both checked 2026-10-12 on the fake
  x.com). macOS keeps 40 px of any window on screen, so the window waits at the right edge of the rightmost screen,
  behind the operator's windows.
- **A notice that needs the operator** (new terms, a challenge) ends the run; the job never accepts anything.
- **The page** follows the other local pages (Tokyo Night / Day), reads in Iowan Old Style, puts handles and times in
  a mono byline built from the data, and opens threads by default.
