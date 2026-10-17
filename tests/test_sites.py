"""The Sites tab: reading a source's list (RSS or sitemap), pulling a post's text out of its page, the first check
that only learns what is there, a new post read and summarised, failures kept on the post, the daily check, and the
page and routes. Offline: every fetch and every answer from Claude is a stand-in."""

import datetime as dt
import json

from test_app import call

from xbrief import config, page, sites, store

SIGIL = {"key": "sigil", "name": "Sigil Fund", "home": "https://www.sigilfund.com/insights",
         "list": "https://www.sigilfund.com/sitemap.xml", "kind": "sitemap", "match": "/blog/"}
ZEE = {"key": "zeeprime", "name": "Zee Prime", "home": "https://zeeprime.capital/writing/",
       "list": "https://zeeprime.capital/rss/", "kind": "rss"}

SITEMAP = """<?xml version="1.0"?><urlset>
<url><loc>https://www.sigilfund.com/</loc><lastmod>2026-08-01T00:00:00Z</lastmod></url>
<url><loc>https://www.sigilfund.com/blog</loc></url>
<url><loc>https://www.sigilfund.com/blog/q1-letter</loc><lastmod>2026-05-22T07:54:09Z</lastmod></url>
<url><loc>https://www.sigilfund.com/blog/q2-letter</loc><lastmod>2026-08-14T19:53:52Z</lastmod></url>
<url><loc>https://elsewhere.example/blog/not-theirs</loc></url>
</urlset>"""

BODY = "Sigil is long ZRO into the Zero launch. " * 20

ARTICLE = f"""<html><head><title>Sigil Fund</title><meta property="og:title" content="Outperformance &amp; HYPE">
<script>alert(1)</script></head><body><nav>Thesis Funds Insights</nav>
<h1>Sigil &mdash; Q2 2026 Letter</h1><time datetime="2026-08-14T12:00:00.000Z">Aug 14</time>
<article class="article"><h2>Sigil Core</h2><p>{BODY}</p><ul><li>HYPE</li><li>LIT</li></ul>
<style>.x{{}}</style></article><footer>© Sigil</footer></body></html>"""

RSS = """<?xml version="1.0"?><rss><channel><title>Zee Prime</title>
<item><title>Argonauts Journey</title><link>https://zeeprime.capital/argonauts-journey/</link>
<pubDate>Mon, 20 Jul 2026 08:40:13 +0000</pubDate>
<content:encoded><![CDATA[<p>Zee Prime is driven by curiosity. </p>""" + "".join(f"<p>More of the essay, part {i}.</p>" for i in range(30)) + """]]></content:encoded></item>
<item><title>Older &amp; wiser</title><link>https://zeeprime.capital/older/</link>
<pubDate>Thu, 30 Oct 2025 09:00:00 +0000</pubDate></item>
</channel></rss>"""

ANSWER = json.dumps({"gist": "Q2 was strong on HYPE and LIT.", "points": ["DeFi hacks hurt.", "ZEC added."],
                     "calls": ["Long ZRO into the Zero launch; most contrarian."], "view": "Thin on <b>sizing</b>.",
                     "topics": ["ZRO", "LayerZero", "Zero mainnet", "LIT", "$HYPE", "a b c d e f g h"]})


def getter(pages: dict):
    seen = []

    def get(url):
        seen.append(url)
        if url not in pages:
            raise OSError(f"no page {url}")
        return pages[url]
    get.seen = seen
    return get


def test_lists():
    items = sites.list_sitemap(SITEMAP, "/blog/")
    assert [i["url"] for i in items] == ["https://www.sigilfund.com/blog/q1-letter", "https://www.sigilfund.com/blog/q2-letter",
                                         "https://elsewhere.example/blog/not-theirs"]  # the blog index itself is not a post
    assert items[1]["published_ms"] == int(dt.datetime(2026, 8, 14, 19, 53, 52, tzinfo=dt.timezone.utc).timestamp() * 1000)
    rss = sites.list_rss(RSS)
    assert [i["title"] for i in rss] == ["Argonauts Journey", "Older & wiser"]
    assert rss[0]["html"].startswith("<p>Zee Prime") and rss[1]["html"] is None
    get = getter({SIGIL["list"]: SITEMAP})
    assert all("sigilfund.com" in i["url"] for i in sites.listed(SIGIL, get))  # another host is never followed


