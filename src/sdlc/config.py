"""SDLC settings: data sources, ports, demo team, and the local-only model check."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
BUNDLE_PATH = CONTRACTS / "bundle.json"
DEPENDENCIES_PATH = CONTRACTS / "sdlc" / "item_dependencies.json"

# live = what the intake pipeline writes; sample = the Northline sample answers run offline.
SOURCES = {
    "live": ROOT / "data" / "out",
    "sample": ROOT / "data" / "sample_out",
}

OWNER_ROLE = "Project owner"
DELIVERY_ROLES = ("Marketing Specialist", "Data Analyst", "Developer")

# Demo identities. Two people per delivery role so a reviewer can differ from the builder.
DEFAULT_TEAM = (
    {"name": "Avery Park", "role": OWNER_ROLE},
    {"name": "Jordan Lee", "role": "Data Analyst"},
    {"name": "Morgan Diaz", "role": "Data Analyst"},
    {"name": "Riley Chen", "role": "Marketing Specialist"},
    {"name": "Casey Brooks", "role": "Marketing Specialist"},
    {"name": "Sam Ortiz", "role": "Developer"},
    {"name": "Drew Kim", "role": "Developer"},
)

# Identities the autopilot pipeline acts under. They are not people and never appear in "Acting as".
AGENT_NAMES = ("Spec agent", "Dev agent", "Test agent", "Debug agent", "Deploy agent", "Status agent")

LOOPBACK_NAMES = {"localhost"}


def autopilot_default() -> bool:
    """SDLC_AUTOPILOT=1 starts new workspaces with the agents in charge of the gates."""
    return os.environ.get("SDLC_AUTOPILOT", "0").strip().lower() in ("1", "true", "on", "yes")


class LocalOnlyError(ValueError):
    """Raised when a model URL would leave this machine."""


@dataclass(frozen=True)
class ModelSettings:
    base_url: str
    model: str
    api_key: str


def console_port() -> int:
    return int(os.environ.get("SDLC_CONSOLE_PORT", "8792"))


def mcp_port() -> int:
    return int(os.environ.get("SDLC_MCP_PORT", "8791"))


def is_loopback_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if host.lower() in LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def model_settings() -> ModelSettings | None:
    """The optional local model, or None for rules only.

    Uses SDLC_LLM_* if set, else the internal agent's INTERNAL_LLM_*.
    Raises LocalOnlyError if the URL is not a loopback address.
    """
    base_url = (os.environ.get("SDLC_LLM_BASE_URL") or os.environ.get("INTERNAL_LLM_BASE_URL") or "").strip()
    model = (os.environ.get("SDLC_LLM_MODEL") or os.environ.get("INTERNAL_LLM_MODEL") or "").strip()
    if not base_url or not model:
        return None
    if not is_loopback_url(base_url):
        raise LocalOnlyError(
            f"Model URL {base_url!r} is not on this machine. "
            "The SDLC agent only talks to 127.0.0.1, ::1 or localhost."
        )
    api_key = (os.environ.get("SDLC_LLM_API_KEY") or os.environ.get("INTERNAL_LLM_API_KEY") or "").strip()
    return ModelSettings(base_url=base_url.rstrip("/"), model=model, api_key=api_key)


def load_dotenv(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from .env without overriding the environment."""
    env_path = path or ROOT / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")
