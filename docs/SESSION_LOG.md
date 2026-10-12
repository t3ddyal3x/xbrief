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
