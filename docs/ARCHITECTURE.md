# xbrief — how it works, what was found, what was decided

The plan it was built from is `../../docs/plans/2026-10-12_x-follows-brief.md`. Its decision 2 (twscrape) was
replaced the same day by the plan's own fallback, a real browser (operator, 2026-10-12: "real browser with the
devtools update"). This file records what the build found and where it differs from the plan.

## The app (2026-10-12)
The static page became an app on the operator's word ("make it into a full blown app"; chosen: a local web app like
macro, with a run button and history and search; X only). `server.py` on 127.0.0.1:8795 behind Caddy, the
standard library only, macro's loopback perimeter. Pages are built on the server (`page.py`); one script,
`static/app.js`, drives the Brief now button, the rail's live line (`/api/status`, every 1.5 s while a run goes,
30 s otherwise) and the schedule form. The CSP allows that script and the app's sheet, nothing inline.

- **The store** (`store.py`, `xbrief.db`, SQLite in WAL): a run is stored whole when its brief is written (meta,
  topics, conversations), each post once however many runs saw it, and an FTS5 index over each post's words (with
  what it reposts or quotes) and accounts. Posts are kept for good (a few hundred bytes each); raw reads, 30 days.
  Search words are each quoted and prefix-matched, so no input can be a query-syntax error.
- **Runs** are `xbrief run` processes, whoever starts them. An flock on `run.lock` keeps it to one; `progress.json`
  carries the phase and the page and post counts (`collect.run(progress=…)`) to the page. The app starts a run in
  its own session and the agent abandons its process group, so a restart never cuts a read off with Brave open.
- **The schedule** moved from two launchd agents (`com.xbrief.am`/`pm`, never loaded) into the app, so the page
  can turn it on and move its windows: settings in the store, one slot a day a window with a random fire time
  (`runner.pick_fire`, same rule as `cli.jitter_seconds`), checked every 20 s. A window slept through runs on
  waking (as launchd would); two due at once run only the later and skip the earlier, which loses nothing because
  a run reads from where the last stopped; a slot within an hour of another run is skipped; turning it on or moving
  it marks a window already over as skipped. Starts off.
- The two briefs of the static build were written again from their raw reads into the store; the old HTML folder
  `briefs/` went to the Trash.

## One run
1. The app's schedule (or the Brief now button, or a terminal) starts `xbrief run --now`; a scheduled run's start
   is already a random minute in its window. Without `--now`, `cli.jitter_seconds` waits a random part of it.
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
5. The pages are saved raw (`raw/`, one gzip a run, 30 days: a feed page is ~0.4 MB of JSON and compresses 7×);
   `brief.write` asks Claude; the run is stored (`store.save_run`); old raw files are pruned.

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

**Model and prompt** (2026-10-12): the writer is named, `claude-opus-5-5` (`config.MODEL`): Opus, the operator's
choice after both were timed; never Sonnet. It lists only the topics' posts; whatever it leaves out is shown at the
end. Timed on the 390-post read of 2026-10-12, one run each:

| writer | time | posts in topics | unsummarised posts of 50+ words |
|---|---|---|---|
| Fable, listing every post | 623 s | 235 | 13 |
| Fable, topics only | 315 s | 262 | 8 |
| Opus, topics only (kept) | 335 s | 252 | 12 |

(Sonnet was also tried, 80 s, and left 24 such posts unsummarised; ruled out by the operator.)

