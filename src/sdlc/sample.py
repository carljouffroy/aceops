"""Build data/sample_out from contracts/answers.sample.json with the team's own BRD + dispatch."""

from __future__ import annotations

import contextlib
import io

from sdlc.config import CONTRACTS, SOURCES


def ensure_sample(force: bool = False) -> bool:
    out = SOURCES["sample"]
    if not force and (out / "work_items.json").is_file():
        return False
    from internal.run import main as internal_main  # the team's pipeline, unchanged

    with contextlib.redirect_stdout(io.StringIO()):
        code = internal_main(["--answers", str(CONTRACTS / "answers.sample.json"), "--out", str(out), "--no-polish"])
    return code == 0
