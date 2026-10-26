#!/usr/bin/env python3
"""Record the ACE Ops console tour as an MP4 under docs/pitch/.

    uv run --with playwright python scripts/demo_video/record_product.py [--cut full|60s]
        [--headed] [--shared-workspace] [--speed 1.0]

Cuts
  full  docs/pitch/product-demo.mp4      (+ product-demo.segments.json)      ~3.9 min
        narration dwell first, then "Do it for me", then "Next →"; the Autopilot
        step holds 15 s so the agents visibly run.
  60s   docs/pitch/product-demo-60s.mp4  (+ product-demo-60s.segments.json)  ~70 s
        "Do it for me" lands first, the result is on screen during the (short)
        dwell, then "Next →"; step 1 and step 12 are passed immediately.

What it does
  1. Starts its own console on :8794 (MCP port :8793, never :8792) from the repo
     root, on a private copy of the Northline sample workspace (see
     isolated_console.py), and waits for /api/state.
  2. Switches autopilot off and resets the demo through the API.
  3. Opens the console in headless Chromium (1600x900, dark), recording video,
     clicks Tour, and drives the 12 steps, scrolling the ticket drawer / the Data
     room page so the screen moves while a voice would be talking.
  4. Writes the segments file (start/end of every step on the video's clock),
     converts the webm to H.264 MP4, deletes the webm, prints the segment table and
     a final "OK <duration>s" or "FAILED <reason>" line.

Failures inside a step are screenshotted to scripts/demo_video/out/ and the tour
is skipped forward so the recording still completes. The console is always
stopped at the end, even on error, and a watchdog kills the browser if Playwright's
shutdown stalls (the video file is already complete by then).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT_DIR = HERE / "out"
PITCH_DIR = ROOT / "docs" / "pitch"

CONSOLE_PORT = 8794
MCP_PORT = 8793
BASE_URL = f"http://127.0.0.1:{CONSOLE_PORT}"
API_HEADERS = {"Content-Type": "application/json", "X-ACE-Console": "1"}

FFMPEG = os.environ.get("FFMPEG") or (shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg")
FFPROBE = os.environ.get("FFPROBE") or (shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe")

VIEWPORT = {"width": 1600, "height": 900}
STEP_COUNT = 12
DRAWER_STEPS = {3, 4, 5, 6, 7}   # the ticket drawer is open: scroll it ~600px down and back
DATA_ROOM_STEP = 10              # scroll the page 500px down and back
AUTOPILOT_STEP = 11              # agents run after "Do it for me"
CONSOLE_READY_TIMEOUT_S = 120.0
SHUTDOWN_TIMEOUT_S = 25.0        # watchdog for Playwright's close sequence

# Per-cut profile. dwell = narration seconds per step (12 steps, in tour order).
CUTS: dict[str, dict] = {
    "full": {
        "mp4": "product-demo.mp4",
        "segments": "product-demo.segments.json",
        "dwell": [14, 10, 10, 14, 12, 8, 16, 10, 12, 16, 20, 10],
        "order": "dwell_then_act",   # narrate, then the click lands at the end of the segment
        "autopilot_hold": 15.0,      # after autopilot is on, before Next
        "settle": 2.0,               # show a step's result before Next
        "tail": 3.0,                 # after Finish
        "advance_timeout": 20.0,     # wait for "Next →" after "Do it for me"
        "skip_when_pending": False,  # on timeout: fail the step (and skip) vs. just skip
    },
    "60s": {
        "mp4": "product-demo-60s.mp4",
        "segments": "product-demo-60s.segments.json",
        "dwell": [0, 6, 6, 7, 7, 5, 8, 6, 6, 7, 8, 0],
        "order": "act_then_dwell",   # the click lands first; the result is on screen while you talk
        "autopilot_hold": 0.0,
        "settle": 0.3,
        "tail": 1.5,
        "advance_timeout": 4.0,
        "skip_when_pending": True,   # e.g. autopilot's 3rd run is not in yet: skip ahead, not a failure
    },
}

ADVANCE_RE = re.compile(r"^\s*(Next\s*→|Finish)\s*$")


def log(msg: str) -> None:
    print(f"[record] {msg}", flush=True)


# ---------------------------------------------------------------- console


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


class ConsoleProcess:
    """The sdlc console as a child process group, killed on exit whatever happens."""

    def __init__(self, shared_workspace: bool):
        self.shared_workspace = shared_workspace
        self.proc: subprocess.Popen | None = None
        self.log_path = OUT_DIR / "console.log"
        self._log_file = None

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc is not None else None

    def start(self) -> None:
        if port_in_use(CONSOLE_PORT):
            raise RuntimeError(f"port {CONSOLE_PORT} is already in use; stop that process or change CONSOLE_PORT")
        env = {
            **os.environ,
            "SDLC_CONSOLE_PORT": str(CONSOLE_PORT),
            "SDLC_MCP_PORT": str(MCP_PORT),
            "PYTHONPATH": "src",
            "PYTHONUNBUFFERED": "1",
        }
        env.pop("SDLC_AUTOPILOT", None)  # the tour switches autopilot on itself, at step 11
        if self.shared_workspace:
            cmd = ["uv", "run", "python", "-m", "sdlc", "--source", "sample", "--no-mcp"]
        else:
            cmd = ["uv", "run", "python", str(HERE / "isolated_console.py"), "--fresh", "--", "--source", "sample", "--no-mcp"]
        self._log_file = open(self.log_path, "w", encoding="utf-8")
        log("starting console: " + " ".join(cmd))
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), env=env, stdout=self._log_file, stderr=subprocess.STDOUT, start_new_session=True
        )

    def wait_ready(self, timeout: float = CONSOLE_READY_TIMEOUT_S) -> None:
        deadline = time.monotonic() + timeout
        last = "not up yet"
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise RuntimeError(f"console exited early (code {self.proc.returncode}); see {self.log_path}:\n{self.log_tail()}")
            try:
                state = api("GET", "/api/state", timeout=3)
                if isinstance(state, dict) and "specs" in state:
                    log(f"console ready: source {state.get('source')}, {len(state.get('specs', []))} specs, agent mode {state.get('agent', {}).get('mode')}")
                    return
            except Exception as exc:  # noqa: BLE001 - keep polling until the deadline
                last = str(exc)
            time.sleep(0.4)
        raise RuntimeError(f"console did not answer on {BASE_URL} within {timeout:.0f}s: {last}\n{self.log_tail()}")

    def log_tail(self, lines: int = 15) -> str:
        try:
            return "\n".join(self.log_path.read_text(encoding="utf-8").splitlines()[-lines:])
        except OSError:
            return ""

    def stop(self) -> None:
        proc = self.proc
        if proc is None:
            return
        self.proc = None
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log("console did not die; leaving it")
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        log("console stopped")


def api(method: str, path: str, body: dict | None = None, timeout: float = 15):
    data = None
    if method != "GET":
        data = json.dumps(body if body is not None else {}).encode("utf-8")
    request = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=API_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def reset_demo() -> None:
    try:
        api("POST", "/api/autopilot", {"actor": "Avery Park", "on": False})
    except urllib.error.HTTPError as exc:
        log(f"autopilot off: HTTP {exc.code} (already off?)")
    state = api("POST", "/api/reset", {})
    log(f"demo reset: {len(state.get('specs', []))} specs, {len(state.get('tickets', []))} tickets, autopilot {state.get('autopilot')}")


def child_pids(pid: int) -> list[int]:
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
    return [int(x) for x in out if x.isdigit()]


def kill_browser_tree(protect_pid: int | None) -> None:
    """Watchdog: kill every descendant of this process except the console's subtree."""
    victims: list[int] = []
    stack = [os.getpid()]
    while stack:
        for child in child_pids(stack.pop()):
            if child == protect_pid:
                continue
            victims.append(child)
            stack.append(child)
    log(f"shutdown watchdog fired; killing {len(victims)} browser/driver process(es)")
    for pid in reversed(victims):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


