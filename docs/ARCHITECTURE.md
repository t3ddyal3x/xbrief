# xbrief — how it works, what was found, what was decided

The plan it was built from is `../../docs/plans/2026-10-12_x-follows-brief.md` (decisions 1–7, taken 2026-10-12).
This file records what building it found, and where the build differs from the plan.

## One run
1. launchd fires at the start of the window; `cli.jitter_seconds` waits a random part of it (never past the window
   end minus 15 minutes; a late wake runs at once).
2. `collect.run`: the job's environment is set (`config.TWS_ENV`, proxies stripped). The fork loads **x.com/home**
   once with the account's cookies to compute X's anti-bot header, and keeps the HTML.
3. `site.resolve` reads from that HTML which web app the account is served and which script it names. When the
   script is new (a deploy), the Following-tab request is read again from X's own script files (cached by their
   content-hashed names) and saved to `site.json`.
4. Pages are read on one connection (`API.raw_session`), with reading-like pauses (`collect.reading_pause`: a few
   seconds, now and then a minute or more, redrawn rather than clamped so no value repeats), until a page reaches the
   newest post of the previous run (by post id, the newest in each entry, promoted posts ignored), the feed ends, or
   the cap of `config.MAX_PAGES` pages. Ending or capping before the boundary is a **gap**, said at the top.
5. The pages are saved raw (`raw/`, 30 days); `brief.write` asks Claude; `page.render` writes the page and
   `index.html`; old raw files are pruned.

## What x.com sends (read from its own code, 2026-10-12)
x.com is mid-move between two web apps:

| | old app ("legacy") | new app ("xweb") |
|---|---|---|
| page names | `abs.twimg.com/responsive-web/client-web/main.<hash>.js` | `abs.twimg.com/x-web/x-web/entry-client-<hash>.js` |
| Following tab | `POST x.com/i/api/graphql/<id>/HomeLatestTimeline`, body `{variables, features, queryId}` | `GET api.x.com/graphql/<id>/HomeLatestTimelineQuery?variables=…`; a page that reports already-seen posts is a `POST {queryId, variables}` |
| variables | `count, cursor, includePromotedContent, latestControlAvailable, requestContext, seenTweetIds` (from published captures: **check on the first run**) | Relay's: `count, cursor, enableRanking(false), requestContext("launch" first), seenTweetIds`, then two provided flags (logged in: true; Grok note translation: false), every one present, null where unset |
| post layout | `legacy.full_text`, `entryId` … | `details.full_text`, `details.created_at_ms`, `url_entities`, `media_entities2`, `quoted_tweet_results`, `reply_to_results`, `entry_id` … |

The logged-out site was the new app on 2026-10-12, and every request id twscrape v0.20.1 pins differs from the new
app's (twscrape's are the old app's). Which app a logged-in account gets is not visible from outside; `bin/xbrief
probe` prints it and the request a run would send.

The new app also pre-renders the first page on the server and sends a CORS preflight before each cross-origin call;
the job does neither. Known differences, left as they are.

## The fork (`t3ddyal3x/twscrape`, branch `xbrief`, one commit on v0.20.1)
Found while reviewing the pinned release for "looking like a person":
- it loaded **x.com/tesla** with the account's cookies every run to compute the anti-bot id (now `TWS_XCLID_PAGE`,
  set to x.com/home);
- its API requests carried **page-load headers** (`accept: text/html…`, `sec-fetch-mode: navigate`,
  `upgrade-insecure-requests`) instead of a page's fetch() headers (now `TWS_XHR_HEADERS=1`: Chrome's order, the
  chrome150 identity, `x-twitter-auth-type: OAuth2Session`; refuses to start under another curl_cffi Chrome);
- it retried on its own in four places (now `TWS_CURL_RETRIES=0`, `TWS_FAIL_LIMIT=1`, `TWS_XCLID_TRIES=2`; a rate
  limit with `TWS_RAISE_WHEN_NO_ACCOUNT=1` raises instead of waiting).
Default behaviour is unchanged for anyone else. 207 tests pass (197 upstream, 10 the fork's).

## The writer
`claude -p --tools "" --strict-mcp-config --mcp-config '{"mcpServers":{}}' --disallowedTools "mcp__*"`, run in the
data dir. Checked 2026-10-12: asked to list its tools, it answered NONE. `--bare` is not usable (it ignores the
subscription login). On made-up posts including an injection attempt, it summarised the attempt rather than obeying it,
and placed every post. A writer failure still publishes every post, unsummarised, with the reason.

## Decisions
- **The account's own build decides the request** (not a hard-coded id): x.com/home is loaded each run anyway for the
  anti-bot id, so reading which app it is costs nothing, and a deploy is followed the way the browser follows it.
- **seenTweetIds**: a later page reports the previous page's posts except the last three (still below the fold),
  as the new app does when a reader scrolls.
- **The page** follows the other local pages (Tokyo Night / Day), reads in Iowan Old Style, puts handles and times in
  a mono byline built from the data, and opens threads by default.