def test_a_page_read():
    page = sites.read_page(ARTICLE)
    assert page["title"] == "Sigil — Q2 2026 Letter"
    assert page["published_ms"] == int(dt.datetime(2026, 8, 14, 12, tzinfo=dt.timezone.utc).timestamp() * 1000)
    assert page["text"].startswith("## Sigil Core\nSigil is long ZRO") and "- HYPE\n- LIT" in page["text"]
    assert "alert" not in page["text"] and "Thesis Funds" not in page["text"] and "© Sigil" not in page["text"]


def test_answers_are_checked():
    s = sites.parse_summary("here: " + ANSWER)
    assert s["gist"].startswith("Q2") and s["calls"] == ["Long ZRO into the Zero launch; most contrarian."]
    assert s["topics"] == ["ZRO", "LayerZero", "Zero mainnet", "LIT", "$HYPE"]  # a topic too long to match is dropped
    long = sites.parse_summary(json.dumps({"gist": "w " * 500, "points": ["p"] * 50}))
    assert len(long["gist"].split()) == sites.LIMITS["gist"] + 1 and len(long["points"]) == sites.MAX_POINTS
    for bad in ("no json", "[1, 2]", '{"view": "only a view"}'):
        try:
            sites.parse_summary(bad)
            raise AssertionError(bad)
        except ValueError:
            pass


def test_first_check_learns_the_list_and_reads_the_newest():
    asked = []
    get = getter({SIGIL["list"]: SITEMAP, "https://www.sigilfund.com/blog/q2-letter": ARTICLE})
    state = sites.check([SIGIL], get=get, ask=lambda t: asked.append(t) or ANSWER, now_ms=1)
    assert state["sigil"] == {"checked_ms": 1, "listed": 2, "new": 1, "error": None}
    assert len(asked) == 1 and "BEGIN POST" in asked[0] and "Sigil is long ZRO" in asked[0]
    assert "https://www.sigilfund.com/blog/q1-letter" not in get.seen  # an old post is noted, never fetched
    posts = store.site_posts()
    assert [p["title"] for p in posts] == ["Sigil — Q2 2026 Letter"] and posts[0]["summary"]["view"] == "Thin on <b>sizing</b>."
    assert store.site_urls("sigil") == {"https://www.sigilfund.com/blog/q1-letter", "https://www.sigilfund.com/blog/q2-letter"}
    # the next check reads only what is new
    more = SITEMAP.replace("</urlset>", "<url><loc>https://www.sigilfund.com/blog/q3-letter</loc></url></urlset>")
    get = getter({SIGIL["list"]: more, "https://www.sigilfund.com/blog/q3-letter": ARTICLE.replace("Q2 2026", "Q3 2026")})
    asked.clear()
    assert sites.check([SIGIL], get=get, ask=lambda t: asked.append(t) or ANSWER, now_ms=2)["sigil"]["new"] == 1
    assert len(asked) == 1 and len(store.site_posts()) == 2
    assert sites.check([SIGIL], get=get, ask=lambda t: asked.append(t) or ANSWER, now_ms=3)["sigil"]["new"] == 0
    assert len(asked) == 1 and store.settings()["sites_checked_ms"] == 3


def test_the_feed_copy_is_read_when_there_is_one():
    asked = []
    get = getter({ZEE["list"]: RSS, "https://zeeprime.capital/argonauts-journey/": "<html><body><h1>Zee Prime Capital</h1></body></html>"})
    sites.check([ZEE], get=get, ask=lambda t: asked.append(t) or ANSWER, now_ms=1)
    assert "More of the essay, part 29." in asked[0]  # the feed's own copy, not the thin page
    assert '"published": "2026-07-20"' in asked[0]  # the post's date is given, not guessed from its text
    assert store.site_posts()[0]["title"] == "Argonauts Journey"


