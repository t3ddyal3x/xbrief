from builders import BASE_MS, lg_item, lg_module, lg_page, lg_tweet, sid, xw_item, xw_module, xw_page, xw_tweet

from xbrief import parse


def test_snowflake_round_trip():
    assert abs(parse.snowflake_ms(parse.ms_to_snowflake(BASE_MS)) - BASE_MS) < 1


def test_xweb_page():
    orig = xw_tweet(-300, "alice", "the original")
    quoted = xw_tweet(-200, "carol", "quoted words")
    page = xw_page([
        xw_item(xw_tweet(10, "bob", "look https://t.co/abc and pic https://t.co/img",
                         urls=[{"url": "https://t.co/abc", "expanded_url": "https://example.com/a", "display_url": "example.com/a"}],
                         media=[{"type": "photo", "media_url_https": "https://pbs.twimg.com/media/A.jpg"}], rng=[0, 30])),
        xw_item(xw_tweet(9, "dave", "RT @alice: the original", retweet=orig)),
        xw_item(xw_tweet(8, "erin", "so true", quote=quoted, reply_to=(sid(1), "frank"))),
        xw_module([xw_tweet(5, "gina", "1/"), xw_tweet(6, "gina", "2/"), xw_tweet(7, "gina", "3/")], "home-conversation-1"),
        xw_item(xw_tweet(4, "adco", "buy this"), entry_id="promoted-tweet-1", promoted=True),
        xw_item({"__typename": "TweetWithVisibilityResults", "tweet": xw_tweet(3, "hank", "limited")}),
        xw_item({"__typename": "TweetTombstone", "rest_id": sid(2), "tombstone": {}}),
        xw_item(xw_tweet(1, "ivy", "short", note="a much longer note text")),
    ], bottom="NEXT")
    ents, cur = parse.entries(page)
    assert cur == "NEXT"
    assert [len(e.posts) for e in ents] == [1, 1, 1, 3, 1, 1, 1, 1]
    bob = ents[0].posts[0]
    assert bob.handle == "bob" and bob.name == "Bob"
    assert bob.text == "look https://t.co/abc and pic " and bob.links[0]["url"] == "https://example.com/a"
    assert bob.media == [{"type": "photo", "url": "https://pbs.twimg.com/media/A.jpg"}]
    assert bob.created_ms == BASE_MS + 10 * 60_000
    assert ents[1].posts[0].retweet_of.handle == "alice" and ents[1].posts[0].retweet_of.text == "the original"
    erin = ents[2].posts[0]
    assert erin.quote.handle == "carol" and erin.reply_to_handle == "frank" and erin.reply_to_id == sid(1)
    assert ents[3].newest_id == int(sid(7))
    assert ents[4].promoted and not ents[0].promoted
    assert ents[5].posts[0].handle == "hank"
    assert ents[6].posts[0].unreadable == "TweetTombstone"
    assert ents[7].posts[0].text == "a much longer note text"
    assert ents[0].posts[0].url == f"https://x.com/bob/status/{sid(10)}"


def test_legacy_page():
    orig = lg_tweet(-300, "alice", "the original")
    page = lg_page([
        lg_item(lg_tweet(10, "bob", "look https://t.co/abc",
                         urls=[{"url": "https://t.co/abc", "expanded_url": "https://example.com/a", "display_url": "example.com/a"}],
                         media=[{"type": "video", "media_url_https": "https://pbs.twimg.com/ext_tw_video_thumb/1.jpg"}])),
        lg_item(lg_tweet(9, "dave", "RT", retweet=orig)),
        lg_item(lg_tweet(8, "erin", "reply", reply_to=(sid(1), "frank"), quote=lg_tweet(-1, "carol", "q"))),
        lg_module([lg_tweet(5, "gina", "1/"), lg_tweet(6, "gina", "2/"), lg_tweet(7, "gina", "3/")], "home-conversation-1"),
        lg_item(lg_tweet(4, "adco", "ad"), promoted=True),
    ], bottom="NEXT")
    ents, cur = parse.entries(page)
    assert cur == "NEXT" and [len(e.posts) for e in ents] == [1, 1, 1, 3, 1]
    bob = ents[0].posts[0]
    assert bob.handle == "bob" and bob.links[0]["url"] == "https://example.com/a" and bob.media[0]["type"] == "video"
    assert abs(bob.created_ms - (BASE_MS + 10 * 60_000)) < 1000
    assert ents[1].posts[0].retweet_of.handle == "alice"
    assert ents[2].posts[0].quote.handle == "carol" and ents[2].posts[0].reply_to_handle == "frank"
    assert ents[4].promoted


