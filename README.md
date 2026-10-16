# xbrief

What the accounts you follow on X posted, twice a day or whenever you ask, so you never open X: **http://xbrief.localhost**

Your own Brave reads your Following tab on a Brave profile kept for this job, in a window parked behind your others. It scrolls
the way you would, and keeps the posts x.com itself loads. Claude reads each post whole and puts what matters first:
everything said about HYPE and Hyperliquid, then the stories most of your people talked about, then the rest a line
each, then every post that argues a claim (a thesis). An X Article is opened and read to its end, and leads the
theses, marked Article. A video of 10 minutes or more (on X, or a YouTube link) is transcribed whole (X's own
captions where it has them, else Whisper on the audio), and so is a podcast episode linked on Spotify or Apple
Podcasts (the show's own transcript where it has one); each is summarised on the post, marked Video or Podcast, and
opens in a pop-up with Copy; the whole transcript is a click away and search reaches it. Each story has a headline that says what happened, a sentence
or two, and the posts that carry it shown beside it as their authors wrote them. Every story folds out to all its
posts, threads in full, and anything that fits no story is listed at the end, never dropped.
Free: no X API, and the writing runs on your Claude subscription.

## The app
- **Brief** shows the newest brief as a front page: HYPE's stories and the four stories the most people talked
  about are open; every other story is one line (its headline and how many people) that opens in place. Under
  **Theses**, each claim opens to the argument step by step, what follows if it holds, and Claude's own view (weak
  spots, what would prove it wrong), labelled as Claude's, with the post beside it.
- **Brief now**, in the bar at the top, reads your Following tab right away: since the last brief, or the last 12,
  24 or 48 hours. The line beside it says what the run is doing, then offers the new brief.
- **History** lists every brief, and sets the **schedule**: two briefs a day, each starting at a random minute
  inside its window (morning 05:30–07:30, evening 17:00–20:00 to begin with). It starts off; tick it and save.
- **Sites** reads the websites on its list once a day (after 07:00; now Sigil Fund, Zee Prime, Capriole and Evanss6) and writes up
  each new post: the gist, its points, every position or call it makes, and Claude's own view, labelled. **Check
  now** reads them at once. A site's first check reads only its newest post. New sites go in `xbrief/config.py`
  (`SITES`): any site with an RSS feed or a sitemap. Beside the write-ups, on the right, are the posts on X by
  the people behind each site (Fiskantes for Sigil, Charles Edwards for Capriole, Evan_ss6 for Evanss6), from what the briefs already
  read, with a mark where each write-up falls. Pick a source above the write-ups to see only it; search (say "zro") to see
  the write-ups that mention it, with the article's own lines, and their posts that do.
- **Search** looks through every post a brief has held: words (each must appear), `@name` for an account, and dates.
  Each post links to the brief that had it. Posts are kept for good; the raw reads they came from, 30 days.

While a run is going, a second Brave icon sits in the Dock for a few minutes, and its window waits at the right
edge of your right-hand screen, behind your other windows, with a thin strip showing. It never comes to the front;
leave it be and it closes itself.

If X pushes back in any way (a rate limit, a logout, a notice that needs you), the run stops at once, retries
nothing, and the brief says so at the top. A brief that stopped early or missed posts always says so.

## Setting up (once)
1. `~/Developer/work/xbrief/bin/xbrief login`. A separate Brave window opens on X's login page. Log in to your main
   account, close anything X shows, click the Following tab once, then quit that Brave with cmd+Q.
2. `bin/xbrief probe` checks the job's Brave is logged in.
3. `bin/install-agent` starts the app (it stays on, like the other pages). Open http://xbrief.localhost, press
   **Brief now**, and check the brief against your Following tab.
4. On **History**, turn the schedule on.

## Day to day
`bin/doctor` says whether it is healthy. `bin/xbrief status` shows the last run.
From a terminal: `bin/xbrief run --now --hours 24` (it waits if a run is already going).
`bin/xbrief rebrief ~/Data/xbrief-data/raw/<file>.json.gz` writes a brief again from a saved read (kept 30 days).

If a brief says X logged you out or wants something: run `bin/xbrief login`, deal with it in that window, quit.
