// xbrief's one script: the Brief now button, the rail's live line, the schedule form, the Sites tab's check. The
// server builds every page; this only talks to /api/run, /api/status, /api/settings and /api/sites, and writes text
// (never markup) into the page.
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

  const sites = document.getElementById("sites");
  if (sites) {
    const msg = document.getElementById("sites-msg");
    const now = document.getElementById("sites-now");
    async function wait() {  // while a check goes, look every 3 s; reload when it is done
      try {
        const r = await fetch("/api/sites", { cache: "no-store" });
        const j = await r.json();
        if (!j.checking) return location.reload();
      } catch (e) { /* the app restarting: look again */ }
      setTimeout(wait, 3000);
    }
    sites.addEventListener("submit", async (e) => {
      e.preventDefault();
      const { ok, j } = await post("/api/sites", { daily: sites.elements.daily.checked });
      msg.textContent = ok ? "Saved." : (j.error || "Not saved.");
    });
    now.addEventListener("click", async () => {
      now.disabled = true;
      const { ok, j } = await post("/api/sites", { check: true });
      msg.textContent = ok ? "Checking the sites now… a new post takes a minute or two to read." : (j.error || "The check did not start.");
      if (ok || j.error) setTimeout(wait, 3000);
    });
    if (msg.dataset.checking) setTimeout(wait, 3000);
  }

  poll();
})();
