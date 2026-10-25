"""Loopback board. The page shell has no client text; the browser inserts that as text."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from board.store import DataError, default_root, load_board, set_status

PAGE = (Path(__file__).with_name("index.html")).read_text(encoding="utf-8")
NO_STORE = {"Cache-Control": "no-store"}


class StatusUpdate(BaseModel):
    status: Literal["To do", "In progress", "Blocked", "Done"]


def create_app(root: Path | None = None) -> FastAPI:
    data_root = (root or default_root()).resolve()
    app = FastAPI(title="ACE Ops board", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(PAGE, headers=NO_STORE)

    @app.get("/api/board")
    def board() -> dict:
        try:
            return load_board(data_root)
        except DataError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.patch("/api/items/{item_id}")
    def patch_item(item_id: str, body: StatusUpdate) -> dict:
        try:
            return set_status(data_root, item_id, body.status)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown work item") from exc
        except DataError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app


app = create_app()
