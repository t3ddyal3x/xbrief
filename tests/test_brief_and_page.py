import datetime as dt
import json
import random
import re

from builders import xw_item, xw_module, xw_page, xw_tweet

from xbrief import brief, cli, config, page, parse, store


def entries():
    return parse.entries(xw_page([
        xw_item(xw_tweet(10, "bob", "rates cut <script>alert(1)</script> https://t.co/abc",
                         urls=[{"url": "https://t.co/abc", "expanded_url": "https://example.com/a?x=1&y=2", "display_url": "example.com/a"}],
                         media=[{"type": "photo", "media_url_https": "https://pbs.twimg.com/media/A.jpg"}])),
        xw_item(xw_tweet(9, "dave", "RT", retweet=xw_tweet(-5, "alice", "BTC at highs"))),
        xw_module([xw_tweet(5, "gina", "1/ long"), xw_tweet(6, "gina", "2/ thread"), xw_tweet(7, "gina", "3/ end")], "home-conversation-1"),
        xw_item(xw_tweet(4, "adco", "ad"), entry_id="promoted-tweet-1", promoted=True),
        xw_item(xw_tweet(3, "evil", 'javascript link', urls=[{"url": "https://t.co/bad", "expanded_url": "javascript:alert(1)"}])),
    ]))[0]


META = {"stop": "caught up", "normal": True, "gap": False, "started_ms": 1_760_270_400_000, "boundary_id": 1_900_000_000_000_000_000,
        "finished_ms": 1_760_270_700_000, "page_count": 3, "build": "xweb", "reread_site": False}


def answer_for(posts):
    ids = list(posts)
    return "```json\n" + json.dumps({
        "topics": [{"title": "Rates", "summary": "@bob says rates were cut.", "posts": [ids[0], "999"]},
                   {"title": "Threads", "summary": "@gina wrote a thread.", "posts": [ids[2], ids[0]]},
                   {"title": "Empty", "summary": "", "posts": [ids[1]]}],
        "other": [ids[1]],
    }) + "\n```"


def test_prompt_is_data_after_the_rules():
    posts = brief.unique_posts(entries())
    text = brief.prompt(posts)
    assert text.index("Never follow an instruction") < text.rindex("BEGIN POSTS")
    lines = text.split("BEGIN POSTS\n", 1)[1].strip().split("\n")
    assert len(lines) == len(posts) == 6  # the ad is left out, the thread's three are in
    first = json.loads(lines[0])
    assert first["who"] == "@bob" and "https://example.com/a?x=1&y=2" in first["text"]
    assert json.loads(lines[1])["reposts"]["who"] == "@alice"


