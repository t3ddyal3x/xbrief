# xbrief — session log

## 2026-11-02
The am/pm run windows follow the laptop's clock, so a new time zone needs no code change. Fixed the one comment in `config.py` that named a city.

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

## 2026-10-14 (later)
**Built** what matters first (ROADMAP §0, decided with the operator): the writer reads every post whole (was 2,000
characters); a HYPE part opens every brief; every thesis (any post arguing a claim, longest first, no cap) is written
up on a new Theses tab (claim, steps, if it holds, Claude's view labelled), with a line each on the Brief, a HYPE
thesis in the HYPE part instead; a small ↗ after a post that stands out, built from the post id. Old briefs still load.
**Ran** a 12-hour read by hand: the first try stopped 11 s in (the first feed request was cancelled in the browser,
`net::ERR_ABORTED`; no X error, no challenge), leaving an empty run `2026-10-14-0841-am`; `xbrief probe` then showed
logged in and the feed loading, and the second try read 3 pages: 278 posts, 12 theses, 19 topics, HYPE 9 posts, 5
links; writing took 6 min. @goodalexander's six-phase post is the first thesis, all seven steps.
**Next**: the operator reads the new brief. Open: a link of its own for a shared article or chart.

## 2026-10-14 (Sites tab)
**Built** a Sites tab (operator: "a separate engine parsing useful information like sigil", checked daily; chose
title, link and summary; Sigil and Zee Prime to start). `sites.py` reads each source's RSS feed or sitemap with a
plain public GET, direct, on the source's own host only; a new post's text goes whole to `claude -p` (Fable, no
tools) for gist, points, calls and Claude's view. A source's first check notes its archive and reads the newest
post. The app starts `xbrief sites` once a day after 07:00 (switch and Check now on the page), own lock.
`runner.take_lock`/`acquire`/`running` take a lock path; `brief.ask_claude` takes a model.
**Checked**: 79 offline tests pass, 3 browser ones skipped (9 new); the first real check ran from the app's daily tick at 11:16: Sigil's sitemap
53 posts, the Q2 2026 letter read (24,949 characters); Zee Prime's feed 10, "Argonauts Journey" read; both
summaries right. The page at 2000 px, light and dark, through a headless Brave with a write guard.
**Next**: the operator looks at /sites. Open: adding a site from the page instead of config.py.

## 2026-10-14 (design pass)
**Changed** how every page looks, not what it does (decided in ARCHITECTURE, Decisions, The page): a headline on
each brief and on Theses; warnings only when something went wrong; light-theme colours readable (small grey text
was 3.6:1, links 3.1:1, now 5:1 or better); HYPE in its own teal instead of the warning orange; Earlier and History
list runs by day and minute (three "Wed 14 Oct · morning" runs were indistinguishable), the 0-post failed run off
Earlier; History opens on the briefs, schedule below; Brief now quieter than the reading; X's byline order (name,
then @handle); search marks the matched words, never inside a link or an escape; narrow widths drop the rail's lists.
**Checked**: offline tests (2 new); every page at 2000 px light and dark, 800 px and phone, through a headless Brave
that refuses writes and form submits; a warning state drawn from made-up data.
**Next**: the operator looks.

## 2026-10-14 (redesign)
**Why**: the operator found the first pass still looked bad ("did you load our design review skill"). The skill had
been loaded but not followed: no review, and no question of whether the look itself was right. Done properly:
`docs/REVIEW_2026-10-14.md`.
**Changed**: Tokyo Day replaced by a paper/ink surface with Hyperliquid's mint for HYPE only; type by role (SF Pro
for headlines and controls, Iowan for reading, mono for numbers and times); a strip under the day's headline with
a tick per post across the read window, HYPE's in mint; HYPE as the lead band; rules replaced by space. Decision
recorded in ARCHITECTURE (Decisions, The page).
**Checked**: offline tests (1 new, for the strip); every page at 2000 px light and dark, an open topic, and phone,
through the write-refusing headless Brave.
**Next**: the operator looks.