def test_page_without_timeline_is_empty():
    assert parse.entries({"errors": [{"message": "x"}]}) == ([], None)


def test_post_round_trips_through_dict():
    p = parse.post_from_result(xw_tweet(1, "a", "t", quote=xw_tweet(0, "b", "q")))
    assert parse.Post.from_dict(p.to_dict()) == p


def test_an_x_article_keeps_its_title_and_opening():
    t = lg_tweet(10, "ga", "https://t.co/art", urls=[{"url": "https://t.co/art", "expanded_url": "https://x.com/i/article/77",
                                                   "display_url": "x.com/i/article/77"}])
    t["article"] = {"article_results": {"result": {"rest_id": "77", "title": "Is It Going to Die", "preview_text": "TLDR: no."}}}
    p = parse.entries(lg_page([lg_item(t)]))[0][0].posts[0]
    assert p.article == {"title": "Is It Going to Die", "preview": "TLDR: no.", "url": "https://x.com/i/article/77"}
    assert parse.Post.from_dict(p.to_dict()).article == p.article
    assert parse.entries(lg_page([lg_item(lg_tweet(9, "b", "plain"))]))[0][0].posts[0].article is None


def test_an_article_read_whole():
    from builders import post_page, with_article, xw_tweet

    blocks = [{"type": "unstyled", "text": "TLDR: no.", "entityRanges": []},
              {"type": "header-one", "text": "Why", "entityRanges": []},
              {"type": "ordered-list-item", "text": "first", "entityRanges": []},
              {"type": "ordered-list-item", "text": "second", "entityRanges": []},
              {"type": "unstyled", "text": "Source: FT", "entityRanges": [{"key": 2, "offset": 0, "length": 10}]},
              {"type": "atomic", "text": " ", "entityRanges": [{"key": 0, "offset": 0, "length": 1}]},
              {"type": "atomic", "text": " ", "entityRanges": [{"key": 1, "offset": 0, "length": 1}]},
              {"type": "atomic", "text": " ", "entityRanges": [{"key": 3, "offset": 0, "length": 1}]},
              {"type": "unordered-list-item", "text": "a point", "entityRanges": []}]
    emb = xw_tweet(-50, "citrini", "Oh it's over")
    ents = [{"key": "0", "value": {"type": "MEDIA", "data": {"caption": "CDS at 11%"}}},
            {"key": "1", "value": {"type": "TWEET", "data": {"tweetId": emb["rest_id"]}}},
            {"key": "2", "value": {"type": "LINK", "data": {"url": "https://ft.com/x"}}},
            {"key": "3", "value": {"type": "TWEET", "data": {"tweetId": "404"}}}]
    t = with_article(xw_tweet(10, "ga", "https://t.co/a"), blocks=blocks, entities=ents)
    text = parse.articles_in([post_page(t, emb)])[t["rest_id"]]
    assert text == ("TLDR: no.\n\n## Why\n\n1. first\n\n2. second\n\nSource: FT (https://ft.com/x)\n\n[image: CDS at 11%]"
                    "\n\n[a post by @citrini: Oh it's over]\n\n[an embedded post]\n\n- a point")
    assert parse.articles_in([post_page(with_article(xw_tweet(9, "b", "x")))]) == {}  # the feed's copy: no body
    ents_ = parse.entries(xw_page([xw_item(with_article(xw_tweet(10, "ga", "https://t.co/a")))]))[0]
    assert parse.attach_articles(ents_, {t["rest_id"]: text}) == 1 and ents_[0].posts[0].article["text"] == text
