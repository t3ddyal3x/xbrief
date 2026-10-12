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
