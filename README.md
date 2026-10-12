# xbrief

What the accounts you follow on X posted, twice a day, so you never open X: **http://xbrief.localhost**

Your own Brave reads your Following tab on a Brave profile kept for this job, in a window parked behind your others. It scrolls
the way you would, and keeps the posts x.com itself loads. Claude then groups them by topic. Every item links to the
original posts, threads are shown in full, and anything that fits no topic is listed at the end, never dropped.
Free: no X API, and the writing runs on your Claude subscription.

## When it runs
Two runs a day, each starting at a random minute so no two days look alike: morning between 05:30 and 07:30,
evening between 17:00 and 20:00. The morning brief is ready by about 07:45. While a run is going, a second Brave
icon sits in the Dock for a few minutes, and its window waits at the right edge of your right-hand screen,
behind your other windows, with a thin strip showing. It never comes to the front; leave it be and it closes itself.

If X pushes back in any way (a rate limit, a logout, a notice that needs you), the run stops at once, retries
nothing, and the brief says so at the top. A brief that stopped early or missed posts always says so.

## Setting up (once)
1. `~/Developer/work/xbrief/bin/xbrief login`. A separate Brave window opens on X's login page. Log in to your main
   account, close anything X shows, click the Following tab once, then quit that Brave with cmd+Q.
2. `bin/xbrief probe` checks the job's Brave is logged in.
3. `bin/xbrief run --now --label am` for one hand run; check the brief against your Following tab.
4. `bin/install-agent` turns on the two daily runs.

## Day to day
`bin/doctor` says whether it is healthy. `bin/xbrief status` shows the last run.
A brief whenever you want one: `bin/xbrief run --now --hours 24` reads the last 24 hours (or `--hours 12`, any
number), and the brief says what window it covers. The next scheduled run carries on from where it stopped.
`bin/xbrief rebrief ~/Data/xbrief-data/raw/<file>.json.gz` writes a brief again from a saved read (kept 30 days).

If a brief says X logged you out or wants something: run `bin/xbrief login`, deal with it in that window, quit.
