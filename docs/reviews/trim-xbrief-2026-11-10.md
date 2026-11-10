# Trim — xbrief, 2026-11-10

Scope: the whole app (`xbrief/`, `bin/`, `ops/`, tests). Run right after the cleanup pass of the same day, which
already merged a dozen duplicated helpers, so what is left is small. Nothing has been removed: this waits for
"do it". Checked for every item: `xbrief/`, `tests/`, `bin/`, `ops/`, `~/Library/LaunchAgents`, the work tree's
hooks and skills (`publish-gitlab/apps/xbrief/clean.py` edits some of these lines by exact text), other apps,
`docs/ROADMAP.md` and `docs/plans/`, and the 41 stored briefs.

## Safe to remove
1. **The first build's login-file cleanup** (`config.OLD_LOGIN`, its delete in `cli.cmd_login`, its check in
   `bin/doctor`, its line in `tests/conftest.py`). The twscrape cookie file of 2026-10-12; the doctor reports no
   fault, so it is gone. ~10 lines. `publish-gitlab`'s clean.py strips these lines: drop its matching entries too.
2. **The old run agents' check and removal** (`com.xbrief.am`/`.pm` in `bin/doctor` and `bin/install-agent`). The
   static-page build's agents; only `com.xbrief.app.plist` is in LaunchAgents. ~8 lines. Same clean.py note.
3. **The "X deployed a new site" note** (`page.run_dek`, `meta.get("reread_site")`). Nothing ever set it (the field
   went today) and none of the 41 stored briefs has it. 2 lines.
4. **Browser options never used**: `browser.launch`'s `extra` and `background` (its one caller passes neither, so
   the foreground branch never runs), `Browser.start(park=)`, `Browser.wheel(x, y)`. ~6 lines.
5. **`brief.SUMMARY_WORDS`**: unused since the 2026-10-14 rework. 1 line.
6. **`page.run_title`'s `name` argument**: never read; two callers pass it.

## Merge
1. **`docs/REVIEW_2026-10-14.md` → `docs/reviews/`**, where every project keeps its reviews.
2. **`collect.wanted`** rebuilds `brief.unique_posts`'s filter (no ads, newer than the last brief). Call it, so the
   Article reader and the writer can never disagree on which posts a brief holds. ~8 lines.
3. **"The post as shown" and its videos/Article** are worked out in `brief._shown/_videos/_article` and again in
   `page.py` (5 places). One `Post.shown` and `parse.videos_in/article_in`, used by both. ~15 lines.
4. **`store.latest_name`** is `runs(limit=1)`'s name; with today's index both are instant. ~5 lines.
5. **`running`** is passed to a dozen page functions beside the status dict that already holds it; `topbar` can
   read it from there, and one `page.not_found` replaces the two not-found pages the server builds by hand.
6. **`page.video_page`** builds a dummy post to reuse `vids`; a `vid_html(v, handle)` for one video removes it.

## Not sure (your call)
1. **The random wait of a hand-typed `xbrief run` without `--now`** (`cli.jitter_seconds`, ~14 lines). From the
   launchd days; the app always passes `--now`, but ARCHITECTURE documents it and a terminal run reaches it.
   Removing it makes a hand run start at once.
2. **`store._upgrade_fts`'s first-build path**: the live db no longer needs it, but restoring an old backup does.
   Keep.
3. **Database backups** in `~/Data/xbrief-data/`: `xbrief.db.bak-20261022-111845-focus` (28 MB) and today's
   `xbrief.db.bak-20261110-092002-onecopy` (92 MB). To the Trash once search has been used for a few days.

All of it: about 80 lines, under 2% of the app's ~4,000.
