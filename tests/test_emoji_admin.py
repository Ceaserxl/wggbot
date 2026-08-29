from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from wggbot.emoji_admin import (
    DiscordAPI,
    EmojiAdmin,
    EmojiAdminError,
    JsonObject,
    _collect_candidates,
    _image_data_uri,
    _load_backup,
    _resolve_emoji,
)

PNG = b"\x89PNG\r\n\x1a\nminimal-test-image"
GIF = b"GIF89aminimal-test-image"
GUILD_ID = "123456789012345678"
EMOJI_ID = "234567890123456789"


class FakeAPI:
    def __init__(self, emojis: list[JsonObject] | None = None):
        self.guilds: list[JsonObject] = [{"id": GUILD_ID, "name": "Test Guild"}]
        self.emojis = emojis or []
        self.assets = {str(emoji["id"]): PNG for emoji in self.emojis}
        self.events: list[tuple[Any, ...]] = []
        self.next_id = 900000000000000000

    async def list_guilds(self) -> list[JsonObject]:
        self.events.append(("list_guilds",))
        return self.guilds

    async def list_emojis(self, guild_id: str) -> list[JsonObject]:
        self.events.append(("list_emojis", guild_id))
        return [dict(emoji) for emoji in self.emojis]

    async def download_emoji(self, emoji: JsonObject) -> bytes:
        self.events.append(("download", str(emoji["id"])))
        return self.assets[str(emoji["id"])]

    async def create_emoji(
        self,
        guild_id: str,
        name: str,
        image: str,
        roles: list[str],
        reason: str,
    ) -> JsonObject:
        self.next_id += 1
        result: JsonObject = {"id": str(self.next_id), "name": name, "roles": roles}
        self.events.append(("create", guild_id, name, image, roles, reason))
        self.emojis.append(result)
        return result

    async def rename_emoji(
        self,
        guild_id: str,
        emoji_id: str,
        name: str,
        reason: str,
    ) -> JsonObject:
        self.events.append(("rename", guild_id, emoji_id, name, reason))
        return {"id": emoji_id, "name": name}

    async def delete_emoji(
        self,
        guild_id: str,
        emoji_id: str,
        reason: str,
    ) -> None:
        self.events.append(("delete", guild_id, emoji_id, reason))


def emoji(name: str = "party", emoji_id: str = EMOJI_ID, **extra: object) -> JsonObject:
    return {
        "id": emoji_id,
        "name": name,
        "animated": False,
        "available": True,
        "managed": False,
        "require_colons": True,
        "roles": [],
        **extra,
    }


def write_png(path: Path, data: bytes = PNG) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_collect_candidates_handles_numeric_prefixes_and_directories(tmp_path: Path) -> None:
    write_png(tmp_path / "120458-pepe-cross.png")
    (tmp_path / "animated.gif").write_bytes(GIF)
    (tmp_path / "ignore.txt").write_text("not an emoji", encoding="utf-8")

    candidates = _collect_candidates([tmp_path], None)

    assert [(name, path.name) for name, path in candidates] == [
        ("pepe_cross", "120458-pepe-cross.png"),
        ("animated", "animated.gif"),
    ]


def test_collect_candidates_rejects_duplicate_inferred_names(tmp_path: Path) -> None:
    write_png(tmp_path / "1-same.png")
    write_png(tmp_path / "2-same.png")

    with pytest.raises(EmojiAdminError, match="Multiple input files map"):
        _collect_candidates([tmp_path], None)


def test_image_data_uri_validates_signature_and_size(tmp_path: Path) -> None:
    valid = write_png(tmp_path / "valid.png")
    assert _image_data_uri(valid).startswith("data:image/png;base64,")

    invalid = write_png(tmp_path / "invalid.png", b"not a png")
    with pytest.raises(EmojiAdminError, match="contents do not match"):
        _image_data_uri(invalid)

    oversized = write_png(tmp_path / "large.png", PNG + b"x" * (256 * 1024))
    with pytest.raises(EmojiAdminError, match="256 KiB"):
        _image_data_uri(oversized)


@pytest.mark.asyncio
async def test_backup_writes_assets_and_versioned_hash_manifest(tmp_path: Path) -> None:
    api = FakeAPI([emoji()])
    admin = EmojiAdmin(api, tmp_path / "backups")

    backup = await admin.backup(GUILD_ID)
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema_version"] == 1
    assert manifest["guild"] == {"id": GUILD_ID, "name": "Test Guild"}
    assert manifest["emoji_count"] == 1
    entry = manifest["emojis"][0]
    assert entry["name"] == "party"
    assert entry["bytes"] == len(PNG)
    assert len(entry["sha256"]) == 64
    assert (backup / entry["asset"]).read_bytes() == PNG
    assert not list((tmp_path / "backups").glob("*/.partial-*"))
    assert admin.verify_backup(backup) == 1


@pytest.mark.asyncio
async def test_remove_is_dry_run_by_default(tmp_path: Path) -> None:
    api = FakeAPI([emoji()])
    admin = EmojiAdmin(api, tmp_path / "backups")

    await admin.remove(GUILD_ID, "party", apply=False, reason=None)

    assert not any(event[0] in {"download", "delete"} for event in api.events)


