"""Long videos: which are read, X's captions or Whisper on the audio, YouTube by Whisper, kept by key, summarised,
given to the writer and shown. Every fetch, ffmpeg, yt-dlp and Whisper is faked."""

import json
import pathlib
import shutil

import pytest

from builders import BASE_MS, lg_item, lg_page, lg_tweet, xw_item, xw_page, xw_tweet

from xbrief import brief, cli, config, page, parse, store, videos, whisper

STREAM = "https://video.twimg.com/amplify_video/77/pl/abc.m3u8?tag=29"
MASTER = """#EXTM3U
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="en (auto-generated)",URI="/amplify_video/77/pl/s0/subs.m3u8",LANGUAGE="en"
#EXT-X-MEDIA:NAME="Audio",TYPE=AUDIO,GROUP-ID="audio-32000",URI="/amplify_video/77/pl/mp4a/32000/a32.m3u8"
#EXT-X-MEDIA:NAME="Audio",TYPE=AUDIO,GROUP-ID="audio-64000",URI="/amplify_video/77/pl/mp4a/64000/a64.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=148650,RESOLUTION=480x270,AUDIO="audio-32000"
/amplify_video/77/pl/avc1/480x270/v.m3u8
"""
SUBS = "#EXTM3U\n#EXT-X-TARGETDURATION:1200\n#EXTINF:1175.0,\n/amplify_video/77/pl/s0/0.vtt\n#EXT-X-ENDLIST\n"
VTT = """WEBVTT
X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:0

1
00:00:00.000 --> 00:00:02.000
<X-word-ms ms=339,80 index=1 character_ranges=0-3,4-7>Last year</X-word-ms> <X-word-ms ms=9 index=2>we asked &amp; won</X-word-ms>

NOTE a note
that runs on

2
00:00:02.000 --> 00:00:04.000
FinCEN listened.

3
00:00:04.000 --> 00:00:09.000
""" + "and then we kept on talking " * 5 + """

4
00:00:09.000 --> 00:00:10.000
The end.
"""
SUMMARY = json.dumps({"gist": "A speech on <b>crypto</b> law.", "points": ["They won."], "calls": ["Long ETH into 2027"],
                      "view": "One side only."})


@pytest.fixture(autouse=True)
def fresh_videos():
    shutil.rmtree(config.VIDEOS, ignore_errors=True)


def fake_get(pages):
    asked = []

    def get(url):
        asked.append(url)
        return pages[url]

    get.asked = asked
    return get


def x_pages(master=MASTER):
    return {STREAM: master, "https://video.twimg.com/amplify_video/77/pl/s0/subs.m3u8": SUBS,
            "https://video.twimg.com/amplify_video/77/pl/s0/0.vtt": VTT}


class FakeRun:
    """ffmpeg and yt-dlp write their file; Whisper writes its JSON; each command is kept."""

    def __init__(self, info="1500\tFalse\tA Long Interview", text="words " * 40):
        self.cmds, self.info, self.text = [], info, text

    def __call__(self, cmd, **kw):
        self.cmds.append(cmd)
        if cmd[0] == config.FFMPEG:
            pathlib.Path(cmd[-1]).write_bytes(b"audio")
        elif cmd[0] == config.YT_DLP and "--print" in cmd:
            return type("R", (), {"stdout": self.info + "\n"})()
        elif cmd[0] == config.YT_DLP:
            out = cmd[cmd.index("-o") + 1].replace("%(ext)s", "webm")
            pathlib.Path(out).write_bytes(b"audio")
        elif cmd[1:3] == ["-m", "xbrief.whisper"]:
            pathlib.Path(cmd[4]).write_text(json.dumps({"text": self.text, "segments": []}))
        return type("R", (), {"stdout": ""})()


def x_item(key="x-77"):
    return {"key": key, "kind": "x", "url": "https://x.com/pv/status/1", "stream": STREAM, "duration_s": 1175, "by": "pv"}