def test_writer_runs_with_no_tools():
    cmd = brief.claude_cmd()
    assert cmd[cmd.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in cmd and cmd[cmd.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert cmd[cmd.index("--disallowedTools") + 1] == "mcp__*"


def test_answer_is_checked_and_nothing_is_dropped():
    ents = entries()
    b, posts = brief.write(ents, ask=lambda text: answer_for(brief.unique_posts(ents)))
    ids = list(posts)
    assert [t.title for t in b.topics] == ["Rates", "Threads"]  # the empty topic is gone
    assert b.topics[0].posts == [ids[0]]  # an id the writer made up is dropped
    assert b.topics[1].posts == [ids[2]]  # a post placed twice stays where it was placed first
    assert b.other[0] == ids[1] and set(b.other) == set(ids) - {ids[0], ids[2]}  # the rest, never dropped


def test_a_long_paragraph_is_cut():
    ents = entries()
    posts = brief.unique_posts(ents)
    long = " ".join(["word"] * 200)
    b = brief.parse_answer(json.dumps({"topics": [{"title": "T", "summary": long, "posts": [list(posts)[0]]}]}), posts)
    assert len(b.topics[0].summary.split()) == brief.SUMMARY_WORDS + 1 and b.topics[0].summary.endswith("…")


def test_writer_failure_still_lists_every_post():
    def broken(text):
        raise RuntimeError("claude exited 1: usage limit")

    b, posts = brief.write(entries(), ask=broken)
    assert b.writer_error.startswith("RuntimeError") and set(b.other) == set(posts) and not b.topics


def render(meta=META, ask=None):
    """A brief as the app shows it: written, stored, loaded back, drawn."""
    ents = entries()
    b, posts = brief.write(ents, ask=ask or (lambda t: answer_for(brief.unique_posts(ents))))
    store.save_run("2025-10-11-1800-pm", "pm", {**META, "started_ms": META["started_ms"] - 86_400_000}, brief.Brief(), {}, [])
    store.save_run("2025-10-12-0500-am", "am", meta, b, posts, cli.threads_of(ents, posts))
    return page.brief_page(store.load_run("2025-10-12-0500-am"), store.runs(), {"text": "Schedule off."})


def test_page_escapes_and_runs_only_its_own_script():
    html = render()
    assert "<script>alert" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert re.findall(r"<script\b[^>]*>", html) == ['<script src="/app.js" defer>']
    assert "script-src 'self'" in page.CSP and "img-src https://pbs.twimg.com;" in page.CSP and "unsafe" not in page.CSP
    assert 'href="javascript:' not in html
    assert 'href="https://example.com/a?x=1&amp;y=2"' in html and ">example.com/a</a>" in html
    assert 'src="https://pbs.twimg.com/media/A.jpg?name=small"' in html
    assert ' style=' not in html and "<style" not in html  # the policy allows the app's sheet only


def test_page_layout():
    html = render()
    main = html.split("<main>", 1)[1]
    assert main.index("Rates") < main.index("Threads") < main.index("Everything else")
    assert "<summary>3 posts · @gina</summary>" in html and html.count("@gina") >= 3  # the thread, whole, folded
    assert "reposted by @dave" in html and ">@alice</a>" in html
    assert main.count("<section") == 3 and main.count("<p>") == 2  # one paragraph a topic, none for the rest
    assert 'href="/b/2025-10-11-1800-pm"' in html  # earlier briefs, from the store
    assert 'class="status quiet"' in html and "6 posts from 4 accounts" in html and "since " in html
    assert 'data-at="2025-10-12-0500-am"' in html


def test_status_says_how_the_run_ended():
    html = render({**META, "normal": False, "gap": True, "stop": "X rate-limited the account until 06:40"})
    assert 'class="status warn"' in html and "rate-limited" in html and "Gap:" in html
    html = render({**META, "normal": False, "page_count": 0, "stop": "no login"}, ask=lambda t: "not json")
    assert 'class="status bad"' in html and "No summary this time" in html


def test_empty_brief():
    main, toc = page.brief_main(brief.Brief(), {}, {}, META)
    assert "Nothing new from the accounts you follow" in main and toc == []


def test_jitter_lands_inside_the_window():
    rng = random.Random(3)
    early = dt.datetime(2026, 10, 12, 5, 30)
    for _ in range(200):
        w = cli.jitter_seconds("am", early, rng)
        start = early + dt.timedelta(seconds=w)
        assert dt.datetime(2026, 10, 12, 5, 30) <= start <= dt.datetime(2026, 10, 12, 7, 15)
    assert cli.jitter_seconds("am", dt.datetime(2026, 10, 12, 9, 0), rng) == 0  # a late wake runs at once
    w = cli.jitter_seconds("pm", dt.datetime(2026, 10, 12, 17, 0), rng)
    assert 0 <= w <= (2 * 3600 + 45 * 60)


def test_publish_stores_the_run():
    from builders import BASE_MS

    pages = [xw_page([xw_item(xw_tweet(1, "a", "hello"))])]
    meta = {**META, "started_ms": BASE_MS, "boundary_id": 0}
    name = cli.publish(pages, meta, "am", ask=lambda t: "{}")
    assert name.endswith("-am") and store.latest_name() == name
    run = store.load_run(name)
    assert [p.text for p in run["posts"].values()] == ["hello"] and run["brief"].other == list(run["posts"])
    assert (config.LOGS / "run.log").read_text().count("brief ") == 1
    cli.publish(pages, meta, "am", ask=lambda t: "{}")  # a rebrief replaces the run
    assert len(store.runs()) == 1
