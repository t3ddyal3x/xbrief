"""A stand-in for x.com/home on loopback, for the browser tests: a For you / Following tablist, a feed that asks
for the next page when the reader scrolls near its end (as x.com does, with an IntersectionObserver), and a log of
every feed request with what the page reported (document.visibilityState, X's x-twitter-active-user)."""

from __future__ import annotations

import http.server
import json
import threading
import urllib.parse

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Home / X</title>
<style>body{margin:0;font:15px sans-serif}nav{position:sticky;top:0;background:#fff;display:flex;gap:2rem;padding:1rem}
.post{height:260px;border-bottom:1px solid #ccc;padding:1rem}#end{height:40px}</style></head><body>
<nav role="tablist"><a role="tab" href="#" id="fy" aria-selected="true"><span>For you</span></a>
<a role="tab" href="#" id="fo" aria-selected="false"><span>Following</span></a></nav>
<main id="feed"></main><div id="end"></div>
<script>
const feed=document.getElementById('feed');let cursor=null,busy=false,mode='foryou';
async function load(){
  if(busy)return;busy=true;
  const op=mode==='following'?'QL/HomeLatestTimeline':'QF/HomeTimeline';
  const r=await fetch('/i/api/graphql/'+op+'?variables='+encodeURIComponent(JSON.stringify({count:20,enableRanking:false}))+'&cursor='+encodeURIComponent(cursor??''),
    {headers:{'x-twitter-active-user':document.visibilityState!=='hidden'?'yes':'no','x-vis':document.visibilityState}});
  const j=await r.json();busy=false;
  const n=j.render||0;for(let i=0;i<n;i++){const d=document.createElement('div');d.className='post';d.textContent=mode+' post';feed.appendChild(d);}
  cursor=j.next;
}
document.getElementById('fo').addEventListener('click',e=>{e.preventDefault();mode='following';cursor=null;feed.innerHTML='';
  document.getElementById('fo').setAttribute('aria-selected','true');load();});
new IntersectionObserver(es=>{if(es[0].isIntersecting&&cursor)load();},{rootMargin:'600px'}).observe(document.getElementById('end'));
load();
</script></body></html>"""


class FakeX:
    def __init__(self, pages: list[dict], status: int = 200, redirect_home_to: str | None = None):
        self.pages = pages  # Following-tab pages, in order; each gets "next" = its index + 1 unless it is the last
        self.status = status
        self.redirect_home_to = redirect_home_to
        self.log: list[dict] = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                b = body.encode() if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("content-type", ctype)
                self.send_header("content-length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                if u.path == "/home":
                    if outer.redirect_home_to:
                        self.send_response(302)
                        self.send_header("location", outer.redirect_home_to)
                        self.end_headers()
                        return
                    return self._send(200, PAGE, "text/html")
                if u.path.startswith("/i/flow/login"):
                    return self._send(200, "<html><title>Log in</title></html>", "text/html")
                if u.path.endswith("/HomeTimeline"):
                    outer.log.append({"op": "HomeTimeline", "vis": self.headers.get("x-vis"),
                                      "active": self.headers.get("x-twitter-active-user")})
                    return self._send(200, json.dumps({"data": {}, "render": 8, "next": None}))
                if u.path.endswith("/HomeLatestTimeline"):
                    cur = urllib.parse.parse_qs(u.query).get("cursor", [""])[0]
                    i = int(cur) if cur else 0
                    outer.log.append({"op": "HomeLatestTimeline", "i": i, "vis": self.headers.get("x-vis"),
                                      "active": self.headers.get("x-twitter-active-user")})
                    if outer.status != 200:
                        return self._send(outer.status, json.dumps({"errors": [{"message": "Rate limit exceeded"}]}))
                    if i >= len(outer.pages):
                        return self._send(200, json.dumps({"data": {"home": {"home_timeline_urt": {"instructions": []}}}, "render": 0, "next": None}))
                    body = dict(outer.pages[i])
                    body["render"] = 20
                    body["next"] = str(i + 1) if i + 1 < len(outer.pages) else None
                    return self._send(200, json.dumps(body))
                self._send(404, "{}")

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def home(self) -> str:
        return f"http://127.0.0.1:{self.port}/home"

    def stop(self):
        self.server.shutdown()
