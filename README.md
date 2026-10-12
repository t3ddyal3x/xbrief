# xbrief

What the accounts you follow on X posted, twice a day, so you never open X: **http://xbrief.localhost**

It reads your own Following tab with your login, the way x.com does in your browser, and Claude groups what it
finds by topic. Every item links to the original posts; threads are shown in full; anything that fits no topic is
listed at the end, never dropped. Free: no X API, and the writing runs on your Claude subscription.

## When it runs
Two runs a day, each starting at a random minute so no two days look alike: morning between 05:30 and 07:30,
evening between 17:00 and 20:00. The morning brief is ready by about 07:45.

If X pushes back in any way (a rate limit, a challenge, a logout), the run stops at once, retries nothing, and the
brief says so at the top. A brief that stopped early or missed posts always says so.

## Setting up (once)
1. Log in to X in Brave, profile **public**.
2. In your own terminal (not through Claude), run `~/Developer/work/xbrief/bin/xbrief login`. It asks for your
   handle and two cookie values from Brave (DevTools, Application, Cookies, https://x.com: `auth_token` and `ct0`).
   Nothing is shown as you paste.
3. `bin/xbrief probe` opens x.com/home once as you and prints the request a run would send. Compare it with
   Brave: on x.com/home open the Following tab, DevTools, Network, filter `HomeLatest`.
4. `bin/xbrief run --now --label am` for one hand run; check the brief against your Following tab.
5. `bin/install-agent` turns on the two daily runs.

## Day to day
`bin/doctor` says whether it is healthy. `bin/xbrief status` shows the last run and the login's state.
`bin/xbrief rebrief ~/Data/xbrief-data/raw/<file>.json` writes a brief again from a saved read (kept 30 days).

If X logs you out: log in again in Brave (public), then `bin/xbrief login` again.
