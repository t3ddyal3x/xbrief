# xbrief — how it works, what was found, what was decided

The plan it was built from is `../../docs/plans/2026-10-12_x-follows-brief.md`. Its decision 2 (twscrape) was
replaced the same day by the plan's own fallback, a real browser (operator, 2026-10-12: "real browser with the
devtools update"). This file records what the build found and where it differs from the plan.

## The app (2026-10-12)
The static page became an app on the operator's word ("make it into a full blown app"; chosen: a local web app like
macro, with a run button and history and search; X only). `server.py` on 127.0.0.1:8795 behind Caddy, the
standard library only, macro's loopback perimeter. Pages are built on the server (`page.py`); one script,
`static/app.js`, drives the Brief now button, the top bar's live line (`/api/status`, every 1.5 s while a run goes,
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

**X Articles** (found 2026-10-15): an Article post's text is only its t.co link; the feed carries the Article's
`title` and `preview_text` (its opening ~280 characters) under `article.article_results.result`, never the body.
Until 2026-10-15 both were dropped, so the brief saw a bare link (goodalexander's "Is CoreWeave Going to Die").
`Post.article` keeps them; search reaches them, the page shows the title as the link with the opening under it. 26
kept posts were given theirs from the raw files that day. The new app's layout for an Article is unseen;
`parse._article` reads the old one's path.

**Articles are read whole** (operator, 2026-10-15: "they 100% need to be fully read"; rule 1 widened for it). After
the feed read ends on its own terms, the job opens each new Article post's own page (x.com/<handle>/status/<id>,
newest first, at most `config.MAX_ARTICLES`, 4–12 s each) and keeps the `TweetResultByRestId`,
`TweetResultsByRestIds` and `TweetDetail` answers in the raw file (`articles`). The first carries the Article whole
as `article_results.result.content_state` (Draft.js: `blocks` and an `entityMap` list of MEDIA with captions, TWEET
by id, LINK); the second the posts it embeds. `parse.article_text` makes it plain text (headings, lists, image
captions, embedded posts' words, link addresses); the writer gets it as `article.text` and is told so; without it,
`article.opening`, and is told to say the argument is cut short. Articles lead the theses, marked "Article". The
probe that found the layout: goodalexander's CoreWeave Article, 133 blocks, 28,000 characters as text, 25 captioned
charts, 3 embedded posts. Charts themselves are not read, only their captions. `xbrief articles <raw>` reads a saved
run's Articles the same way, then rebriefs it.

**A quoted post's own quote** comes as `nested_quoted_tweet_results`, not `quoted_status_result` (found 2026-10-16:
213 in a month's reads, one of them an Article). Until then it was dropped: the writer never saw what a quoted post
quoted. `parse` reads it (a repost of a quote of a quote is the deepest); `parse.inner` lists a post and all inside
it, and the writer, search, Sites and the Article reader go through it. 165 stored posts were given theirs.
**A post wrapped for limited visibility** (`TweetWithVisibilityResults`) holds a post with no `__typename` (92 of
92 in five raw files); the Article reader unwraps it, or it would miss the Article and end the reading.

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

**Stories, not drawers** (2026-10-14, operator: "the entire thing needs a re-work; it's just not a good experience";
research and plan in `docs/plans/2026-10-14_rework.md`). That morning's brief ran to 3,450 words: twenty topics of
equal weight under headings that named a drawer ("AI products and companies"), each a paragraph retelling posts as
"@a said, @b said". Now `hype` and `stories` are lists of stories, each one piece of news or one conversation:
`headline` (what happened, a sentence with a verb), `gist` (one or two sentences, people by name, no handles),
`key` (one to three posts that carry it) and `posts`; theses are unchanged. Stored as `topics` (`Topic.title` is the
headline, `summary` the gist, `hype` marks HYPE's), so a brief from before still loads: its paragraph is the gist and
the posts its `[[post id]]` marks pointed at are its key posts. The writer no longer orders stories: the page ranks
them by how many people posted in each (Nuzzel's measure), then by posts.

## Long videos (2026-10-16)
The operator: transcript summaries for X and YouTube videos, only those of 10 minutes or more, the fastest way, never
downloading a video to run Whisper on it. Measured first (`docs/plans/2026-10-16_videos.md`): X makes its own
captions for many videos, an "en (auto-generated)" WebVTT track listed in the stream index the feed names, fetched
in a fraction of a second, and as good as Whisper large-v3 (97.5% and 95.3% of words the same on a 20- and a
74-minute video; each got names the other missed). Half the long videos one morning had none. YouTube refused its
captions to scripts (HTTP 429) and its transcript panel did not open in Chrome; its audio came in seconds.
So (`videos.py`, after the read and the Articles, before the writer): X's captions where they exist; else Whisper
large-v3 (MLX, `python -m xbrief.whisper`, its own process) on the video's 64 kbps audio track, copied by ffmpeg,
never the picture; YouTube by Whisper on yt-dlp's audio. Whisper ran 12–16 times faster than real time here. Each
transcript is summarised alone by Opus (`config.SITE_MODEL`, the Sites prompt's shape: gist, points, calls, view),
and the writer gets that summary, not the transcript, so a morning of podcasts cannot overflow its prompt. Each
video's transcript and summary are kept in `videos/<key>.json` (a failure is not kept, so the next brief retries);
the post keeps them too, so search reaches the words, and `/video/<key>` shows the transcript. At most
`config.MAX_VIDEOS` a brief; what is past the cap or failed is said at the top of the brief.
Always English (operator, 2026-10-16, "everything in english always"): left to guess, Whisper heard Taiki Maeda's
91-minute English interview with a Malaysian guest as Malay and wrote nine-tenths of it in Malay; its summary
read fine, but the transcript and search did not. Whisper now runs with `language="en"`, and X's captions are
used only from an English track, else Whisper.
Podcasts (2026-10-16): The Stalwart's post of Jeff Yan on Odd Lots linked Spotify, which xbrief did not read, so the
brief had no summary of it. Spotify's audio is its own, but every show not exclusive to Spotify has a public feed:
Spotify's embed page gives the episode's title, show and length; Apple's podcast directory (a free, keyless search)
gives the show's feed; the feed's item of the same title gives the audio and, on many shows, the publisher's own
transcript (`podcast:transcript`; Odd Lots has one on 1,284 of 1,288 episodes). Measured on that episode: Bloomberg's
transcript and Whisper large-v3 agree on 97.4% of Bloomberg's words; Bloomberg's has "Odd Lots" where Whisper heard
"loblots", marks each speaker's turn, and leaves out the ads Whisper transcribed. So the show's own English transcript
first, else Whisper on the feed's audio, the rule X's captions follow. An Apple Podcasts link goes to Apple's lookup
for the same. A title the feed does not list is said, never guessed at. On the page a podcast is "Podcast", "listen".
The summary opens in a pop-up at reading width with Copy (operator, 2026-10-16: the line opening in place in a
400 px card was hard to read, and was not seen to open).

## The Sites tab (2026-10-14)
The operator asked for "a separate engine parsing useful information like sigil": funds' and researchers' own sites,
checked daily, not their X accounts (reading a profile page would break rule 1). `sites.py`:
- **A source** (`config.SITES`) names its list: an RSS feed (Zee Prime, WordPress: the feed carries each post whole
  in `content:encoded`, used in place of the page) or a sitemap with a path to match (Sigil, whose site has no feed;
  `/blog/`). Only addresses on the source's own host are followed.
- **A check** reads each list; a post not in `site_posts` is fetched, its text taken from `<article>`, else
  `<main>`, else `<body>`, with scripts, navigation, headers and footers dropped, and given whole (up to 80,000
  characters) to `claude -p` with no tools, model Opus (`config.SITE_MODEL`; Fable until 2026-10-15, when it began to need
  paid credits and the operator chose Opus). It returns gist, points, calls (positions and forecasts with their numbers) and view (Claude's,
  labelled on the page). A fetch or writer failure is kept on the post and shown; the post is not tried again.
- **The first check of a source** marks everything already listed as known (`baseline`) and reads the newest one,
  so adding a site never summarises its whole archive.
- **When**: the server's schedule loop starts `xbrief sites` as its own process once a day at its first look after
  07:00 (a day slept through runs on waking), unless the Sites page's switch is off; **Check now** starts one at
  once. Its own lock (`sites.lock`), so it runs beside an X read.
- Checked live 2026-10-14: Sigil's sitemap lists 53 posts, the newest the Q2 2026 letter (24,949 characters read);
  Zee Prime's feed lists 10, the newest "Argonauts Journey".
- **Capriole** (added 2026-10-14) is read from its Substack feed (caprioleio.substack.com), not capriole.com: the
  site has no feed, its sitemap mixes posts with fixed pages under no common path, and update #70 (2026-05-05) says
  the updates are moving to Substack. Both end at that post on 2026-10-14; the feed lists 8. A post's title is the
  feed's own before its page's: a Substack page's first heading is the publication's name ("Charles Edwards"). The
  writer is given the post's day: without it, it dated update #70 a month early from the text.
- **Evanss6** (added 2026-10-15, operator's ask) is read from its Substack feed (evanss6.substack.com/feed), which
  carries each post whole: 6 posts, the newest "Have Fun Staying Poor" (2026-09-09). Its people: Evan_ss6, the
  handle the posts link to, already followed (60 of their posts kept by 2026-10-15).
- **Fable needs usage credits** (2026-10-15 11:11, `claude -p` exited 1: "Fable 5.1 requires usage credits"):
  Evanss6's first write-up failed on it; the row was deleted so the next check reads it again. Every new post's
  write-up failed the same way, so the operator moved the summaries to Opus the same day.
- **The people behind a source** (operator, 2026-10-14: "tie the head figures with these people in terms of their
  twitter"; "I just want it tied together as one place"; "the article in the middle and the twitter stuff on the
  right like we have for the brief"): a source's `x` names their handles (Sigil: Fiskantes; Capriole: caprioleio; Evanss6: Evan_ss6;
  Zee Prime: none followed). The Sites page sets the write-ups in the middle and their people's posts in a right-hand
  column (sticky, its own scroll, at 1440 px and wider; under the write-ups below that), newest first, with a mark
  where each write-up falls among them, so what they said before and after a letter reads in order. The side panel
  narrows it to one source; the search box narrows both columns to the words (the example: "zro" finds Sigil's Q2
  letter, with the article's own lines that hold it, and Fiskantes's posts that say it). A write-up keeps its
  article's text for this; the three read before 2026-10-14 15:00 had theirs fetched again once. The posts come
  from the store, which the Following tab's reads fill: their profiles are never opened (rule 1), so the column
  starts 2026-10-12, when xbrief began, and a post scrolled past between reads is missing.
- **Only the relevant posts** (operator, 2026-10-14: "i don't want every x-post just the relevant ones"): the
  writer also returns each write-up's `topics` (tickers, names, projects, events, as a post would say them, never
  a common word alone). Unsearched, the column holds a person's posts only when their words, a repost's or a
  quote's name one of their source's topics, labelled with the ones matched. A short all-capitals ticker matches
  exactly (LIT is not "lit"), a name in any case, each as a whole word or phrase. The authors are not a topic of
  their own posts: a topic that holds or is held by the firm's name, a handle or a name they post under is
  dropped (Fable listed "Fiskantes" and "Capriole Investments"). A search is the operator's own and shows every
  post holding its words. The three existing write-ups were written again for their topics.

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
- **The page** is a front page in Tokyo Night / Day (re-worked 2026-10-14 on "the entire thing needs a re-work";
  plan `docs/plans/2026-10-14_rework.md`; earlier the same day `docs/REVIEW_2026-10-14.md` and
  `docs/plans/2026-10-14_elegance.md`). Operator: "tokyo night were the right colors just wanted it to be more
  coherent", then "please don't have hype have its own color". The colours keep macro's roles: text is a ladder of
  Tokyo's slates (headlines, reading, secondary, quietest), blue is focus and selection only, and yellow and red mark
  a problem only. No part of a brief has a colour of its own: HYPE leads by being first, nothing else.
  One bar at the top of every page (tabs, search, the hours and Brief now, the live line); no side rail. A brief opens
  on the day as a headline, how much was read, a link to the brief before, and a strip with a tick for every post
  across the window. Then HYPE's stories and theses; then the four stories the most people posted in (`page.LEAD`),
  open; then every other story as one line, its headline and how many people, opening in place (`<details>`, no
  script); then the theses, a line each, opening to the argument, what follows, Claude's view (labelled) and the post;
  then everything else, folded. An open story sets Claude's words on the left in Iowan Old Style and its key posts on
  the right as cards in the system sans, as written (name without emoji, @handle and time linking to X, its first
  picture, what it quotes): serif is what Claude wrote, sans what people posted. Below 1100 px the cards go under the
  words. The `› N posts` fold is kept (operator: "i like the sources folded that way"). The Theses tab, the rail's
  contents with their bars, and the margin notes of the elegance pass are gone; `/theses` shows the brief. Figures
  are lining (old-style ones made the 0 in @0x… read as an o). Small text reads at 4.5:1 or better in both themes.
  A warning box appears only when something went wrong. Runs are listed by day and minute. Search marks the words
  it matched. X sends post text with &, < and > as entities; the page reads them back before escaping once.