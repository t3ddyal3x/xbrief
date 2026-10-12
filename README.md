# xbrief

What the accounts you follow on X posted, twice a day or whenever you ask, so you never open X: **http://xbrief.localhost**

Your own Brave reads your Following tab on a Brave profile kept for this job, in a window parked behind your others. It scrolls
the way you would, and keeps the posts x.com itself loads. Claude then groups them by topic. Every item links to the
original posts, threads are shown in full, and anything that fits no topic is listed at the end, never dropped.
Free: no X API, and the writing runs on your Claude subscription.

## The app
- **Brief** shows the newest brief. **Brief now** reads your Following tab right away: since the last brief, or
  the last 12, 24 or 48 hours. The line under it says what the run is doing, then offers the new brief.
- **History** lists every brief, and sets the **schedule**: two briefs a day, each starting at a random minute
  inside its window (morning 05:30–07:30, evening 17:00–20:00 to begin with). It starts off; tick it and save.
- **Search** looks through every post ever read: words (each must appear), `@name` for an account, and dates.
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
