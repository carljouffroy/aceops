# Demo video pipeline

| File | Made by | What it is |
|---|---|---|
| `docs/pitch/product-demo.mp4` + `.segments.json` | `record_product.py` | the full tour, ~3.9 min, headless console at 1600x900 |
| `docs/pitch/product-demo-60s.mp4` + `.segments.json` | `record_product.py --cut 60s` | the same tour, ~70 s |
| `docs/pitch/aceops-demo.mp4` | `compose.sh` | full product + presenters in a circle + their audio |
| `docs/pitch/aceops-demo-final.mp4` | `assemble.sh` | GB10 clip, then the 60 s product cut, presenters' circle over both |

Everything runs on this Mac with `uv`, Playwright (Chromium) and `/opt/homebrew/bin/ffmpeg`.

## 1. Record the product

```sh
uv run --with playwright python scripts/demo_video/record_product.py            # full, docs/pitch/product-demo.mp4
uv run --with playwright python scripts/demo_video/record_product.py --cut 60s  # short, docs/pitch/product-demo-60s.mp4
```

It starts its own console on `:8794` (never `:8792`, which a person may be using) on a
**private copy** of the Northline sample workspace (`scripts/demo_video/out/workspace/`,
via `isolated_console.py`), resets the demo, clicks **Tour**, and walks the 12 steps.
It prints a segment table and ends with `OK <duration>s` or `FAILED <reason>`; a step that
fails is screenshotted to `scripts/demo_video/out/` and skipped so the recording still finishes.

- **full**: narration dwell first (14, 10, 10, 14, 12, 8, 16, 10, 12, 16, 20, 10 s), then
  "Do it for me", then "Next →". The click lands at the *end* of each segment. The Autopilot
  step holds 15 s so the agents visibly run.
- **60s**: "Do it for me" lands *first*, then a short dwell (0, 6, 6, 7, 7, 5, 8, 6, 6, 7, 8, 0 s)
  with the result on screen, then "Next →". Steps 1 and 12 are passed immediately.

Flags: `--headed` to watch Chromium, `--speed 2` for a quick rehearsal (halves every dwell),
`--shared-workspace` to run the literal `python -m sdlc --source sample` on `data/sample_out`.
If Playwright complains about a missing browser: `uv run --with playwright playwright install chromium`.

## 2. Record the camera take

- One continuous take, 1080p (or 4K); landscape or portrait both work. The composers crop a
  centred square for the circle, so keep the speakers in the middle of the frame. Phone or
  QuickTime (File > New Movie Recording) is fine. Good audio matters more than the picture.
- Read `docs/pitch/demo-script.md`; each step there is one tour step. Keep the timing close
  to the segments file of the cut you are recording against. Print the table first:

  ```sh
  python3 -c 'import json,sys; [print(f"{s[\"step\"]:>2}  {s[\"start\"]:6.1f}s  {s[\"end\"]:6.1f}s  {s[\"title\"]}") for s in json.load(open(sys.argv[1]))]' docs/pitch/product-demo-60s.segments.json
  ```

  `start`/`end` are seconds on the product video's clock. In the full cut the on-screen click
  lands near the *end* of each segment, so say the "click" line late. In the 60 s cut the click
  lands at the *start* of each segment, so talk over the result.
- Play the product video on a second screen (muted) while you record, so the voices stay in step.

## 3a. Compose: product full-frame + presenters (3-minute version)

```sh
scripts/demo_video/compose.sh CAMERA.mp4                                   # -> docs/pitch/aceops-demo.mp4
scripts/demo_video/compose.sh CAMERA.mp4 docs/pitch/product-demo.mp4 OUT.mp4 [OFFSET]
```

The output uses the camera take's audio and length. A longer camera take holds the product's
last frame; a shorter one cuts the product. `OFFSET` (fourth argument or env var) delays the
product by that many seconds when the presenters start talking before the screen should move.

## 3b. Assemble: GB10 clip, then the 60 s product, presenters over both (final version)

```sh
scripts/demo_video/assemble.sh GB10.mp4 CAMERA.mp4 [OUT.mp4]               # -> docs/pitch/aceops-demo-final.mp4
```

- `GB10.mp4` (a teammate's clip of the box, portrait phone video is fine) plays first, full
  length, with **its own audio**, fitted on a blurred fill of itself.
- `docs/pitch/product-demo-60s.mp4` plays second (`PRODUCT=path` to use another cut).
- `CAMERA.mp4` (the two presenters) is the bottom-left circle over **both** segments from t=0;
  its audio is used over the product segment. `VOICE_OVER_GB10=1` uses the camera audio over
  the GB10 clip as well. `OFFSET=seconds` shifts the camera (picture and sound) later.
- The segments are joined with the `concat` filter, so the three sources may differ in size,
  frame rate and codec. The script prints every input's duration and the output's.

So for the final video the presenters record **one** take: the GB10 intro (~length of the clip)
followed straight away by the 60 s script, and the camera take's clock is the final video's clock.

### If the voices and the screen drift

Play the result. If the presenters are *late* (the screen moves before they get to that line),
there is no knob: shorten the lines or re-record. If they are *early* (talking before the screen
should move), shift the camera / product with `OFFSET`:

```sh
OFFSET=2.5 scripts/demo_video/assemble.sh GB10.mp4 CAMERA.mp4
OFFSET=4.5 scripts/demo_video/compose.sh CAMERA.mp4
```

The dwells are fixed in `record_product.py` (`CUTS`); changing them means re-recording the product.

## Test without real footage

```sh
# a fake camera take (10 s), a fake portrait GB10 clip (10 s), a fake landscape camera take (15 s)
ffmpeg -y -f lavfi -i testsrc=size=1280x720:rate=30   -f lavfi -i sine=frequency=440:sample_rate=48000 -t 10 -c:v libx264 -pix_fmt yuv420p -c:a aac scripts/demo_video/out/cam-test.mp4
ffmpeg -y -f lavfi -i testsrc=size=1080x1920:rate=30  -f lavfi -i sine=frequency=300:sample_rate=48000 -t 10 -c:v libx264 -pix_fmt yuv420p -c:a aac scripts/demo_video/out/gb10-test.mp4
ffmpeg -y -f lavfi -i testsrc2=size=1280x720:rate=30  -f lavfi -i sine=frequency=600:sample_rate=48000 -t 15 -c:v libx264 -pix_fmt yuv420p -c:a aac scripts/demo_video/out/cam2-test.mp4

scripts/demo_video/compose.sh  scripts/demo_video/out/cam-test.mp4 docs/pitch/product-demo.mp4 scripts/demo_video/out/compose-test.mp4
scripts/demo_video/assemble.sh scripts/demo_video/out/gb10-test.mp4 scripts/demo_video/out/cam2-test.mp4 scripts/demo_video/out/assemble-test.mp4
```