def test_the_feed_gives_a_video_its_length_and_stream_and_youtube_links_are_found():
    t = lg_tweet(10, "pv", "watch https://t.co/y", urls=[
        {"url": "https://t.co/y", "expanded_url": "https://www.youtube.com/watch?v=UTv_fyfpvF8&t=3", "display_url": "youtube.com"}],
        media=[{"type": "video", "id_str": "77", "media_url_https": "https://pbs.twimg.com/thumb.jpg",
                "video_info": {"duration_millis": 1175011, "variants": [
                    {"content_type": "application/x-mpegURL", "url": STREAM},
                    {"bitrate": 256000, "content_type": "video/mp4", "url": "https://video.twimg.com/v.mp4"}]}}])
    p = parse.entries(lg_page([lg_item(t)]))[0][0].posts[0]
    assert p.media == [{"type": "video", "url": "https://pbs.twimg.com/thumb.jpg", "id": "77", "duration_s": 1175, "stream": STREAM}]
    assert parse.youtube_ids(p) == ["UTv_fyfpvF8"]
    for u in ("https://youtu.be/UTv_fyfpvF8", "https://www.youtube.com/live/UTv_fyfpvF8?si=x", "https://m.youtube.com/watch?feature=share&v=UTv_fyfpvF8"):
        assert parse.youtube_ids(parse.Post("1", "a", "", 0, "", links=[{"url": u}])) == ["UTv_fyfpvF8"]


def test_only_long_videos_are_wanted_quoted_ones_too_each_once():
    def vid(i, s):
        return {"type": "video", "url": "u", "id": str(i), "duration_s": s, "stream": f"{STREAM}&{i}"}
    q = parse.Post("2", "q", "", 0, "", media=[vid(5, 3600)])
    posts = {"1": parse.Post("1", "a", "", 0, "", media=[vid(1, 599), vid(2, 600)], quote=q),
             "3": parse.Post("3", "b", "", 0, "", quote=q, links=[{"url": "https://youtu.be/abcdefghijk"}])}
    assert [(w["key"], w["by"]) for w in videos.wanted(posts)] == [("x-2", "a"), ("x-5", "q"), ("yt-abcdefghijk", "b")]


def test_vtt_keeps_only_the_words():
    assert videos.vtt_text(VTT) == ["Last year we asked & won", "FinCEN listened.",
                                    " ".join(["and then we kept on talking"] * 5), "The end."]


def test_an_x_video_with_captions_is_read_from_them_summarised_and_kept():
    get, run = fake_get(x_pages()), FakeRun()
    asked = []
    doc = videos.read(x_item(), get=get, run=run, ask=lambda t: asked.append(t) or SUMMARY)
    assert doc["transcript"].startswith("Last year we asked & won FinCEN listened. and then") and doc["source"] == "X's captions"
    assert run.cmds == []  # no audio, no Whisper
    assert "BEGIN VIDEO" in asked[0] and asked[0].endswith("The end.\n") and '"length": "20 minutes"' in asked[0]
    assert doc["summary"]["gist"] == "A speech on <b>crypto</b> law." and videos.kept("x-77")["summary"] == doc["summary"]
    again = videos.read(x_item(), get=fake_get({}), run=run, ask=lambda t: 1 / 0)  # kept: nothing is fetched again
    assert again["summary"] == doc["summary"]


def test_an_x_video_without_captions_gets_whisper_on_its_audio_track_only():
    master = "\n".join(ln for ln in MASTER.splitlines() if "SUBTITLES" not in ln)
    run = FakeRun(text="  spoken   " + "words " * 40)
    doc = videos.read(x_item(), get=fake_get(x_pages(master)), run=run, ask=lambda t: SUMMARY)
    ff = run.cmds[0]
    assert ff[0] == config.FFMPEG and ff[ff.index("-i") + 1] == "https://video.twimg.com/amplify_video/77/pl/mp4a/64000/a64.m3u8"
    assert "-vn" in ff and run.cmds[1][1:3] == ["-m", "xbrief.whisper"]
    assert doc["source"] == "Whisper large-v3" and doc["transcript"].startswith("spoken")


