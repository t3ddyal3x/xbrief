"""Which site build X serves this account, and how that build asks for the Following tab.

X is moving x.com from its old web app ("legacy": abs.twimg.com/responsive-web/…/main.*.js, requests to
x.com/i/api/graphql/<id>/HomeLatestTimeline with a features block) to a new one ("xweb": abs.twimg.com/x-web/…,
Relay persisted queries to api.x.com/graphql/<id>/HomeLatestTimelineQuery, no features block). On 2026-10-12
the logged-out site was xweb; what a logged-in account gets is read from its own home page, every run.

Nothing here is hard-coded per deploy: the request id, the variables and their order, and (legacy) the
feature switches are read from the scripts the page names, the way the page itself reads them. Script files
have content-hashed names, so each is fetched once and kept in the cache.
"""

from __future__ import annotations

import heapq
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Awaitable, Callable
from urllib.parse import urljoin

from . import config

GetText = Callable[[str], Awaitable[str]]

LEGACY_MAIN = re.compile(r"https://abs\.twimg\.com/responsive-web/client-web(?:-legacy)?/main\.[\w]+\.js")
XWEB_ENTRY = re.compile(r"https://abs\.twimg\.com/x-web/[\w./-]*entry-client[\w.-]*\.js")
LOGGED_OUT = "entry-client-logged-out"
XWEB_IMPORT = re.compile(r"""["'`](\.{1,2}/[\w./-]+\.js)["'`]""")

LEGACY_NAME = "HomeLatestTimeline"
XWEB_NAME = "HomeLatestTimelineQuery"
XWEB_SCAN_CAP = 3000  # script files fetched at most while looking for the operation


class SiteError(Exception):
    """The page is not what a logged-in account gets, or the operation cannot be found."""


class LoggedOut(SiteError): ...


@dataclass
class Op:
    build: str  # "legacy" | "xweb"
    query_id: str
    name: str
    script: str  # the script file the operation was read from
    page_script: str  # the main/entry script the page named; a new one means a new deploy
    variables: list[list] = field(default_factory=list)  # xweb: [name, default] in the operation's order
    provided: dict = field(default_factory=dict)  # xweb: Relay's provided variables and the values sent
    features: dict = field(default_factory=dict)  # legacy: feature switches and their values
    field_toggles: dict = field(default_factory=dict)  # legacy

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Op":
        return cls(**json.loads(text))


def detect(html: str) -> tuple[str, str]:
    """(build, the script the page names). Raises LoggedOut / SiteError."""
    if LOGGED_OUT in html:
        raise LoggedOut("x.com/home came back as the logged-out site: the login has expired or was revoked")
    m = LEGACY_MAIN.search(html)
    if m:
        return "legacy", m.group(0)
    m = XWEB_ENTRY.search(html)
    if m:
        return "xweb", m.group(0)
    raise SiteError("x.com/home names neither the old web app's main script nor the new app's entry script")


async def cached(url: str, get_text: GetText) -> str:
    name = url.rsplit("/", 1)[-1]
    if not re.fullmatch(r"[\w.~-]+\.js", name):
        raise SiteError(f"unexpected script name {name!r}")
    path = config.CACHE / name
    if path.exists():
        return path.read_text(errors="replace")
    text = await get_text(url)
    config.CACHE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_text(text)
    tmp.replace(path)
    return text


# ── legacy ──────────────────────────────────────────────────────────────────────────────────────────

LEGACY_OP = re.compile(
    r'queryId:"([\w-]+)",operationName:"' + LEGACY_NAME + r'",operationType:"query",'
    r"metadata:\{featureSwitches:\[([^\]]*)\],fieldToggles:\[([^\]]*)\]"
)


def initial_state(html: str) -> dict:
    i = html.find("window.__INITIAL_STATE__=")
    if i < 0:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(html, i + len("window.__INITIAL_STATE__="))
        return obj if isinstance(obj, dict) else {}
    except ValueError:
        return {}


def switch_values(state: dict) -> dict:
    fs = state.get("featureSwitch") or {}
    out = {}
    for src in ((fs.get("defaultConfig") or {}), ((fs.get("user") or {}).get("config") or {})):
        for k, v in src.items():
            if isinstance(v, dict) and "value" in v:
                out[k] = v["value"]
    return out


def _legacy_rank(url: str) -> int:
    name = url.rsplit("/", 1)[-1]
    return 0 if name.startswith("main.") else 1 if re.search(r"home|timeline", name, re.I) else 2


async def legacy_op(html: str, main_url: str, get_text: GetText) -> Op:
    """The old app defines its requests across main.js and the chunks the page maps (2026-10-12: the Following
    tab's is not in main.js). Search main, then chunks named for home or timelines, then the rest."""
    from twscrape.xclid import get_scripts_list

    urls = [u for u in dict.fromkeys([main_url] + get_scripts_list(html)) if "/responsive-web/" in u]
    urls.sort(key=_legacy_rank)
    for url in urls[:XWEB_SCAN_CAP]:
        m = LEGACY_OP.search(await cached(url, get_text))
        if m:
            return _legacy_from_match(m, html, url, main_url)
    raise SiteError(f"{LEGACY_NAME} not found in {len(urls)} script files the page maps")


