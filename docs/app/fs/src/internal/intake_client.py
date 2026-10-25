"""Client for the intake admin API. Answer text is never sent back as a command."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from internal.answers import index_answers

DEFAULT_ADMIN_URL = "http://127.0.0.1:8788"


class IntakeAdminError(Exception):
    def __init__(self, message: str, *, unreachable: bool = False, url: str = "") -> None:
        super().__init__(message)
        self.unreachable = unreachable
        self.url = url


class IntakeAdminClient:
    def __init__(self, base_url: str, token: str, client_id: str | None = None) -> None:
        self.base_url = base_url.rstrip("/") or DEFAULT_ADMIN_URL
        self.token = token
        self.client_id = client_id

    @classmethod
    def from_env(cls) -> IntakeAdminClient:
        _load_dotenv()
        base_url = os.environ.get("INTAKE_ADMIN_URL", "").strip() or DEFAULT_ADMIN_URL
        token = os.environ.get("ADMIN_TOKEN", "").strip()
        return cls(base_url, token)

    def create_client(self) -> dict[str, str]:
        body = self._request("POST", "/admin/clients")
        if not isinstance(body, dict) or not body.get("id"):
            raise IntakeAdminError("create_client returned no id", url=self.base_url)
        self.client_id = str(body["id"])
        token = body.get("invitation_token")
        return {
            "id": self.client_id,
            "invitation_token": "" if token is None else str(token),
        }

    def get_answers(self) -> list[dict]:
        """Latest answer per checklist item, with older rows on history."""
        rows = self._request(
            "GET",
            f"/admin/clients/{_quote(self._require_client())}/answers?history=true",
        )
        if not isinstance(rows, list):
            raise IntakeAdminError("answers response was not a list", url=self.base_url)
        return list(index_answers(rows).values())

    def get_events(self, since_cursor: int = 0) -> list[dict]:
        """Events with id greater than since_cursor.

        The admin route names that cursor `since`, not `since_cursor`.
        """
        cursor = int(since_cursor)
        path = (
            f"/admin/clients/{_quote(self._require_client())}/events"
            f"?since={cursor}"
        )
        rows = self._request("GET", path)
        if not isinstance(rows, list):
            raise IntakeAdminError("events response was not a list", url=self.base_url)
        selected = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                event_id = int(row.get("id"))
            except (TypeError, ValueError):
                continue
            if event_id > cursor:
                selected.append(row)
        return selected

    def _require_client(self) -> str:
        if not self.client_id:
            raise IntakeAdminError("No intake client id", url=self.base_url)
        return self.client_id

    def _request(self, method: str, path: str) -> Any:
        if not self.token:
            raise IntakeAdminError("ADMIN_TOKEN is not set", url=self.base_url)
        url = self.base_url + path
        request = urllib.request.Request(url, method=method)
        request.add_header("Accept", "application/json")
        request.add_header("Authorization", f"Bearer {self.token}")
        if method == "POST":
            request.data = b""
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise IntakeAdminError(
                f"admin API returned {exc.code}: {detail}",
                url=self.base_url,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise IntakeAdminError(str(exc), unreachable=True, url=self.base_url) from exc
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IntakeAdminError("admin API returned invalid JSON", url=self.base_url) from exc


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def _load_dotenv() -> None:
    seen: set[Path] = set()
    roots = [Path.cwd(), Path(__file__).resolve().parents[2]]
    for root in roots:
        path = (root / ".env").resolve()
        if path in seen:
            continue
        seen.add(path)
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = value.strip().strip("'").strip('"')