@pytest.mark.asyncio
async def test_remove_applied_backs_up_before_delete(tmp_path: Path) -> None:
    api = FakeAPI([emoji()])
    admin = EmojiAdmin(api, tmp_path / "backups")

    await admin.remove(GUILD_ID, EMOJI_ID, apply=True, reason="Owner requested cleanup")

    event_names = [event[0] for event in api.events]
    assert event_names.index("download") < event_names.index("delete")
    assert api.events[-1] == ("delete", GUILD_ID, EMOJI_ID, "Owner requested cleanup")
    assert len(list((tmp_path / "backups" / GUILD_ID).glob("*/manifest.json"))) == 1


@pytest.mark.asyncio
async def test_rename_rejects_collisions_without_mutation(tmp_path: Path) -> None:
    api = FakeAPI([emoji("old"), emoji("taken", "345678901234567890")])
    admin = EmojiAdmin(api, tmp_path / "backups")

    with pytest.raises(EmojiAdminError, match="already exists"):
        await admin.rename(GUILD_ID, "old", "taken", apply=True, reason="test")

    assert not any(event[0] in {"download", "rename"} for event in api.events)


@pytest.mark.asyncio
async def test_add_skips_existing_and_requires_reason_before_backup(tmp_path: Path) -> None:
    image = write_png(tmp_path / "new.png")
    api = FakeAPI([emoji("existing")])
    admin = EmojiAdmin(api, tmp_path / "backups")

    with pytest.raises(EmojiAdminError, match="--reason"):
        await admin.add(
            GUILD_ID,
            [("new", image)],
            [],
            apply=True,
            reason=None,
        )

    assert not any(event[0] in {"download", "create"} for event in api.events)


@pytest.mark.asyncio
async def test_restore_verifies_hash_and_blocks_cross_server(tmp_path: Path) -> None:
    source_api = FakeAPI([emoji()])
    backup = await EmojiAdmin(source_api, tmp_path / "backups").backup(GUILD_ID)
    destination_api = FakeAPI()
    admin = EmojiAdmin(destination_api, tmp_path / "safety")

    with pytest.raises(EmojiAdminError, match="belongs to guild"):
        await admin.restore(
            "999999999999999999",
            backup,
            allow_cross_server=False,
            apply=False,
            reason=None,
        )

    asset = next(path for path in backup.iterdir() if path.name != "manifest.json")
    asset.write_bytes(asset.read_bytes() + b"tampered")
    with pytest.raises(EmojiAdminError, match="size/hash verification"):
        await admin.restore(
            GUILD_ID,
            backup,
            allow_cross_server=False,
            apply=False,
            reason=None,
        )


def test_load_backup_rejects_unsafe_asset_path(tmp_path: Path) -> None:
    backup = tmp_path / "backup"
    backup.mkdir()
    manifest = {
        "schema_version": 1,
        "guild": {"id": GUILD_ID, "name": "Test"},
        "emojis": [
            {
                "id": EMOJI_ID,
                "name": "party",
                "asset": "../outside.png",
                "bytes": 10,
                "sha256": "a" * 64,
                "roles": [],
            }
        ],
    }
    (backup / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(EmojiAdminError, match="unsafe asset path"):
        _load_backup(backup)


def test_resolve_emoji_requires_id_for_ambiguous_name() -> None:
    emojis = [emoji("same"), emoji("same", "345678901234567890")]

    with pytest.raises(EmojiAdminError, match="ambiguous"):
        _resolve_emoji(emojis, "same")
    assert _resolve_emoji(emojis, EMOJI_ID)["id"] == EMOJI_ID


@pytest.mark.asyncio
async def test_discord_api_uses_documented_routes_payloads_and_reason() -> None:
    class RecordingAPI(DiscordAPI):
        def __init__(self) -> None:
            super().__init__("unused")
            self.calls: list[tuple[str, str, dict[str, Any]]] = []

        async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
            self.calls.append((method, path, kwargs))
            if method == "DELETE":
                return None
            return {"id": EMOJI_ID, "name": "new_name"}

    api = RecordingAPI()
    await api.create_emoji(GUILD_ID, "new_name", "data:image/png;base64,AAAA", [], "a reason")
    await api.rename_emoji(GUILD_ID, EMOJI_ID, "renamed", "rename reason")
    await api.delete_emoji(GUILD_ID, EMOJI_ID, "delete reason")

    assert api.calls == [
        (
            "POST",
            f"/guilds/{GUILD_ID}/emojis",
            {
                "json_body": {
                    "name": "new_name",
                    "image": "data:image/png;base64,AAAA",
                    "roles": [],
                },
                "reason": "a reason",
            },
        ),
        (
            "PATCH",
            f"/guilds/{GUILD_ID}/emojis/{EMOJI_ID}",
            {"json_body": {"name": "renamed"}, "reason": "rename reason"},
        ),
        (
            "DELETE",
            f"/guilds/{GUILD_ID}/emojis/{EMOJI_ID}",
            {"reason": "delete reason"},
        ),
    ]