def test_captions_in_another_language_are_passed_over_for_whisper_in_english(monkeypatch, tmp_path):
    master = MASTER.replace('LANGUAGE="en"', 'LANGUAGE="ms"').replace('NAME="en ', 'NAME="ms ')
    run = FakeRun()
    doc = videos.read(x_item(), get=fake_get(x_pages(master)), run=run, ask=lambda t: SUMMARY)
    assert doc["source"] == "Whisper large-v3" and run.cmds[1][1:3] == ["-m", "xbrief.whisper"]
    seen = {}

    def transcribe(audio, **kw):
        seen.update(kw)
        return {"language": kw["language"], "text": " said ", "segments": [{"start": 0.0, "text": " said "}]}

    monkeypatch.setitem(__import__("sys").modules, "mlx_whisper", type("M", (), {"transcribe": staticmethod(transcribe)}))
    whisper.main("a.m4a", str(tmp_path / "out.json"))
    assert seen["language"] == "en" and json.loads((tmp_path / "out.json").read_text())["text"] == "said"


def test_a_youtube_video_gets_whisper_and_a_short_or_live_one_is_left_out():
    run = FakeRun()
    doc = videos.read({"key": "yt-abcdefghijk", "kind": "youtube", "url": "https://www.youtube.com/watch?v=abcdefghijk",
                       "by": "b"}, run=run, ask=lambda t: SUMMARY)
    assert doc["title"] == "A Long Interview" and doc["duration_s"] == 1500 and doc["source"] == "Whisper large-v3"
    assert [c[0] for c in run.cmds[:2]] == [config.YT_DLP, config.YT_DLP] and "bestaudio" in " ".join(run.cmds[1])
    short = videos.read({"key": "yt-shortshort", "kind": "youtube", "url": "u", "by": "b"}, run=FakeRun("110\tFalse\tBungee"))
    assert short["skip"] == "shorter than 10 minutes" and videos.kept("yt-shortshort")["skip"]
    live = videos.read({"key": "yt-livelivelive", "kind": "youtube", "url": "u", "by": "b"}, run=FakeRun("NA\tTrue\tLive"))
    assert live["skip"] == "live now"


def test_a_failure_is_said_not_kept_and_a_kept_transcript_is_not_redone():
    def broken(url):
        raise OSError("HTTP Error 403")

    doc = videos.read(x_item("x-88"), get=broken, run=FakeRun(), ask=lambda t: SUMMARY)
    assert doc["error"] == "OSError: HTTP Error 403" and videos.kept("x-88") is None
    get = fake_get(x_pages())
    doc = videos.read(x_item("x-88"), get=get, ask=lambda t: "no json")  # the transcript is kept, the summary fails
    assert doc["error"].startswith("ValueError") and videos.kept("x-88")["transcript"]
    get2 = fake_get({})
    doc = videos.read(x_item("x-88"), get=get2, ask=lambda t: SUMMARY)
    assert doc["summary"] and get2.asked == []
    music = {**x_pages(), "https://video.twimg.com/amplify_video/77/pl/s0/0.vtt": "WEBVTT\n\n00:00.000 --> 00:01.000\nMusic."}
    silent = videos.read(x_item("x-99"), get=fake_get(music), run=FakeRun(), ask=lambda t: 1 / 0)
    assert silent["skip"] == "almost no speech"


def test_the_key_names_only_a_kept_file():
    assert videos.kept("../secrets/x") is None and videos.kept("x-1/../../a") is None


def test_a_brief_with_a_long_video_gives_the_writer_its_summary_and_shows_it():
    t = xw_tweet(10, "pv", "my speech")
    p = parse.entries(xw_page([xw_item(t)]))[0][0].posts[0]
    p.media = [{"type": "video", "url": "https://pbs.twimg.com/t.jpg", "id": "77", "duration_s": 1175, "stream": STREAM}]
    ents = [parse.Entry("e", "1", [p])]
    docs, left = videos.read_all({p.id: p}, get=fake_get(x_pages()), run=FakeRun(), ask=lambda t: SUMMARY)
    assert left == 0 and videos.attach(ents, docs) == 1 and videos.attach(ents, docs) == 0
    line = json.loads(brief._line(p))
    assert line["videos"] == [{"length": "20 min", "gist": "A speech on <b>crypto</b> law.", "points": ["They won."],
                               "calls": ["Long ETH into 2027"]}] and "transcript" not in json.dumps(line)
    assert '("videos"): its summary was written from the whole transcript' in brief.PROMPT
    assert "a long video's summary always has something to say" in brief.PROMPT
    b = brief.parse_answer(json.dumps({"theses": [{"posts": [p.id], "claim": "Law changed."}]}), {p.id: p})
    html = page.thesis_html(b.theses[0], {p.id: p}, {}, "th0")
    assert '<span class="n">Video · @pv</span>' in html and "A speech on &lt;b&gt;crypto&lt;/b&gt; law." in html
    assert '<a href="/video/x-77">read it</a>' in html and "<b>crypto</b>" not in html


