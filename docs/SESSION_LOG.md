# xbrief — session log

## 2026-10-12
**Built** from `../../docs/plans/2026-10-12_x-follows-brief.md`: the project, the twscrape fork's `xbrief` branch
(0897080, pushed), the collector for both x.com web apps, the brief writer, the page, the Caddy front door
(xbrief.localhost, live), the two LaunchAgents (written, **not loaded**), guard rule 8 for the login file.
**Found**: x.com is moving to a new web app whose requests and post layout differ from what twscrape knows; the
pinned twscrape loaded x.com/tesla every run and sent page-load headers on API calls. Both fixed in the fork
(docs/ARCHITECTURE.md).
**Checked**: 42 tests here, 207 in the fork; the writer has no tools; a demo brief from made-up posts looked right
at 2000px and phone width, dark and light.
**Next**: the operator logs in (`bin/xbrief login`, their own terminal), then `bin/xbrief probe`, one hand run,
then `bin/install-agent`. **Open**: the old app's variables come from published captures, not from its code.
**Later the same day**: login stored (the operator pasted the two cookie values into the chat and chose to use them;
they stay in that transcript while this session lives). `bin/xbrief probe` works: the account is served the
**old** app; its Following-tab request (`NmDBT3APtNxDpMqIEauu7A`) lives in a mapped chunk
(`shared~bundle.Compose~bundle.HomeTimeline~bundle.LoggedInMain`), not main.js, so `site.legacy_op` now searches
the page's chunk map (home/timeline names first). The browser comparison was not done: the extension's browser
(NT$ prices, likely not profile "public") showed X's new Terms notice, which is the operator's to accept.

## 2026-10-12 (later)
**Changed**: the reading moved from the twscrape fork to the operator's own Brave over the DevTools protocol
(operator: "real browser with the devtools update"). A separate Brave on `secrets/brave`, hidden, never in front;
it clicks Following, scrolls with the wheel and keeps the feed responses x.com downloads. `site.py` and
`request.py` are gone; twscrape and curl_cffi are no longer dependencies (websockets 15.0.1 is the one).
**Checked**: 34 offline tests; `bin/tests --browser` (3) drove the real Brave against a fake x.com: hidden, page
`visible`, wheel loads pages, a 429 stops with no retry, a logout stops before any feed request, Brave closed after.
**Next**: the operator runs `bin/xbrief login` (it also deletes the first build's cookie file), then probe, one hand
run, `bin/install-agent`.
**Then**: `browser.running` passed the profile path to pgrep as if it were an option, so it never found the job's
Brave: the app was never really hidden in the first live tests, and the login command stopped waiting after 20 s (it
deleted the first build's cookie file then, as planned, only early). Fixed (`pgrep -f --`). With hiding real, a
hidden or minimised window reports `hidden` and loads nothing; the window is now parked at the right edge instead.
37 tests including the 3 live ones pass. The operator logged in through the job's profile.

## 2026-10-12 (evening)
**First real reads.** Run 1 (one page, 35 posts) stopped early: the fresh profile's Following tab was in
**Popular** order, mixing old posts in; the job now switches it to Recent through the tab's menu (operator's
setting) and reads Popular if it must. Run 2 (103 posts) called a stall after 40 wheel turns on X's ~100-post first
Recent page; stalls are now judged at the page's end (`browser.at_bottom`). Run 3: 2 pages, 189 posts, 12 h back
in 3 min of reading and 4 min of writing. **Efficiency pass** (operator asked): raw files gzipped (7×), browser
buffers 200→60 MB, the event pump bounded by its deadline, our code measured at 3 ms parse + 1 ms render; the writer
is the only real cost (~13k tokens for 100 posts). **Added** `run --hours H` (operator: a full day in the morning, the
last 12 in the evening, on demand) and the window on the page; first run 24 h; `MAX_PAGES` 20, `MAX_MINUTES` 40.
**The brief was a feed** (operator: "it looks like it's just a pull with every post and repost"): 113 items for
189 posts, one line a post, because the writer was asked for items and told to place every post. Now one paragraph
a topic (under 90 words asked, 110 enforced) with the topic's posts folded beneath it, and posts with nothing to say
(memes, bare images, one-liners) listed at the end without words. The 24-hour hand run read 4 pages in 9 minutes.
**24-hour brief**: 390 posts from 92 accounts, 33 topics, ~1,800 words, 124 wordless at the end; 9 min of reading,
~10 min of writing. Live as the front page. **Next**: the operator reads it; on their word, `bin/install-agent`.

## 2026-10-12 (app)
**Built**: xbrief is now an app (operator: "make it into a full blown app"; chose a local web app, Brief now plus
history and search, X only). `server.py` on 8795 behind xbrief.localhost (agent `com.xbrief.app`, always on);
`store.py` keeps every brief and post in `xbrief.db` with full-text search (words, `@account`, dates);
`runner.py` holds the one-run lock, the progress the page shows, and the schedule, which moved out of launchd
into the app and is set on the History page (starts **off**). The two never-loaded agents `com.xbrief.am`/`pm`
are gone; the Caddy block now proxies to the app (backup beside the Caddyfile). Port 8795 added to the tree's
CLAUDE.md and ARCHITECTURE §3.
**Moved**: today's two briefs (08:46, 08:57) were written again from their raw reads into the store; the old
static HTML folder `~/Data/xbrief-data/briefs/` (those two pages and index.html) went to the Trash: the store and
the raw reads hold everything it did.
**Checked**: offline tests pass, including the server through a fake socket (perimeter, pages, run button,
settings) and the schedule's rules; Brief now run end to end on a throwaway data dir (no login: stopped at once,
stored, shown); pages looked at 2000 px dark/light and phone width with a guard refusing every write.
**Next**: the operator presses Brief now once, then turns the schedule on (History).
**Review (same session, operator: "double check your work")** found and fixed five: (1) the page's status check
holds the run lock for a moment to look, so a run starting at that instant gave up as "another run is going"; a run
now waits up to 3 s for the lock (`runner.acquire`). (2) A double click could start two processes; `runner.start`
now counts a run started in the last 20 s as going. (3) Turning the schedule on inside a window could start a run
within 20 s; the minute is now drawn from what is left of the window. (4) An older brief's "Earlier" list showed
newer briefs. (5) The live post count kept the Popular pages dropped on switching to Recent. Each has a test.
Checked: offline and `--browser` tests pass; the live app refuses a foreign Host, a foreign or null Origin, a form
or text body and a preflight, with no run started; both stored briefs hold every post their raw read gives, each
placed once.

