"""Build docs/app: the ACE Ops console running entirely in the browser.

Copies the console page (theme inlined, the browser bridge injected), the Python
sources it needs, the contracts and the sample dataset into docs/app so GitHub
Pages can serve the whole product as static files. Run: uv run python scripts/build_site.py
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "app"
FS = OUT / "fs"

SOURCE_GLOBS = [
    ("src/sdlc", ["*.py", "agents/*.py"]),
    ("src/internal", ["*.py"]),
    ("contracts", ["bundle.json", "answers.sample.json"]),
    ("contracts/sdlc", ["*.json"]),
    ("contracts/sdlc/datasets", ["*.csv", "*.json"]),
]
SKIP = {"api.py", "mcp_server.py", "__main__.py"}  # server-only modules; everything else is stdlib


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    FS.mkdir(parents=True)
    files: list[str] = []
    for folder, patterns in SOURCE_GLOBS:
        for pattern in patterns:
            for path in sorted((ROOT / folder).glob(pattern)):
                if path.name in SKIP or not path.is_file():
                    continue
                rel = path.relative_to(ROOT).as_posix()
                target = FS / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                files.append(rel)
    for pkg in ("src/sdlc", "src/sdlc/agents", "src/internal"):
        init = f"{pkg}/__init__.py"
        if init not in files:
            (FS / init).parent.mkdir(parents=True, exist_ok=True)
            (FS / init).write_text("", encoding="utf-8")
            files.append(init)
    (FS / "manifest.json").write_text(json.dumps({"files": files}, indent=1), encoding="utf-8")

    web = ROOT / "src" / "sdlc" / "web"
    html = (web / "index.html").read_text(encoding="utf-8").replace("/*__THEME__*/", (web / "theme.css").read_text(encoding="utf-8"), 1)
    # The bridge must install its fetch interceptor before the console script runs.
    stamp = int(time.time())
    html = html.replace("<title>ACE Ops Delivery</title>", f"<title>ACE Ops Delivery · in your browser</title>\n  <script src=\"bridge.js?v={stamp}\"></script>", 1)
    # The console's CSP forbids external scripts; the browser build needs the Pyodide CDN.
    html = html.replace(
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'",
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; connect-src 'self' https://cdn.jsdelivr.net; img-src data:; worker-src blob:; base-uri 'none'; form-action 'none'",
        1,
    )
    (OUT / "index.html").write_text(html, encoding="utf-8")
    shutil.copy2(ROOT / "scripts" / "site" / "bridge.js", OUT / "bridge.js")
    total = sum((FS / f).stat().st_size for f in files)
    print(f"docs/app built: {len(files)} files, {total / 1e6:.1f} MB in fs/, page {len(html) // 1000} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
