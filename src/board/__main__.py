"""Serve the work board on http://127.0.0.1:8790."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import uvicorn


def main() -> None:
    uvicorn.run("board.app:app", host="127.0.0.1", port=8790, log_level="info")


if __name__ == "__main__":
    main()
