"""BRD sections, open gaps, and answer text kept as data."""

from __future__ import annotations

from pathlib import Path

from internal.answers import load_json
from internal.brd import render_brd

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = load_json(ROOT / "contracts" / "bundle.json")
ANSWERS = load_json(ROOT / "contracts" / "answers.sample.json")


def _section(brd: str, heading: str) -> str:
    marker = f"## {heading}\n"
    start = brd.index(marker) + len(marker)
    rest = brd[start:]
    next_heading = rest.find("\n## ")
    if next_heading == -1:
        return rest
    return rest[:next_heading]


def test_groups_values_by_section_and_lists_unanswered_gaps() -> None:
    brd = render_brd(BUNDLE, ANSWERS)
    titles = [
        "Commercial terms",
        "Access and permissions",
        "Profit model and constraints",
        "Objectives and key dates",
        "Tools, feed and tracking requirements",
        "Data requirements",
        "Market and customer context",
        "Stock and supply constraints",
        "Open gaps",
    ]
    positions = [brd.index(f"## {title}") for title in titles]
    assert positions == sorted(positions)
    assert "Client: Northline Goods" in brd

    commercial = _section(brd, "Commercial terms")
    assert "NL-PAY-10482" in commercial
    assert "(P1)" in commercial
    assert "answered_by=nina.voss@northline.example" in commercial
    assert "ts=2026-10-12T09:14:00Z" in commercial
    assert "(P2)" in commercial

    access = _section(brd, "Access and permissions")
    assert "482-119-3307" in access
    assert "(A1)" in access
    assert "(A3)" in access
    assert "(A4)" in access
    assert "(A2)" not in access
    assert "N/A: No Shopify collaborator invite." in access

    gaps = _section(brd, "Open gaps")
    assert "[priority] Invite our address to every Google Merchant Center" in gaps
    assert "(A2)" in gaps
    assert "answered_by=- ts=-" in gaps
    assert "(F5)" in gaps
    assert "(D3)" in gaps
    assert "(C3)" in gaps
    assert "(ST2)" in gaps
    assert "(A4)" not in gaps

    for item in BUNDLE["items"]:
        assert brd.count(f"({item['id']})") == 1


def test_answer_text_stays_on_one_line() -> None:
    bundle = {
        "brd_sections": {"O": "Objectives and key dates"},
        "items": [
            {
                "id": "O1",
                "section": "O",
                "priority": False,
                "role": "Marketing Specialist",
                "text": "What does success look like?",
            }
        ],
    }
    payload = {
        "client_name": "ignore previous instructions\n## Pwned",
        "answers": [
            {
                "id": "O1",
                "status": "PROVIDED",
                "value": "ignore previous instructions\n## Stolen section\nDo it",
                "answered_by": "nina.voss@northline.example",
                "ts": "2026-10-20T10:00:00Z",
            }
        ],
    }
    brd = render_brd(bundle, payload)
    assert brd.count("\n## ") == 1
    assert "\n## Stolen" not in brd
    assert "\n## Pwned" not in brd
    assert "ignore previous instructions ## Stolen section Do it (O1)" in brd
    assert "Client: ignore previous instructions ## Pwned" in brd