def test_publish_reads_the_videos_and_says_what_failed():
    from test_app import call

    t = xw_tweet(10, "pv", "my speech")
    t["media_entities2"] = []
    pages = [xw_page([xw_item(t)])]
    meta = {"stop": "caught up", "normal": True, "gap": False, "started_ms": BASE_MS, "boundary_id": 0}

    def read_videos(posts):
        (p,) = posts.values()
        p.media = [{"type": "video", "url": "u", "id": "77", "duration_s": 1175, "stream": STREAM}]
        return videos.read_all(posts, get=fake_get(x_pages()), run=FakeRun(), ask=lambda t: SUMMARY)

    name = cli.publish(pages, meta, "am", ask=lambda t: "{}", read_videos=read_videos)
    run = store.load_run(name)
    assert run["meta"]["videos_read"] == 1 and run["meta"]["videos_failed"] == []
    (p,) = run["posts"].values()
    assert p.videos[0]["transcript"].startswith("Last year") and store.search("fincen")[0]
    code, _, html = call("GET", "/video/x-77")
    assert code == 200 and "FinCEN listened." in html and "Transcript: X&#x27;s captions" in html
    assert call("GET", "/video/x-nope")[0] == 404
    assert "2 long videos past the cap" in page.status_html({**meta, "videos_left": 2}, brief.Brief())
    assert "x-9: OSError" in page.status_html({**meta, "videos_failed": ["x-9: OSError: 403"]}, brief.Brief())


def test_a_transcript_reads_in_paragraphs():
    text = " ".join(["word"] * 79 + ["end."] + ["more"] * 130)
    paras = page.paragraphs(text)
    assert [len(p.split()) for p in paras] == [80, 120, 10] and paras[0].endswith("end.")


# ── podcasts ──

SP_ID = "5AqOmZDGZcMj1OyBLWvcXW"
FEED = "https://feeds.example.com/oddlots.rss"
EMBED = ('<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": {"state": {
    "data": {"entity": {"title": "Jeff Yan’s Plan for Hyperliquid", "subtitle": "Odd Lots", "duration": 3480111}}}}}})
         + "</script></html>")
SEARCH = "https://itunes.apple.com/search?term=Odd+Lots&media=podcast&entity=podcast&limit=10"
DIRECTORY = json.dumps({"results": [{"collectionName": "Odd Lot Improv", "feedUrl": "https://other.example/rss"},
                                    {"collectionName": "Odd Lots", "feedUrl": FEED}]})
SHOW_VTT = """WEBVTT - Jeff Yan's Plan

0:00:02.750 --> 0:00:04.430
<v Speaker 1>Hello and welcome to Odd Lots.

0:00:04.890 --> 0:00:05.590
<v Speaker 1>I'm Joe.

0:00:05.890 --> 0:00:06.430
<v Speaker 2>And I'm Tracy. """ + "we talk about markets " * 10 + """
"""


def rss(transcripts=True, title="Jeff Yan's Plan for Hyperliquid"):
    tx = ('<podcast:transcript url="https://api.example/t.srt" type="application/srt" language="en"/>'
          '<podcast:transcript url="https://api.example/t.vtt" type="text/vtt" language="en"/>'
          '<podcast:transcript url="https://api.example/es.vtt" type="text/vtt" language="es"/>') if transcripts else ""
    return f"""<?xml version="1.0"?><rss xmlns:podcast="https://podcastindex.org/namespace/1.0"><channel>
<item><title>Another Episode</title><enclosure url="https://cdn.example/other.mp3" type="audio/mpeg"/></item>
<item><title>{title}</title><enclosure url="https://cdn.example/jy.mp3" type="audio/mpeg"/>{tx}</item>
</channel></rss>"""


def sp_post():
    return {"1": parse.Post("1", "TheStalwart", "NEW ODD LOTS", 0, "", links=[
        {"url": f"https://open.spotify.com/episode/{SP_ID}?si=6r5vLG4ARt68WLAtkQNK3Q&utm_source=copy-link"},
        {"url": f"https://open.spotify.com/intl-de/episode/{SP_ID}"},
        {"url": "https://podcasts.apple.com/us/podcast/jeff-yans-plan/id1056200096?i=1000796459553"}])}