**What matters first** (2026-10-14, operator: "I just want my attention focused on stuff that matters"; "my attention
is focused on HYPE"). Topics are ordered by how much was said, so an essay became one sentence: that morning's brief
put @nic_carter's 5,400-character essay in topic 15 of 35, and the writer read only each post's first 2,000
characters. Now the writer gets every post whole (+4% input on that read), and its answer has three parts, a post in
one only: `hype` (one paragraph on HYPE and Hyperliquid), `theses` (any post that argues a claim, short ones too, no
cap, sorted longest first by the page's own count; each with claim, steps, if_it_holds, and Claude's view in
weak_spots and wrong_if, the one place for an opinion, labelled on the page), then `topics` as before. A HYPE thesis
is written up in the HYPE part; the rest on the Theses tab, with a line each on the Brief. A summary points at a post
that stands out with `[[post id]]`; the page links it to that post on X, built from the post, and drops an id not in
the brief. The writer's timeout went from 15 to 30 minutes for the longer answer.

## The Sites tab (2026-10-14)
The operator asked for "a separate engine parsing useful information like sigil": funds' and researchers' own sites,
checked daily, not their X accounts (reading a profile page would break rule 1). `sites.py`:
- **A source** (`config.SITES`) names its list: an RSS feed (Zee Prime, WordPress: the feed carries each post whole
  in `content:encoded`, used in place of the page) or a sitemap with a path to match (Sigil, whose site has no feed;
  `/blog/`). Only addresses on the source's own host are followed.
- **A check** reads each list; a post not in `site_posts` is fetched, its text taken from `<article>`, else
  `<main>`, else `<body>`, with scripts, navigation, headers and footers dropped, and given whole (up to 80,000
  characters) to `claude -p` with no tools, model Fable (`config.SITE_MODEL`: the operator prefers Fable for
  summaries). It returns gist, points, calls (positions and forecasts with their numbers) and view (Claude's,
  labelled on the page). A fetch or writer failure is kept on the post and shown; the post is not tried again.
- **The first check of a source** marks everything already listed as known (`baseline`) and reads the newest one,
  so adding a site never summarises its whole archive.
- **When**: the server's schedule loop starts `xbrief sites` as its own process once a day at its first look after
  07:00 (a day slept through runs on waking), unless the Sites page's switch is off; **Check now** starts one at
  once. Its own lock (`sites.lock`), so it runs beside an X read.
- Checked live 2026-10-14: Sigil's sitemap lists 53 posts, the newest the Q2 2026 letter (24,949 characters read);
  Zee Prime's feed lists 10, the newest "Argonauts Journey".

## Decisions
- **The job's own Brave profile**, logged in once by the operator: Chromium does not allow remote control of an
  everyday profile, and the job must not touch the operator's open browser.
- **Parked, not hidden**: hiding the app (cmd+H) or minimising the window makes the page report itself hidden (X's
  `x-twitter-active-user: no`) and stop drawing, so the feed does not load (both checked 2026-10-12 on the fake
  x.com). macOS keeps 40 px of any window on screen, so the window waits at the right edge of the rightmost screen,
  behind the operator's windows.
  Its own desktop (Space) was tried 2026-10-14: full screen took the front and the read timed out on the fake
  x.com; the Dock assigns a desktop per app (it would move the operator's own Brave too), and moving one window
  needs SIP off. The 40 px stays.
- **A notice that needs the operator** (new terms, a challenge) ends the run; the job never accepts anything.
- **The page** follows the other local pages (Tokyo Night / Day), reads in Iowan Old Style, puts handles, times and
  controls in a mono, builds bylines from the data, and folds each topic's and thesis's posts under its paragraph.
  Design pass 2026-10-14: a brief opens on its own headline (the day in full, the part of it in italic, one line
  of what the read covered); the rail no longer repeats it, and a warning box appears only when something went
  wrong. Tokyo Day's hues were darkened until small text reads at 4.5:1 on the panel (grey 3.6, link 3.1, red 3.0
  before); grey is slate so blue means a heading or a link. HYPE has its own colour (Tokyo's teal) and orange means
  a problem only. Lists of runs show day and minute, since three runs of one morning shared one title; a run that
  read nothing is on History, not under Earlier; a plain ending is not said on every row. Search marks the words it
  matched. Narrow (under 860 px) the rail keeps its controls and drops its lists, so the brief is not pushed a
  screen and a half down.
