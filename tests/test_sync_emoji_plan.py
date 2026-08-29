from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from wggbot.emoji_admin import EmojiAdminError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_emoji_plan.py"
SPEC = importlib.util.spec_from_file_location("sync_emoji_plan", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
preflight_live_state = MODULE.preflight_live_state
verify_final_state = MODULE.verify_final_state


def plan() -> dict[str, Any]:
    return {
        "renames": [
            {
                "id": "123456789012345678",
                "from": "old_name",
                "to": "group_new_name",
                "animated": False,
            }
        ],
        "uploads": [{"name": "group_upload", "animated": True}],
        "expected_after": {"total": 2, "static": 1, "animated": 1},
    }


def live(emoji_id: str, name: str, *, animated: bool = False) -> dict[str, Any]:
    return {"id": emoji_id, "name": name, "animated": animated}


def test_preflight_reports_remaining_work_and_accepts_partial_resume() -> None:
    renames, uploads = preflight_live_state(plan(), [live("123456789012345678", "old_name")], 50)
    assert [entry["to"] for entry in renames] == ["group_new_name"]
    assert [entry["name"] for entry in uploads] == ["group_upload"]

    renames, uploads = preflight_live_state(
        plan(),
        [
            live("123456789012345678", "group_new_name"),
            live("234567890123456789", "group_upload", animated=True),
        ],
        50,
    )
    assert renames == []
    assert uploads == []


def test_preflight_rejects_live_drift_and_capacity_overflow() -> None:
    with pytest.raises(EmojiAdminError, match="outside the reviewed plan"):
        preflight_live_state(
            plan(),
            [
                live("123456789012345678", "old_name"),
                live("999999999999999999", "surprise"),
            ],
            50,
        )

    with pytest.raises(EmojiAdminError, match="exceeds Discord"):
        preflight_live_state(plan(), [live("123456789012345678", "old_name")], 0)


def test_verify_final_state_checks_names_ids_types_and_counts() -> None:
    final = [
        live("123456789012345678", "group_new_name"),
        live("234567890123456789", "group_upload", animated=True),
    ]
    verify_final_state(plan(), final)

    with pytest.raises(EmojiAdminError, match="Final live names differ"):
        verify_final_state(plan(), final[:1])

    wrong_id = [
        live("999999999999999999", "group_new_name"),
        live("234567890123456789", "group_upload", animated=True),
    ]
    with pytest.raises(EmojiAdminError, match="does not have final name"):
        verify_final_state(plan(), wrong_id)