def test_spotify_and_apple_episode_links_are_found_each_once():
    assert [(w["key"], w["kind"]) for w in videos.wanted(sp_post())] == [(f"sp-{SP_ID}", "podcast"), ("ap-1000796459553", "podcast")]
    assert videos.wanted(sp_post())[1]["show_id"] == "1056200096"


def test_a_spotify_episode_is_read_from_the_shows_own_english_transcript_with_its_speakers():
    get = fake_get({f"https://open.spotify.com/embed/episode/{SP_ID}": EMBED, SEARCH: DIRECTORY, FEED: rss(),
                    "https://api.example/t.vtt": SHOW_VTT})
    run, asked = FakeRun(), []
    doc = videos.read(videos.wanted(sp_post())[0], get=get, run=run, ask=lambda t: asked.append(t) or SUMMARY)
    assert doc["show"] == "Odd Lots" and doc["title"] == "Jeff Yan’s Plan for Hyperliquid" and doc["duration_s"] == 3480
    assert doc["source"] == "the show's own" and run.cmds == []  # no audio, no Whisper
    assert doc["transcript"].splitlines()[:2] == ["Speaker 1: Hello and welcome to Odd Lots. I'm Joe.",
                                                 "Speaker 2: And I'm Tracy. " + " ".join(["we talk about markets"] * 10)]
    assert "https://api.example/es.vtt" not in get.asked and '"show": "Odd Lots"' in asked[0]
    assert page.paragraphs(doc["transcript"])[0] == "Speaker 1: Hello and welcome to Odd Lots. I'm Joe."


def test_an_apple_episode_without_a_transcript_gets_whisper_on_the_feeds_audio():
    lookup = json.dumps({"results": [{"wrapperType": "track", "collectionName": "Odd Lots", "feedUrl": FEED},
                                     {"wrapperType": "podcastEpisode", "trackId": 1000796459553, "collectionName": "Odd Lots",
                                      "trackName": "Jeff Yan's Plan for Hyperliquid", "trackTimeMillis": 3480000, "feedUrl": FEED}]})
    get = fake_get({"https://itunes.apple.com/lookup?id=1056200096&entity=podcastEpisode&limit=300": lookup,
                    FEED: rss(transcripts=False)})
    run = FakeRun()
    doc = videos.read(videos.wanted(sp_post())[1], get=get, run=run, ask=lambda t: SUMMARY)
    ff = run.cmds[0]
    assert ff[0] == config.FFMPEG and ff[ff.index("-i") + 1] == "https://cdn.example/jy.mp3" and "-vn" in ff
    assert doc["source"] == "Whisper large-v3" and doc["summary"]["gist"]


def test_an_episode_no_public_feed_lists_is_said_and_a_short_one_left_out():
    get = fake_get({f"https://open.spotify.com/embed/episode/{SP_ID}": EMBED, SEARCH: DIRECTORY, FEED: rss(title="Something else")})
    doc = videos.read(videos.wanted(sp_post())[0], get=get, run=FakeRun(), ask=lambda t: SUMMARY)
    assert doc["error"] == "ValueError: no public feed of Odd Lots lists this episode" and videos.kept(f"sp-{SP_ID}") is None
    short = fake_get({f"https://open.spotify.com/embed/episode/{SP_ID}": EMBED.replace("3480111", "300000"), SEARCH: DIRECTORY})
    assert videos.read(videos.wanted(sp_post())[0], get=short, run=FakeRun())["skip"] == "shorter than 10 minutes"


def test_a_podcast_shows_as_one_on_the_post():
    p = parse.Post("1", "TheStalwart", "", 0, "", videos=[{"key": f"sp-{SP_ID}", "kind": "podcast", "url": "https://open.spotify.com/x",
                                                          "duration_s": 3480, "show": "Odd Lots", "title": "Jeff Yan",
                                                          "source": "the show's own", "summary": json.loads(SUMMARY)}])
    h = page.vids(p)
    assert "<b>Podcast</b> · 58 min · Odd Lots · Jeff Yan</summary>" in h and ">listen</a>" in h