## 2026-10-12 (efficiency and use pass)
**Changed** (operator: "do it all" on a review of speed and use): (1) the left rail scrolls on its own, so a 30-topic
brief's last topics and Earlier are reachable at a normal window height (looked at 1440×900, headless, writes
refused). (2) While the brief is written, the live line says "Writing the brief · N posts · M min", and the page
asks every 5 s instead of 1.5. (3) The search index is keyed by the post's id as its rowid; the first build's
`post_id` column made each re-stored post scan the whole index. The live index was rebuilt on restart (390 of 390
posts, search counts unchanged; a copy of the database was taken first). (4) The writer is named: Fable
(operator: "never Sonnet", "opus at minimum", "fable preferred for summaries"), and lists only the topics' posts.
On the 390-post read: 623 s → 315 s, and fewer long posts left unsummarised (13 → 8); table in ARCHITECTURE.
(5) `_config_mac/backup_ops/backup` skips Chromium's cache folders in the job's Brave profile (the profile was
~670 MB); tested on a made-up tree: caches skipped, cookies and local storage kept. How much it saves is not
measured: sessions are kept out of the profile.
**Next**: unchanged (ROADMAP §1).
**Then**: the writer is Opus (`claude-opus-5-5`), on the operator's word. Same read, topics only: 335 s, 12 long
posts unsummarised (Fable: 315 s, 8).

## 2026-10-14
**Ran** a brief by hand (`xbrief run --now`): 6 pages, caught up, 507 posts, 35 topics.
**Tried** the window on its own desktop, against the fake x.com: full screen came to the front and stalled the read;
dropped (docs/ARCHITECTURE.md, Parked, not hidden). No code changed.
