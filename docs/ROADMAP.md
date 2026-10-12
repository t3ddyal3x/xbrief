# xbrief — roadmap

1. **First hand run** (needs the operator's login): `bin/xbrief login`, `bin/xbrief probe` checked against Brave's
   network tab (address, GET or POST, variables), one `bin/xbrief run --now`, the brief checked against the
   Following tab with replies. Then set `config.MAX_PAGES` from that run's page count.
2. `bin/install-agent` for the two daily runs.
3. If the Following tab hides replies the operator wants: a private List on the same account instead (plan decision 4).
4. If twscrape stays broken after an X change: headless Brave with the login, reading the Following tab's own
   responses (the plan's fallback).
