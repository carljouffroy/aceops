/* ACE Ops in the browser: loads CPython (Pyodide), the product's own Python sources and
   contracts into an in-memory filesystem, then answers the console's /api/* calls locally.
   Nothing is sent to any server. The console code is unchanged; fetch is intercepted. */
(function () {
  "use strict";
  const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
  const base = new URL(".", document.currentScript.src);
  const overlay = document.createElement("div");
  overlay.id = "boot";
  overlay.innerHTML = '<div class="boot-card"><div class="boot-mark">ACE OPS</div><div class="boot-line" id="boot-line">Starting the engine in your browser…</div><div class="boot-bar"><i id="boot-bar"></i></div><div class="boot-note">CPython via WebAssembly · the real gates, engine and analysis · state stays in this tab</div></div>';
  const style = document.createElement("style");
  style.textContent = "#boot{position:fixed;inset:0;z-index:999;display:grid;place-items:center;background:#120c08;color:#f6efe4;font-family:'Work Sans','Helvetica Neue',Inter,Arial,sans-serif;transition:opacity .4s}#boot.off{opacity:0;pointer-events:none}.boot-card{text-align:center;max-width:520px;padding:24px}.boot-mark{font-size:40px;letter-spacing:.34em;text-indent:.34em;color:#fff;text-shadow:0 0 30px rgba(255,236,200,.6)}.boot-line{margin-top:18px;color:#e4d8c6}.boot-bar{margin:16px auto 0;width:260px;height:4px;border-radius:4px;background:rgba(243,217,164,.12);overflow:hidden}.boot-bar i{display:block;height:100%;width:5%;background:linear-gradient(90deg,#c9955a,#f3d9a4);transition:width .4s}.boot-note{margin-top:14px;font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#8c7961}";
  document.head.appendChild(style);
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(overlay));
  const say = (t, p) => { const l = document.getElementById("boot-line"); if (l) l.textContent = t; const b = document.getElementById("boot-bar"); if (b && p) b.style.width = p + "%"; };

  let bridge = null;
  const ready = (async () => {
    await new Promise((r) => { const s = document.createElement("script"); s.src = PYODIDE + "pyodide.js"; s.onload = r; s.onerror = () => { say("Could not load the Python runtime (network?).", 0); }; document.head.appendChild(s); });
    say("Loading CPython…", 15);
    const py = await loadPyodide({ indexURL: PYODIDE });
    say("Loading the product's sources and the client data…", 45);
    const manifest = await (await fetch(new URL("fs/manifest.json", base))).json();
    let n = 0;
    for (const rel of manifest.files) {
      const res = await fetch(new URL("fs/" + rel, base));
      const data = rel.endsWith(".csv") ? new Uint8Array(await res.arrayBuffer()) : await res.text();
      const full = "/aceops/" + rel;
      py.FS.mkdirTree(full.slice(0, full.lastIndexOf("/")));
      py.FS.writeFile(full, data);
      n += 1; say(`Loading ${rel}`, 45 + Math.round(40 * n / manifest.files.length));
    }
    py.FS.mkdirTree("/aceops/data");
    say("Generating the Northline sample with the team's own pipeline…", 90);
    try {
      await py.runPythonAsync("import sys, os\nos.chdir('/aceops')\nsys.path.insert(0, '/aceops/src')\nfrom sdlc import browser_bridge\nbrowser_bridge.setup()");
    } catch (e) {
      say("The engine failed to start: " + String(e).split("\n").filter((l) => l.trim()).slice(-1)[0], 0);
      throw e;
    }
    bridge = py.pyimport("sdlc.browser_bridge");
    say("Ready.", 100);
    setTimeout(() => { overlay.classList.add("off"); }, 300);
    setInterval(() => { try { bridge.tick(); } catch (e) { console.warn("tick", e); } }, 3000);
    return bridge;
  })();

  const realFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : input.url;
    const u = new URL(url, location.href);
    if (!u.pathname.startsWith("/api/")) return realFetch(input, init);
    await ready;
    const method = ((init && init.method) || "GET").toUpperCase();
    const body = init && init.body ? String(init.body) : null;
    const out = JSON.parse(bridge.handle(method, u.pathname + u.search, body));
    const isText = Object.prototype.hasOwnProperty.call(out, "text");
    return new Response(isText ? out.text : JSON.stringify(out.json), { status: out.status, headers: { "content-type": isText ? "text/plain; charset=utf-8" : "application/json" } });
  };
})();