# ---------------------------------------------------------------- recording


class TourRecorder:
    def __init__(self, page, t0: float, cut: dict, speed: float):
        self.page = page
        self.t0 = t0
        self.cut = cut
        self.speed = speed
        self.segments: list[dict] = []
        self.failures: list[tuple[int, str]] = []

    # time helpers
    def clock(self) -> float:
        return round(time.monotonic() - self.t0, 2)

    def pause(self, seconds: float) -> None:
        if seconds > 0:
            self.page.wait_for_timeout(seconds * 1000 / self.speed)

    # panel helpers
    @property
    def panel(self):
        return self.page.locator("#tour-panel")

    def wait_for_step(self, n: int, timeout_s: float = 20.0) -> None:
        self.page.wait_for_function(
            "(n) => { const p = document.getElementById('tour-panel'); if (!p || p.hidden) return false;"
            " const t = p.querySelector('.tour-n'); return !!t && t.textContent.trim() === `Step ${n} of 12`; }",
            arg=n,
            timeout=timeout_s * 1000,
        )

    def step_title(self) -> str:
        try:
            return self.panel.locator("h4").first.inner_text(timeout=3000).strip()
        except Exception:  # noqa: BLE001
            return "step"

    def advance_button(self):
        return self.panel.get_by_role("button", name=ADVANCE_RE)

    def do_it_button(self):
        return self.panel.get_by_role("button", name=re.compile(r"Do it for me"))

    def click_do_it(self, n: int) -> None:
        do_it = self.do_it_button().first
        if do_it.is_visible():
            do_it.click()
            log(f"step {n:2d}  clicked 'Do it for me'")

    def wait_for_advance(self, timeout_s: float) -> bool:
        try:
            self.advance_button().first.wait_for(state="visible", timeout=timeout_s * 1000)
            return True
        except Exception:  # noqa: BLE001 - PlaywrightTimeoutError
            return False

    def click_advance(self, n: int) -> None:
        adv = self.advance_button().first
        label = "Finish" if n == STEP_COUNT else "Next →"
        adv.click()
        log(f"step {n:2d}  clicked '{label}'")

    def click_skip(self, n: int) -> None:
        self.panel.locator(".tour-skip").first.click()
        log(f"step {n:2d}  clicked 'skip' (step result still pending)")

    # visuals
    def smooth_scroll(self, selector: str | None, distance: int, budget_s: float) -> None:
        """Scroll an element (or the page) to `distance` and back, spread over budget_s seconds."""
        steps = 24
        down_s = up_s = budget_s * 0.4
        hold_s = budget_s * 0.2
        js = (
            "([sel, y]) => { const el = sel ? document.querySelector(sel) : document.scrollingElement;"
            " if (el) el.scrollTop = y; }"
        )
        for k in range(1, steps + 1):
            self.page.evaluate(js, [selector, distance * k / steps])
            self.pause(down_s / steps)
        self.pause(hold_s)
        for k in range(steps - 1, -1, -1):
            self.page.evaluate(js, [selector, distance * k / steps])
            self.pause(up_s / steps)

    def dwell(self, n: int, seconds: float) -> None:
        if seconds <= 0:
            return
        end = time.monotonic() + seconds / self.speed
        if n in DRAWER_STEPS or n == DATA_ROOM_STEP:
            lead = min(2.5, seconds * 0.25)
            self.pause(lead)
            budget = max(2.0, seconds - lead - 1.0)
            if n in DRAWER_STEPS:
                try:
                    self.page.wait_for_selector("#drawer.on .d-body", timeout=3000)
                except Exception:  # noqa: BLE001 - no drawer: nothing to scroll
                    pass
                self.smooth_scroll("#drawer .d-body", 600, budget)
            else:
                self.smooth_scroll(None, 500, budget)
        remaining = end - time.monotonic()
        if remaining > 0:
            self.page.wait_for_timeout(remaining * 1000)

    def screenshot(self, name: str) -> None:
        try:
            self.page.screenshot(path=str(OUT_DIR / name), full_page=False)
            log(f"screenshot {OUT_DIR / name}")
        except Exception as exc:  # noqa: BLE001
            log(f"screenshot failed: {exc}")

    # one step
    def run_step(self, n: int) -> None:
        cut = self.cut
        start = self.clock()
        title = ""
        ok = True
        error = None
        note = None
        try:
            self.wait_for_step(n)
            title = self.step_title()
            log(f"step {n:2d} @ {start:6.1f}s  {title}")
            dwell_s = cut["dwell"][n - 1]
            if cut["order"] == "act_then_dwell":
                self.click_do_it(n)
                self.dwell(n, dwell_s)
            else:
                self.dwell(n, dwell_s)
                self.click_do_it(n)
            if self.wait_for_advance(cut["advance_timeout"]):
                if n == AUTOPILOT_STEP and cut["autopilot_hold"] > 0:
                    log(f"step {n:2d}  autopilot on, holding {cut['autopilot_hold']:.0f}s so the agents run")
                    self.pause(cut["autopilot_hold"])
                else:
                    self.pause(cut["settle"])
                self.click_advance(n)
            elif cut["skip_when_pending"]:
                note = "advanced via skip"
                self.click_skip(n)
            else:
                raise TimeoutError(f"'Next →' did not appear within {cut['advance_timeout']:.0f}s")
        except Exception as exc:  # noqa: BLE001 - record, screenshot, skip forward
            ok = False
            error = f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}".strip()
            self.failures.append((n, error))
            log(f"step {n:2d}  FAILED: {error}")
            self.screenshot(f"step-{n:02d}-failed.png")
            self.skip_forward(n)
        end = self.clock()
        seg = {"step": n, "title": title, "start": start, "end": end, "ok": ok}
        if note:
            seg["note"] = note
        if error:
            seg["error"] = error
        self.segments.append(seg)

    def skip_forward(self, n: int) -> None:
        """Best effort: advance the tour so the next step can still be recorded."""
        try:
            adv = self.advance_button().first
            if adv.is_visible():
                adv.click()
                return
            skip = self.panel.locator(".tour-skip").first
            if skip.is_visible():
                skip.click()
                return
            # Last resort: the tour keeps its step in localStorage; move it on and reload.
            self.page.evaluate("(i) => localStorage.setItem('aceops.tour', String(i))", n)  # 0-based index of the next step
            self.page.reload(wait_until="domcontentloaded")
        except Exception as exc:  # noqa: BLE001
            log(f"skip forward failed on step {n}: {exc}")

    def start_tour(self) -> None:
        page = self.page
        page.wait_for_selector(".spec", timeout=45000)
        self.pause(1.5)
        page.click("#tour")
        page.wait_for_function(
            "() => { const p = document.getElementById('tour-panel'); const m = document.getElementById('modal');"
            " return (p && !p.hidden) || (m && m.classList.contains('on')); }",
            timeout=10000,
        )
        if page.locator("#modal.on").count():
            btn = page.locator("#modal.on button", has_text=re.compile(r"^\s*Reset and start"))
            if btn.count():
                log("tour asked to reset first; clicking 'Reset and start'")
                btn.first.click()
            page.wait_for_function("() => { const p = document.getElementById('tour-panel'); return p && !p.hidden; }", timeout=20000)