def test_failures_are_kept_and_one_source_does_not_stop_another():
    get = getter({SIGIL["list"]: SITEMAP, "https://www.sigilfund.com/blog/q2-letter": ARTICLE})
    state = sites.check([ZEE, SIGIL], get=get, ask=lambda t: "not json", now_ms=1)
    assert state["zeeprime"]["error"].startswith("OSError") and state["sigil"]["new"] == 1
    post = store.site_posts()[0]
    assert post["error"].startswith("ValueError") and "summary" not in post
    thin = getter({SIGIL["list"]: SITEMAP.replace("q2-letter", "q9"), "https://www.sigilfund.com/blog/q9": "<p>hi</p>",
                   "https://www.sigilfund.com/blog/q1-letter": ARTICLE})
    sites.check([SIGIL], get=thin, ask=lambda t: ANSWER, now_ms=2)
    assert any("almost no text" in (p.get("error") or "") for p in store.site_posts())


def test_once_a_day_after_seven():
    day = dt.datetime(2026, 10, 14)
    ms = lambda d: int(d.timestamp() * 1000)  # noqa: E731
    assert not sites.due(day.replace(hour=6, minute=59), {})
    assert sites.due(day.replace(hour=7), {})
    assert sites.due(day.replace(hour=23), {"sites_checked_ms": ms(day.replace(hour=6))})
    assert not sites.due(day.replace(hour=9), {"sites_checked_ms": ms(day.replace(hour=7, minute=5))})
    assert not sites.due(day.replace(hour=9), {"sites_started_ms": ms(day.replace(hour=8))})  # started, not ended yet
    assert not sites.due(day.replace(hour=9), {"sites_daily": False})
    started = []
    assert sites.tick(day.replace(hour=8), starter=lambda **kw: started.append(kw) or True) and started == [{"by": "schedule"}]


def test_the_sites_page(monkeypatch):
    code, _, html = call("GET", "/sites")
    assert code == 200 and "Nothing read yet" in html and "Sigil Fund" in html and 'href="/sites" aria-current' in html
    get = getter({SIGIL["list"]: SITEMAP, "https://www.sigilfund.com/blog/q2-letter": ARTICLE})
    sites.check([SIGIL], get=get, ask=lambda t: ANSWER, now_ms=1)
    code, _, html = call("GET", "/sites")
    assert 'href="https://www.sigilfund.com/blog/q2-letter"' in html and "Thin on &lt;b&gt;sizing&lt;/b&gt;" in html
    assert "Claude's view" in html and "Long ZRO into the Zero launch" in html
    store.save_site_post({"source": "sigil", "url": "javascript:alert(1)", "title": "x", "error": "E"}, 5)
    assert 'href="javascript' not in call("GET", "/sites")[2]  # only an http(s) address is a link
    started = []
    monkeypatch.setattr(sites, "start", lambda **kw: started.append(kw) or True)
    assert call("POST", "/api/sites", {"check": True})[0] == 202 and started == [{"by": "page"}]
    assert call("POST", "/api/sites", {"daily": False})[0] == 200 and store.settings()["sites_daily"] is False
    assert call("POST", "/api/sites", {"daily": "no"})[0] == 400
    assert call("POST", "/api/sites", {"check": True}, headers={"Origin": "https://evil.example"})[0] == 403
    monkeypatch.setattr(sites, "start", lambda **kw: False)
    assert call("POST", "/api/sites", {"check": True})[0] == 409
    assert json.loads(call("GET", "/api/sites")[2])["checking"] is False


def test_the_real_list_is_well_formed():
    assert {s["key"] for s in config.SITES} == {"sigil", "zeeprime", "capriole", "evanss6", "chumba"}
    for s in config.SITES:
        assert s["kind"] in ("rss", "sitemap") and s["list"].startswith("https://") and s["home"].startswith("https://")


