// xbrief's one script: the Brief now button, the rail's live line, the schedule form. The server builds every page;
// this only talks to /api/run, /api/status and /api/settings, and writes text (never markup) into the page.
(() => {
  "use strict";
  const live = document.getElementById("live");
  const run = document.getElementById("run");
  const at = document.body.dataset.at || "";
  let timer = null;

  function show(s) {
    if (!live) return;
    live.className = "live" + (s.kind ? " " + s.kind : "");
    live.textContent = s.text || "";
    if (s.href) {
      const a = document.createElement("a");
      a.href = s.href;
      a.textContent = s.link || "Open";
      live.append(" ", a);
    }
    if (run) run.querySelector("button").disabled = !!s.running;
  }

  async function poll() {
    clearTimeout(timer);
    let s = null;
    try {
      const r = await fetch("/api/status?at=" + encodeURIComponent(at), { cache: "no-store" });
      s = await r.json();
      show(s);
    } catch (e) {
      show({ kind: "bad", text: "The app is not answering." });
    }
    timer = setTimeout(poll, !s || !s.running ? 30000 : s.slow ? 5000 : 1500);
  }

  async function post(path, body) {
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    return { ok: r.ok, j };
  }

  if (run) {
    run.addEventListener("submit", async (e) => {
      e.preventDefault();
      const h = run.elements.hours.value;
      run.querySelector("button").disabled = true;
      const { ok, j } = await post("/api/run", { hours: h ? Number(h) : null });
      if (!ok) show({ kind: "bad", text: j.error || "The run did not start." });
      poll();
    });
  }

  const sched = document.getElementById("sched");
  if (sched) {
    const msg = document.getElementById("sched-msg");
    sched.addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = sched.elements;
      const { ok, j } = await post("/api/settings", {
        schedule: f.on.checked,
        windows: { am: [f.am0.value, f.am1.value], pm: [f.pm0.value, f.pm1.value] },
      });
      if (!ok) {
        msg.textContent = j.error || "Not saved.";
        return;
      }
      location.reload();
    });
  }

  poll();
})();