def newest_webm(video_dir: Path) -> Path | None:
    files = sorted(video_dir.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def run_recording(cut: dict, headed: bool, speed: float, protect_pid: int | None) -> tuple[Path, list[dict], list[tuple[int, str]]]:
    from playwright.sync_api import sync_playwright

    video_dir = OUT_DIR / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    for stale in video_dir.glob("*.webm"):
        stale.unlink(missing_ok=True)

    pw = sync_playwright().start()
    browser = context = page = None
    recorder = None
    try:
        browser = pw.chromium.launch(headless=not headed)
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=1,
            color_scheme="dark",
            record_video_dir=str(video_dir),
            record_video_size=VIEWPORT,
        )
        page = context.new_page()
        t0 = time.monotonic()  # the video's clock starts with the page
        recorder = TourRecorder(page, t0, cut, speed)
        page.goto(BASE_URL + "/", wait_until="domcontentloaded", timeout=30000)
        recorder.start_tour()
        for n in range(1, STEP_COUNT + 1):
            recorder.run_step(n)
        recorder.pause(cut["tail"])
    except Exception:
        if recorder is not None:
            recorder.screenshot("fatal.png")
        raise
    finally:
        # Close the page first: that finalizes the webm. Then tear the rest down under a
        # watchdog, because context/browser close has been seen to stall after a long run.
        watchdog = threading.Timer(SHUTDOWN_TIMEOUT_S, kill_browser_tree, args=(protect_pid,))
        watchdog.daemon = True
        watchdog.start()
        for name, obj in (("page", page), ("context", context), ("browser", browser)):
            if obj is None:
                continue
            try:
                obj.close()
            except Exception as exc:  # noqa: BLE001
                log(f"{name} close: {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}")
        try:
            pw.stop()
        except Exception as exc:  # noqa: BLE001
            log(f"playwright stop: {type(exc).__name__}")
        watchdog.cancel()
    webm = newest_webm(video_dir)
    if webm is None or not webm.is_file():
        raise RuntimeError("Playwright produced no video file")
    assert recorder is not None
    return webm, recorder.segments, recorder.failures


