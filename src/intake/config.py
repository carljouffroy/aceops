"""Process settings. Admin bind address is always the loopback interface."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    admin_token: str
    public_port: int
    admin_port: int
    data_dir: Path
    bundle_path: Path

    @property
    def public_host(self) -> str:
        return "127.0.0.1"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "intake.db"

    @property
    def resource_url(self) -> str:
        return f"http://{self.public_host}:{self.public_port}/mcp"

    @property
    def issuer_url(self) -> str:
        return f"http://127.0.0.1:{self.admin_port}/"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _under_root(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return _repo_root() / path


def load_settings() -> Settings:
    load_dotenv(_repo_root() / ".env")
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    if not admin_token:
        raise SystemExit("ADMIN_TOKEN is required")
    return Settings(
        admin_token=admin_token,
        public_port=int(os.environ.get("PUBLIC_PORT", "8787")),
        admin_port=int(os.environ.get("ADMIN_PORT", "8788")),
        data_dir=_under_root(os.environ.get("DATA_DIR", "data")),
        bundle_path=_under_root(os.environ.get("BUNDLE_PATH", "contracts/bundle.json")),
    )