def test_the_people_behind_a_source():
    from builders import xw_tweet
    from test_app import publish
    publish([xw_tweet(1, "Fiskantes", "Zero mainnet is close, long $ZRO"), xw_tweet(3, "Fiskantes", "gm, this party is lit"),
             xw_tweet(4, "Fiskantes", "RT", retweet=xw_tweet(-6, "carl", "LayerZero ships")),
             xw_tweet(5, "Fiskantes", "zero chance", quote=xw_tweet(-7, "dan", "HYPE ath")),
             xw_tweet(2, "bob", "RT", retweet=xw_tweet(-5, "Fiskantes", "a ZRO post of theirs"))])
    src = dict(SIGIL, x=["Fiskantes"])
    doc = {"source": "sigil", "url": "https://www.sigilfund.com/blog/q2-letter", "title": "Q2", "published_ms": 5,
           "summary": sites.parse_summary(ANSWER), "text": "## Core\nWe trimmed HYPE.\n" + "x " * 300 + "then ZRO. " + "y " * 300}
    got = sites.people_posts([src], docs=[doc])
    # only what the write-up is about: a ticker exactly (not "lit"), a name in any case, a repost's or a quote's words;
    # "zero chance" is not "Zero mainnet"; another account's repost of theirs is not theirs
    assert [((p.retweet_of or p).text, about) for p, about in got] == [
        ("zero chance", ["HYPE"]), ("LayerZero ships", ["LayerZero"]), ("Zero mainnet is close, long $ZRO", ["ZRO", "Zero mainnet"])]
    assert sites.people_posts([src], docs=[]) == []  # no write-up, nothing is relevant
    me = dict(doc, summary={**doc["summary"], "topics": ["Fiskantes", "Sigil Fund Ltd", "Sigil"]})
    assert sites.people_posts([src], docs=[me]) == []  # the authors are not a topic
    assert [p.text for p, _ in sites.people_posts([src], ["lit"])] == ["gm, this party is lit"]  # a search is the operator's own
    assert sites.people_posts([ZEE], docs=[doc]) == []
    # a write-up is found by the words in its article, and shows the lines that hold them
    assert sites.matches(doc, ["zro"]) and sites.matches(doc, ["hype", "trimmed"]) and not sites.matches(doc, ["sol"])
    assert not sites.matches(doc, ["ro"])  # a word that begins with it, not any part of one
    lines = sites.found_lines(doc["text"], ["zro"])
    assert len(lines) == 1 and "then ZRO." in lines[0] and lines[0].startswith("…") and len(lines[0]) < 370
    store.save_site_post(dict(doc), 1)
    html = page.sites_page(store.site_posts(), [src, ZEE], {}, {}, False, {"text": ""}, xposts=got, key="sigil")
    side = html[html.index('<aside class="side">'):]
    assert '<span class="about">ZRO, Zero mainnet</span>' in side and 'href="#s0"' in side and "party is lit" not in side
    html = page.sites_page(store.site_posts(), [src, ZEE], {}, {}, False, {"text": ""},
                           xposts=sites.people_posts([src], ["zro"]), key="sigil", q="zro", words=["zro"],
                           lines={doc["url"]: lines})
    assert "long $<mark>ZRO</mark>" in html and "In the article" in html and "then <mark>ZRO</mark>." in html
    assert 'href="/sites?s=sigil&amp;q=zro" aria-current=page' in html and 'href="/sites?q=zro"' in html
    assert 'value="zro"' in html and 'name="s" value="sigil"' in html
    assert "No one from this source is followed" in page.sites_page([], [ZEE], {}, {}, False, {"text": ""}, key="zeeprime")


def test_the_sites_route_narrows(monkeypatch):
    monkeypatch.setattr(config, "SITES", [dict(SIGIL, x=["Fiskantes"]), ZEE])
    store.save_site_post({"source": "sigil", "url": "https://www.sigilfund.com/blog/a", "title": "About ZRO",
                          "summary": json.loads(ANSWER), "text": "Long ZRO."}, 1)
    store.save_site_post({"source": "zeeprime", "url": "https://zeeprime.capital/b/", "title": "Argonauts",
                          "summary": json.loads(ANSWER), "text": "Fusion."}, 2)
    html = call("GET", "/sites?q=fusion")[2]
    assert "Argonauts" in html and "About ZRO" not in html
    html = call("GET", "/sites?s=sigil")[2]
    assert "About ZRO" in html and "Argonauts</a></h2>" not in html
    assert call("GET", "/sites?s=nope")[0] == 200  # an unknown source shows them all