def _legacy_from_match(m: re.Match, html: str, script_url: str, main_url: str) -> Op:
    names = re.findall(r'"(\w+)"', m.group(2))
    toggles = re.findall(r'"(\w+)"', m.group(3))
    values = switch_values(initial_state(html))
    from twscrape.api import GQL_FEATURES  # the fork's fallback values, used only where the page has none

    features = {n: values.get(n, GQL_FEATURES.get(n, False)) for n in names}
    field_toggles = {n: values.get(n, False) for n in toggles}
    return Op("legacy", m.group(1), LEGACY_NAME, script_url, main_url, features=features, field_toggles=field_toggles)


# ── xweb ────────────────────────────────────────────────────────────────────────────────────────────

XWEB_PARAMS = re.compile(r"params:\{id:`([\w-]+)`,metadata:\{[^}]*\},name:`" + XWEB_NAME + r"`")
LOCAL_ARG = re.compile(r"(\w+)=\{defaultValue:([^,{}]+),kind:`LocalArgument`,name:`(\w+)`\}")
OP_ARGS = re.compile(r"operation:\{argumentDefinitions:\[(.*?)\],kind:`Operation`,name:`" + XWEB_NAME + "`")
ARG_ITEM = re.compile(r"\{defaultValue:([^,{}]+),kind:`LocalArgument`,name:`(\w+)`\}|(\w+)")


def _default(token: str):
    token = token.strip()
    return {"null": None, "!0": True, "!1": False, "true": True, "false": False}.get(
        token, int(token) if re.fullmatch(r"-?\d+", token) else token.strip("`\"'")
    )


def provided_value(name: str):
    if "isloggedin" in name.lower():
        return True
    return False  # feature switches the page reads with a false default (e.g. Grok note auto-translation)


def xweb_op_from_chunk(chunk: str, chunk_url: str, entry_url: str) -> Op | None:
    m = XWEB_PARAMS.search(chunk)
    if not m:
        return None
    start = chunk.rfind("(function(){", 0, m.start())
    body = chunk[start if start >= 0 else 0 : m.end()]
    local = {letter: (name, _default(dv)) for letter, dv, name in LOCAL_ARG.findall(body)}
    args = OP_ARGS.search(body)
    if not args:
        raise SiteError(f"{XWEB_NAME}'s argument list is not where it was on 2026-10-12")
    variables = []
    for dv, name, letter in ARG_ITEM.findall(args.group(1)):
        if name:
            variables.append([name, _default(dv)])
        elif letter in local:
            variables.append(list(local[letter]))
        else:
            raise SiteError(f"{XWEB_NAME} argument {letter!r} has no definition")
    provided = {n: provided_value(n) for n, _ in variables if n.startswith("__relay_internal__pv__")}
    return Op("xweb", m.group(1), XWEB_NAME, chunk_url, entry_url, variables=variables, provided=provided)


async def xweb_op(entry_url: str, get_text: GetText) -> Op:
    """Walk the entry's imports, files named home* first, until one defines the operation."""
    seen: set[str] = set()
    queue: list[tuple[int, int, str]] = [(0, 0, entry_url)]
    n = 0
    while queue and n < XWEB_SCAN_CAP:
        _, _, url = heapq.heappop(queue)
        if url in seen:
            continue
        seen.add(url)
        n += 1
        text = await cached(url, get_text)
        op = xweb_op_from_chunk(text, url, entry_url)
        if op:
            return op
        for rel in XWEB_IMPORT.findall(text):
            nxt = urljoin(url, rel)
            if nxt not in seen and nxt.startswith("https://abs.twimg.com/"):
                name = nxt.rsplit("/", 1)[-1]
                heapq.heappush(queue, (0 if name.startswith("home") else 1, n, nxt))
    raise SiteError(f"{XWEB_NAME} not found in {n} script files reachable from the entry")


# ── both ────────────────────────────────────────────────────────────────────────────────────────────


def load_saved() -> Op | None:
    try:
        return Op.from_json(config.SITE.read_text())
    except (OSError, ValueError, TypeError):
        return None


async def resolve(html: str, get_text: GetText) -> tuple[Op, bool]:
    """The operation for the build this page is, and whether it was re-read (a new deploy)."""
    build, page_script = detect(html)
    saved = load_saved()
    if saved and saved.build == build and saved.page_script == page_script:
        return saved, False
    if build == "legacy":
        op = await legacy_op(html, page_script, get_text)
    else:
        op = await xweb_op(page_script, get_text)
    tmp = config.SITE.with_suffix(".part")
    tmp.write_text(op.to_json())
    tmp.replace(config.SITE)
    return op, True