# ---------------------------------------------------------------- encoding


def ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def encode_mp4(webm: Path, mp4: Path) -> None:
    mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(webm),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-r", "30", "-movflags", "+faststart",
        "-an", str(mp4),
    ]
    log("encoding: " + " ".join(cmd))
    subprocess.run(cmd, check=True)


def print_segments(segments: list[dict]) -> None:
    print()
    print(f"{'step':>4}  {'start':>7}  {'end':>7}  {'len':>5}  title")
    for seg in segments:
        length = seg["end"] - seg["start"]
        flag = ""
        if not seg.get("ok", True):
            flag = "   <-- FAILED: " + seg.get("error", "")
        elif seg.get("note"):
            flag = "   (" + seg["note"] + ")"
        print(f"{seg['step']:>4}  {seg['start']:>7.1f}  {seg['end']:>7.1f}  {length:>5.1f}  {seg['title']}{flag}")
    print()


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record the ACE Ops console tour to docs/pitch/")
    parser.add_argument("--cut", choices=sorted(CUTS), default="full", help="which cut to record (default full)")
    parser.add_argument("--headed", action="store_true", help="show the browser window while recording")
    parser.add_argument("--shared-workspace", action="store_true",
                        help="run the literal `python -m sdlc --source sample` (shares data/sample_out with any console on :8792)")
    parser.add_argument("--speed", type=float, default=1.0, help="divide every dwell by this factor (rehearsals only)")
    args = parser.parse_args(argv)
    cut = CUTS[args.cut]
    mp4_path = PITCH_DIR / cut["mp4"]
    segments_path = PITCH_DIR / cut["segments"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    console = ConsoleProcess(shared_workspace=args.shared_workspace)
    try:
        console.start()
        console.wait_ready()
        reset_demo()
        webm, segments, failures = run_recording(cut, headed=args.headed, speed=args.speed, protect_pid=console.pid)
        segments_path.parent.mkdir(parents=True, exist_ok=True)
        segments_path.write_text(json.dumps(segments, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        log(f"segments written to {segments_path}")
        encode_mp4(webm, mp4_path)
        duration = ffprobe_duration(mp4_path)
        webm.unlink(missing_ok=True)
        print_segments(segments)
        for n, err in failures:
            print(f"WARN step {n} failed: {err}")
        print(f"video {mp4_path} ({duration:.1f}s)")
        print(f"OK {duration:.1f}s")
        return 0
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        print(f"FAILED {type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}")
        return 1
    finally:
        try:
            if console.proc is not None and console.proc.poll() is None:
                api("POST", "/api/autopilot", {"actor": "Avery Park", "on": False}, timeout=5)
        except Exception:  # noqa: BLE001 - best effort
            pass
        console.stop()


if __name__ == "__main__":
    raise SystemExit(main())