## 2026-10-14 (Tokyo, coherent)
**Changed**: back to Tokyo Night / Day on the operator's word ("tokyo night were the right colors just wanted it
to be more coherent"), with macro's roles: headings, reading, secondary and quiet text on Tokyo's slate ladder
(no more blue text), teal for HYPE only, blue for focus and selection only, yellow and red for problems only. The
type by role, headline, read-window strip and HYPE band stay. Small text holds 4.5:1 in both themes (text in the
HYPE band one step up the ladder to keep it). Review and ARCHITECTURE updated.
**Checked**: offline tests; Brief, an open topic, Theses and History, dark and light, at 2000 px.
**Next**: the operator looks.

## 2026-10-14 (Capriole, and the people on X)
**Changed**: Capriole added to the Sites list, read from its Substack feed (its site has no feed and says updates
moved to Substack). A feed's own title now wins over the page's, and the writer is given the post's day; both
faults showed on Capriole's first read, which was redone. Each source names its people's X handles (Fiskantes for
Sigil, caprioleio for Capriole); the Sites page links them and shows their last week of posts from the store under
On X, below the write-ups. No new read of X.
**Checked**: offline tests (1 new); a live check (Capriole's "Institutions are Guzzling Bitcoin", 2026-05-05);
the page at 2000 px light and dark through the write-refusing headless Brave.
**Next**: the operator looks; Zee Prime's people, if any are followed.

## 2026-10-14 (Sites: one place per source and topic)
**Changed**: the Sites page is now the write-ups in the middle and their people's X posts on the right (as the
brief's margin), with a mark where each write-up falls in their timeline; Sources in the side panel narrow it to
one; a search box narrows both to words, and a write-up then shows the article's lines that hold them. Write-ups
keep their article's text (the three existing ones fetched again once). The 7-day On X block is gone.
**Checked**: offline tests (2 new); "zro" finds Sigil's line "Sigil is long ZRO into the event — our most
contrarian position"; no Fiskantes post in the store says ZRO yet (the store starts 2026-10-12). The page at
2000 px light and dark.
**Next**: the operator looks.

## 2026-10-14 (elegance)
**Researched** best-in-class reading and briefing pages (Tufte CSS, gwern.net, Particle, Semafor, Techmeme,
Axios, Readwise Reader, Linear, Butterick): `docs/plans/2026-10-14_elegance.md`. **Built** on the operator's "build
it": the posts behind a sentence in the right margin on a wide screen (folds kept, their word), headlines in Iowan,
balanced headings and paragraphs without a lone last word, a hairline and faint lift on Claude's view, and a bar per
story in the contents. HYPE lost its own colour (operator, mid-build); it leads by place only. **Dropped after
looking**: old-style figures (the 0 in @0xNairolf read as an o) and small-caps openings (most open on an @handle).
**Checked**: offline tests (1 new for the margin notes; the strip test no longer has a HYPE colour); 2000 px dark
and light, 1280 px (no margin, ↗ kept), phone, through the write-refusing headless Brave.
**Next**: the operator looks.

## 2026-10-14 (margin notes aligned)
**Fixed** the operator's "seems misaligned": each margin note's first line was within 1.5 px of its marker's baseline, but
its lines ran on 19.6 px against the text's 28.35 px and drifted. Now the byline sits on the marker line's baseline
(measured 0 px) and the note runs three lines to two of the text (18.9 px); the notes sit 42 px from the text (was
88). Scoped to the brief, so the Sites page keeps its own layout.

## 2026-10-14 (Sites: only the relevant X posts)
**Changed**: the people's column shows only posts that name what their source's write-ups are about (new `topics`
from the writer), each labelled with what it matched; a search still shows every post holding its words. The three
write-ups were written again by Fable to get topics.
**Checked**: offline tests; live, 2 of Charles Edwards's kept posts match (Bitcoin), none of Fiskantes's 2; the
page at 2000 px.
**Next**: the operator looks.

## 2026-10-14 (margin notes refined)
**Changed** on "please make it look better": the number in the text is a plain footnote mark (no grey box); each
margin note is one object, a hairline on its left with its number hung outside it, the name without its emoji,
then @handle and time; hovering the number lights the note's hairline. Baselines re-measured: 0 px on every note.

## 2026-10-14 (starting over: plan)
**Asked**: "the entire thing needs a re-work; it's just not a good experience; please do some reviews online and
start over". **Researched** Nuzzel, Techmeme, Bloomberg Five Things, the Economist's Espresso, Axios, Particle,
shapeof.ai's summary and citation patterns, Reeder and Readwise. **Measured** the 08:44 brief: 3,450 words, twenty
topics of equal weight, headings that name a drawer, not the news. **Plan**: `docs/plans/2026-10-14_rework.md`
(stories with a news headline and a two-sentence gist, ranked by how many people talked about them, five open and
the rest one line each, the key posts in their own words beside each story, one page with a top bar; the rail,
the Theses tab and the margin notes go). Nothing built.
**Next**: the operator's word on the plan.

## 2026-10-14 (starting over: built)
**Built** on "yup go build", steps 1–4 of `docs/plans/2026-10-14_rework.md`. The writer returns stories (headline,
gist, key posts, posts; HYPE as stories too) and is told to leave trivia out; the page ranks them by how many people
posted in each, opens HYPE and the top four with their key posts beside them as cards, lists the rest a line each
(those from one person in two columns), and the theses as lines that open in place. One top bar replaces the rail;
the Theses tab and the margin notes are gone (`/theses` shows the brief). Older briefs still show: paragraph as gist,
its pointed-at posts as key posts. Fixed on the way: X's `&gt;`-style entities showed escaped twice; dark-theme quiet
text lifted to 4.7:1 on a card.
**Rewrote** the 08:44 brief with the new writer (`xbrief rebrief`, Opus, about 9 minutes): 69 stories, 18 theses.
That was before the trivia line was added; the next brief is the first with it.
**Checked**: offline tests (new: ranking, key-post cards, old briefs, entities); 2000 px light and dark, 1000 px,
phone, through the write-refusing headless Brave.
**Next**: the operator looks. Faces (step 5) not built.

## 2026-10-15 (Evanss6 added to Sites)
**Added** Evanss6 (evanss6.substack.com, its feed; people: Evan_ss6, already followed) to `config.SITES`; the
well-formed-list test names it. App restarted.
**Found**: the first check's write-up failed — `claude -p` now says Fable 5.1 requires usage credits. The failed
row was deleted so the next check reads the newest post again. No other source has had a new post since.
**Next**: the operator buys credits or picks another summary model (never Sonnet); then Check now.

## 2026-10-15 (X Articles kept)
**Ran** a read at the operator's ask (11:15, 105 posts) for goodalexander's CRWV post: an X Article, shown as a
bare link because the parser dropped an Article's title and opening.
**Fixed**: `Post.article` keeps them (parse, writer line, search, page: title as the link, opening under it, the
Sites people-column match). 26 kept posts given theirs from the raw files (store backed up first, in the session's
scratchpad); the 11:15 brief rewritten, and the CRWV article is now its own thesis. The full article was read for the
operator in their own Chrome, by hand; the job still never opens it (rule 1).
**Next**: the Fable credits question from the entry above.

## 2026-10-15 (Sites summaries on Opus)
**Changed** `config.SITE_MODEL` to Opus at the operator's word ("just stick with opus"), since Fable needs paid
credits. Checked the sites: Evanss6's "Have Fun Staying Poor" written up.

## 2026-10-15 (Articles read whole)
**Built** at the operator's word ("they 100% need to be fully read"): after a clean feed read the job opens each new
Article post's own page and keeps what it fetches (`collect.read_articles`, at most `config.MAX_ARTICLES`); the
parser turns the Article's body into text (`parse.article_text`: headings, lists, image captions, embedded posts,
links); the writer reads it whole and is told when it only has the opening; Articles lead the theses, marked
"Article"; search reaches the whole text; the page's run line says "Reading Articles · n of m". Rule 1 and 3 widened
(CLAUDE.md). New `xbrief articles <raw>` reads a saved run's Articles, then rebriefs it.
**Probe** (one page, the job's Brave): goodalexander's CoreWeave Article arrives whole in `TweetResultByRestId`.
**Ran** `xbrief articles` on the 11:15 run: 2 read whole; the brief rewritten, both Articles at the top of the theses
with write-ups from the full text.
**Checked**: offline tests (new: article text, the job opening Articles, X pushing back on one, the cap, the writer
and thesis order); `bin/tests --browser`.
**Not done**: the 24 Articles in briefs before today keep their opening only; `xbrief articles <raw>` per raw file
reads them if wanted.

## 2026-10-16 (Articles: the double-check)
**Found and fixed**, at the operator's ask to double-check the Article work:
- A post wrapped for limited visibility hides its type; the Article reader would have missed its Article and ended
  the reading (`parse._tweet_results`).
- A quoted post's own quote (`nested_quoted_tweet_results`) was never read: 213 in a month's reads, one this
  morning an Article (Chamath's private-credit deep dive). Now read, given to the writer, searched; 165 stored
  posts updated from the raw files (store backed up first).
- Articles first and the "Article" mark looked one quote deep; now any depth (`parse.inner`).
- A feed page cut off by leaving the tab would have read as X pushing back; the finished feed is now ignored.
- A handle starting with "login"/"logout" would have read as X's login page (`collect.BLOCKED`).
- Articles past the cap are said at the top of the brief; `xbrief articles` cut short still rebriefs.
- An Article's title links to its post (checked to show it whole), not x.com/i/article/.
**Ran**: the operator's 06:54 run (the pre-fix code) read 405 posts, no new Article found; with the fixes,
`xbrief articles` read the nested one and the brief was rewritten; its theses re-sorted in place.
**Checked**: offline tests; `bin/tests --browser`.

## 2026-10-16 (long videos)
**Measured** (plan `docs/plans/2026-10-16_videos.md`): X makes its own captions for many videos, as good as Whisper
large-v3 (97.5% and 95.3% of words the same on two); YouTube refuses captions to scripts here.
**Built** on the operator's answers (10 minutes or more; X's captions, else Whisper on the audio track; YouTube by
Whisper): `videos.py` reads each long video of a brief's posts before the writer, summarises it alone (Opus), keeps
it in `videos/`; the writer gets the summary; the post shows it (Video · length, opens to gist, points, calls,
Claude's view, a link to the transcript at `/video/<key>`); videos lead the theses with Articles, marked Video;
search reaches the transcript. mlx-whisper 0.4.3 pinned into xbrief's venv (the weights are the shared HF cache).
**Ran** on this morning's brief: 7 long videos (3 by X's captions, 31–45 s each; 4 by Whisper, 78–855 s), none
failed. The writer left Shane Parrish's interview post unsummarised; the prompt now says a post with an Article or a
video summary is never left out.
**Checked**: offline tests (new `test_videos.py`).

## 2026-10-16 (videos always in English)
**Found** on checking the morning's brief: Whisper, left to guess the language, wrote nine-tenths of Taiki Maeda's
91-minute English interview with a Malaysian guest in Malay. Its summary read fine; the transcript and search did not.
**Built** on the operator's word ("everything in english always"): Whisper runs with `language="en"`; X's captions
are used only from an English track, else Whisper. Old transcript renamed aside in `videos/` (`.malay-2026-10-16.bak`).
**Ran**: rebrief of 2026-10-16_0654-am; the interview re-transcribed in 710 s, 18,543 words, no Malay left.
**Checked**: offline tests (new test: other-language captions go to Whisper, Whisper told English); the page and search.

## 2026-10-16 (podcasts; the summary in a pop-up)
**Found**: The Stalwart's post of Jeff Yan on Odd Lots linked Spotify, which xbrief did not read: no summary. The
operator could not see that the Video line opens, and found the summary hard to read in the 400 px card.
**Measured**: Odd Lots' public feed carries Bloomberg's own transcript (1,284 of 1,288 episodes); on the Jeff Yan
episode it and Whisper large-v3 agree on 97.4% of Bloomberg's words; Bloomberg's gets the names, marks speakers,
drops the ads.
**Built**: Spotify and Apple Podcasts episode links are read like long videos (`videos._podcast`): the show's feed
from Apple's directory, the episode by title, the show's own English transcript, else Whisper on the feed's audio;
shown as Podcast, listen. The Video/Podcast line has the page's open arrow and opens its summary in a pop-up at
reading width (`dialog.peek`), with Copy (plain text: line, gist, numbered points, calls, Claude's view, link).
**Ran**: rebrief of 2026-10-16_0654-am; Jeff Yan's episode from the show's transcript in 23 s, 10,597 words.
**Checked**: offline tests (new podcast tests); the pop-up and Copy in headless Brave (guarded), dark and light.

## 2026-10-17 (a fifth site)
**Built**: The Cookie Chumbles (chumbawamba22.substack.com, by "chumba", no X handle on the Substack) added to
`config.SITES` as an RSS source; the list test names it.
**Ran**: `bin/xbrief sites`: its first check learned its two posts and read the newest, "The Most Spectacularly
Wrong Thesis" (2026-04-29).
**Checked**: offline tests; restart; doctor clean.

## 2026-10-18 (one recording, read once)
**Found**: the 10-18 morning brief transcribed Pomp's Jordi Visser episode four times (X, YouTube, Spotify, Apple:
all 3,613 s) and Saylor's ParaFi talk twice (X, YouTube: 2,607 s), about 25 of its 90 minutes.
**Built**: every place a video was posted is identified first (title, show, length: one small request), grouped by
recording (`videos.same`: length within 1 s, and the same title where both have one, else the same poster), and
read once from its best place (the show's own transcript, then X's captions, then Whisper; the next if one fails);
the others keep a copy marked `same_as`. An X video (no title) joins only where exactly one recording matches. The
cap of 12 now counts recordings, not places. A post shows one recording once.
**Checked**: on the last 17 kept videos the grouping finds exactly those two (Pomp's four, Saylor's two), nothing
else; offline tests (new: read once from the best place, an ambiguous X video read alone, `same`).
Also: the operator's Brave would not open: another session's headless Brave (a hung `--dump-dom`) had run for 40 h
and the Brave icon switched to it. Stopped it.

## 2026-10-19 — the am brief stalled on a film; Whisper stopped by hand
The page's am run (07:24) spent 50 min in Whisper on its ninth video, YouTube C8wix2kLcCk, "Raw Iron: Making of
Pumping Iron" (2002, 4,460 s, mostly music and gym noise, posted by @TrungTPhan), against 890 s for a 22,774-word
podcast the same morning. The Whisper process held the GPU at ~95% (per-process `accumulatedGPUTime`), which is
what made the whole Mac lag. Stopped on the operator's word (`kill` of the `xbrief.whisper` child); the run logged the
video as failed, as `videos.py` is built to, and wrote the brief at 09:03: 441 posts, 25 theses, 56 topics. Nothing
in code changed. **Proposed, not built:** time Whisper out at a multiple of the audio's length instead of the flat
4 h, so noise cannot hold the GPU for hours.

## 2026-10-20 — one podcast read three times
The am run transcribed and summarised one B_Madden4 episode ("Members Leave Carriers, Not Brokers", Claims Denied)
from all three places it was posted: X 3,714 s, Spotify 3,718 s, Apple 3,808 s (Apple's copy carries more ads).
`videos.same` wanted lengths to the second, so no two matched; ~12 min of Whisper and two Opus calls wasted.
**Changed**: one show's episode of one title is one recording at any length; otherwise lengths may differ by
`SAME_S` = 5 s (was 1). Tests cover today's three copies, which now group as one. App restarted; the run going
finishes on the old code, the next run reads such a recording once.
**Changed, same day**: a brief's "Videos not read" box printed raw program errors. It now gives each video a line:
who posted it, its title linked to the video, the reason in plain words (`videos.why`), and "Read since" with a link
to the summary when a later run read it. `cli.publish` now keeps each failure's key, poster, kind, title, url and
error; briefs from before keep "key: error" and are shown the same way.

## 2026-10-20 — harden (whole app), on "the app is slow af"
**Measured**: the pages are not slow at the server or in a clean browser: the front page (716 KB, 14,500 nodes)
answers in 50 ms, paints in 0.13–0.25 s and scrolls at a steady 60 fps in headless Brave at 2000 px; search and Sites
the same. The run is: the am Brief now took 75 min (read 13, videos 52, writer 10). Whisper holding the GPU (10-19)
is the likely cause of the page feeling slow during a run; not measured.
**Changed** (branch `harden-2026-10-20`, f24e0c7): a recording's summary is written while the next is transcribed
(two at a time); a failed summary keeps its transcript for the next brief instead of re-transcribing from another
place; Whisper is stopped past a third of the audio's length (min 10 min, was a flat 4 h) and that recording kept as
not read, never retried. Tests: both new ones fail on the old code.
**Left**: `collect._done` advances `state.json` before the brief is written, so a crash in publish leaves those posts
to a rebrief of the raw file; not changed.

## 2026-10-20 (evening) — the brief before waking; a morning is one brief
**Measured**: Whisper at utility priority (what every run inherited until the app's agent went Interactive at 17:37)
took 90–100 s on a 10-minute clip, at normal priority 51–52 s, the same text. Runs since then transcribe at full speed.
**Built** on the operator's word ("running this before i wake up and then running it again"; decisions in
`docs/plans/2026-10-20_early-run.md`): a Brief now the same morning as the early run reads only what came after and
writes the morning's brief again over both reads, under the early run's name (`cli.catching_up`, `combine`,
`publish_raw`); nothing new leaves it and says so; the top bar says "Brief caught up.". Each schedule window has its
own switch. **Set**: schedule on, morning 05:00–05:45, evening off (operator: "just run it in the morning").
Branch `harden-2026-10-20` merged into main and deleted; app restarted.
**Checked**: offline tests (new: catch-up as one brief, nothing new, rebrief of a read, another day or window, a
window switched off). `bin/tests --browser`: the read passes; its never-in-front check failed because the operator was
switching apps during it (it fails the same on the code before today's change).
**Next**: look at the 10-21 brief: did the 05:00 run read with the display asleep, how long it took, then Brief now.

## 2026-10-22 — published on GitLab, anonymously; the focus is a setting
**Changed**: HYPE is now `config.FOCUS` (None: no focus part); stored briefs' `hype` keys renamed `focus` (backup
beside the db); `collect.raw_files` returns nothing before the first login instead of crashing the doctor.
**Published**: the GitLab copy, private, one commit under an anonymous name at 12:00 UTC from
source 5791a9d, made by `../docs/plans/2026-10-22_publish-xbrief-clean.py` (no focus, the sites kept as examples,
Application Support data folder, page on 127.0.0.1:8795, no Caddy, MIT). Its download page is
members-only until the operator says go.
**Checked**: tests here and in the export (fresh venv, FOCUS None); the scan with `2026-10-22_publish-xbrief-allow.txt`
(Claude only: the operator OK'd naming it) passes on the export and on the page's own zip, which matches the export
file for file; the writer's instructions differ from before only in the focus wording and key names.


## 2026-10-26 — Brief now opens the new brief
**Changed** (operator: "it doesn't automatically jump to the newest brief"): a page that saw a run going (its own
Brief now, or one it watched) opens the brief that run wrote when it ends, instead of offering "New brief · Open"
(`static/app.js`). A catch-up with nothing new opens the morning's brief, whose line says "Nothing new since …"; a
failed run stays put and says so; a page opened after a run ended only offers the link. App restarted.
**Checked**: a copy of the app on :8895 over a copy of the db, Brief now spawning a fake run (no Brave, no X), driven
by headless Brave: from an older brief, from History, reloaded mid-run, nothing new (from History and from the
brief), failed, opened afterwards — each as above, no reload loop.


## 2026-10-27 — The video count counts only videos still to read
**Changed** (operator: a catch-up showed "Transcribing videos · 8 of 9" while only two were new): the rail's count
leaves out recordings already read by the morning's first run, which a catch-up passes over in a moment
(`videos.read_all`). That catch-up now reads "1 of 2", "2 of 2". App restarted.
**Checked**: `test_the_count_shown_is_of_the_videos_still_to_read` (one kept, two new → 0 of 2, 1 of 2) fails on the
old code and passes on the new; full offline suite green.

## 2026-11-01
**Found** (operator: "issue with the Sunday brief"): the 07:30 catch-up's writer answered with JSON missing a comma
(`JSONDecodeError … char 3560`), and with no second ask the morning's brief was stored over as 324 posts unsorted,
0 theses, 0 topics, replacing the 05:02 run's 19 theses.
**Fixed**: `brief.write` asks the writer once more when its answer does not parse; a writer that fails outright
(exit, usage limit) is still not asked again. App restarted. Sunday's brief written again from both reads
(`xbrief rebrief …0730-am`): 324 posts, 20 theses, 42 topics.
**Checked**: `test_an_answer_that_does_not_parse_is_asked_for_once_more` (bad then good → brief; bad twice → two
asks, the error shown; outright failure → one ask); full offline suite green.
