from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import quote

import aiohttp
from dotenv import load_dotenv

from .settings import PROJECT_ROOT

API_BASE = "https://discord.com/api/v10"
CDN_BASE = "https://cdn.discordapp.com"
BACKUP_SCHEMA_VERSION = 1
MAX_EMOJI_BYTES = 256 * 1024
MAX_RATE_LIMIT_RETRIES = 5
SUPPORTED_IMAGES = {
    ".gif": "image/gif",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".png": "image/png",
}
EMOJI_NAME = re.compile(r"^[A-Za-z0-9_]{2,32}$")
SNOWFLAKE = re.compile(r"^[0-9]{1,20}$")

JsonObject = dict[str, Any]


class EmojiAdminError(RuntimeError):
    """An expected operator-facing emoji administration error."""


class DiscordAPIError(EmojiAdminError):
    def __init__(self, status: int, method: str, path: str, detail: str):
        super().__init__(f"Discord API {method} {path} failed ({status}): {detail}")
        self.status = status


class EmojiAPI(Protocol):
    async def list_guilds(self) -> list[JsonObject]: ...

    async def list_emojis(self, guild_id: str) -> list[JsonObject]: ...

    async def download_emoji(self, emoji: JsonObject) -> bytes: ...

    async def create_emoji(
        self,
        guild_id: str,
        name: str,
        image: str,
        roles: list[str],
        reason: str,
    ) -> JsonObject: ...

    async def rename_emoji(
        self,
        guild_id: str,
        emoji_id: str,
        name: str,
        reason: str,
    ) -> JsonObject: ...

    async def delete_emoji(
        self,
        guild_id: str,
        emoji_id: str,
        reason: str,
    ) -> None: ...


class DiscordAPI:
    def __init__(self, token: str, api_base: str = API_BASE, cdn_base: str = CDN_BASE):
        self.token = token
        self.api_base = api_base.rstrip("/")
        self.cdn_base = cdn_base.rstrip("/")
        self.session: aiohttp.ClientSession | None = None
        self.cdn_session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> DiscordAPI:
        self.session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bot {self.token}",
                "User-Agent": "WGGBot-Emoji-Admin/1.0",
            }
        )
        self.cdn_session = aiohttp.ClientSession(headers={"User-Agent": "WGGBot-Emoji-Admin/1.0"})
        return self

    async def __aexit__(self, *_exc: object) -> None:
        if self.session is not None:
            await self.session.close()
        if self.cdn_session is not None:
            await self.cdn_session.close()

    def _session(self) -> aiohttp.ClientSession:
        if self.session is None:
            raise RuntimeError("DiscordAPI must be used as an async context manager")
        return self.session

    def _cdn_session(self) -> aiohttp.ClientSession:
        if self.cdn_session is None:
            raise RuntimeError("DiscordAPI must be used as an async context manager")
        return self.cdn_session

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: JsonObject | None = None,
        params: JsonObject | None = None,
        reason: str | None = None,
    ) -> Any:
        headers: dict[str, str] = {}
        if reason:
            headers["X-Audit-Log-Reason"] = quote(reason, safe="")

        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            async with self._session().request(
                method,
                f"{self.api_base}{path}",
                json=json_body,
                params=params,
                headers=headers,
            ) as response:
                raw = await response.read()
                payload: Any = None
                if raw:
                    try:
                        payload = json.loads(raw)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        payload = raw.decode("utf-8", errors="replace")

                if response.status == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                    retry_after = 1.0
                    if isinstance(payload, dict):
                        value = payload.get("retry_after", 1.0)
                        if isinstance(value, int | float):
                            retry_after = max(0.0, float(value))
                    await asyncio.sleep(retry_after)
                    continue

                if response.status >= 400:
                    detail = _api_error_detail(payload)
                    raise DiscordAPIError(response.status, method, path, detail)
                return payload

        raise DiscordAPIError(429, method, path, "rate limit retries exhausted")

    async def list_guilds(self) -> list[JsonObject]:
        guilds: list[JsonObject] = []
        after: str | None = None
        while True:
            params: JsonObject = {"limit": 200}
            if after is not None:
                params["after"] = after
            page = await self._request("GET", "/users/@me/guilds", params=params)
            if not isinstance(page, list):
                raise EmojiAdminError("Discord returned an invalid guild list")
            typed_page = [cast(JsonObject, guild) for guild in page if isinstance(guild, dict)]
            guilds.extend(typed_page)
            if len(page) < 200:
                break
            next_after = str(typed_page[-1].get("id", "")) if typed_page else ""
            if not next_after or next_after == after:
                raise EmojiAdminError("Discord guild pagination did not advance")
            after = next_after
        return guilds

    async def list_emojis(self, guild_id: str) -> list[JsonObject]:
        payload = await self._request("GET", f"/guilds/{guild_id}/emojis")
        if not isinstance(payload, list):
            raise EmojiAdminError("Discord returned an invalid emoji list")
        return [cast(JsonObject, emoji) for emoji in payload if isinstance(emoji, dict)]

    async def download_emoji(self, emoji: JsonObject) -> bytes:
        emoji_id = str(emoji["id"])
        extension = "gif" if emoji.get("animated") else "png"
        url = f"{self.cdn_base}/emojis/{emoji_id}.{extension}"
        async with self._cdn_session().get(url) as response:
            data = await response.read()
            if response.status >= 400:
                raise EmojiAdminError(
                    f"Discord CDN download failed for emoji {emoji_id} ({response.status})"
                )
            if not data:
                raise EmojiAdminError(f"Discord CDN returned an empty asset for emoji {emoji_id}")
            return data

    async def create_emoji(
        self,
        guild_id: str,
        name: str,
        image: str,
        roles: list[str],
        reason: str,
    ) -> JsonObject:
        payload = await self._request(
            "POST",
            f"/guilds/{guild_id}/emojis",
            json_body={"name": name, "image": image, "roles": roles},
            reason=reason,
        )
        if not isinstance(payload, dict):
            raise EmojiAdminError("Discord returned an invalid created emoji")
        return cast(JsonObject, payload)

    async def rename_emoji(
        self,
        guild_id: str,
        emoji_id: str,
        name: str,
        reason: str,
    ) -> JsonObject:
        payload = await self._request(
            "PATCH",
            f"/guilds/{guild_id}/emojis/{emoji_id}",
            json_body={"name": name},
            reason=reason,
        )
        if not isinstance(payload, dict):
            raise EmojiAdminError("Discord returned an invalid renamed emoji")
        return cast(JsonObject, payload)

    async def delete_emoji(
        self,
        guild_id: str,
        emoji_id: str,
        reason: str,
    ) -> None:
        await self._request(
            "DELETE",
            f"/guilds/{guild_id}/emojis/{emoji_id}",
            reason=reason,
        )


class EmojiAdmin:
    def __init__(self, api: EmojiAPI, backup_root: Path):
        self.api = api
        self.backup_root = backup_root
        self._guild_names: dict[str, str] | None = None

    async def guild_name(self, guild_id: str) -> str:
        if self._guild_names is None:
            self._guild_names = {
                str(guild.get("id")): str(guild.get("name") or guild.get("id"))
                for guild in await self.api.list_guilds()
            }
        return self._guild_names.get(guild_id, guild_id)

    async def backup(self, guild_id: str) -> Path:
        emojis = await self.api.list_emojis(guild_id)
        guild_name = await self.guild_name(guild_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        guild_root = self.backup_root / guild_id
        guild_root.mkdir(parents=True, exist_ok=True)
        target = guild_root / timestamp

        with tempfile.TemporaryDirectory(prefix=".partial-", dir=guild_root) as partial_name:
            partial = Path(partial_name)
            entries: list[JsonObject] = []
            for emoji in sorted(emojis, key=lambda item: str(item.get("id", ""))):
                emoji_id = str(emoji.get("id", ""))
                name = str(emoji.get("name", "emoji"))
                if not SNOWFLAKE.fullmatch(emoji_id):
                    raise EmojiAdminError(f"Discord returned an invalid emoji ID: {emoji_id!r}")
                extension = ".gif" if emoji.get("animated") else ".png"
                filename = f"{emoji_id}-{_filesystem_name(name)}{extension}"
                data = await self.api.download_emoji(emoji)
                (partial / filename).write_bytes(data)
                entries.append(
                    {
                        "id": emoji_id,
                        "name": name,
                        "animated": bool(emoji.get("animated", False)),
                        "available": bool(emoji.get("available", True)),
                        "managed": bool(emoji.get("managed", False)),
                        "require_colons": bool(emoji.get("require_colons", True)),
                        "roles": [str(role) for role in emoji.get("roles", [])],
                        "asset": filename,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )

            manifest = {
                "schema_version": BACKUP_SCHEMA_VERSION,
                "created_at": datetime.now(UTC).isoformat(),
                "guild": {"id": guild_id, "name": guild_name},
                "emoji_count": len(entries),
                "emojis": entries,
            }
            (partial / "manifest.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            partial_path = Path(partial_name)
            partial_path.rename(target)
        return target

    async def backup_before_change(self, guild_id: str) -> Path:
        path = await self.backup(guild_id)
        print(f"Safety backup: {path}")
        return path

    def verify_backup(self, backup_path: Path) -> int:
        manifest = _load_backup(backup_path)
        emojis = cast(list[JsonObject], manifest["emojis"])
        for entry in emojis:
            _verify_backup_asset(backup_path / str(entry["asset"]), entry)
        expected_count = manifest.get("emoji_count")
        if expected_count != len(emojis):
            raise EmojiAdminError(
                f"Backup manifest count is {expected_count!r}, but contains {len(emojis)} entries"
            )
        return len(emojis)

    async def add(
        self,
        guild_id: str,
        candidates: list[tuple[str, Path]],
        roles: list[str],
        *,
        apply: bool,
        reason: str | None,
    ) -> int:
        current = await self.api.list_emojis(guild_id)
        existing_names = {str(item.get("name")) for item in current}
        planned = [(name, path) for name, path in candidates if name not in existing_names]
        skipped = [(name, path) for name, path in candidates if name in existing_names]

        for name, path in skipped:
            print(f"SKIP existing :{name}: <- {path}")
        for name, path in planned:
            print(f"{'ADD' if apply else 'WOULD ADD'} :{name}: <- {path}")
        if not planned:
            print("No emojis need to be added.")
            return 0
        if not apply:
            print("Dry run only; repeat with --apply and --reason to make changes.")
            return 0

        audit_reason = _required_reason(reason)
        await self.backup_before_change(guild_id)
        created = 0
        for name, path in planned:
            result = await self.api.create_emoji(
                guild_id,
                name,
                _image_data_uri(path),
                roles,
                audit_reason,
            )
            created += 1
            print(f"ADDED :{name}: ({result.get('id', 'unknown ID')})")
        print(f"Added {created} emoji(s); skipped {len(skipped)} existing name(s).")
        return created

    async def remove(
        self,
        guild_id: str,
        identifier: str,
        *,
        apply: bool,
        reason: str | None,
    ) -> None:
        emoji = _resolve_emoji(await self.api.list_emojis(guild_id), identifier)
        action = f"REMOVE :{emoji['name']}: ({emoji['id']})"
        if not apply:
            print(f"WOULD {action}")
            print("Dry run only; repeat with --apply and --reason to make changes.")
            return

        audit_reason = _required_reason(reason)
        await self.backup_before_change(guild_id)
        await self.api.delete_emoji(guild_id, str(emoji["id"]), audit_reason)
        print(action)

    async def rename(
        self,
        guild_id: str,
        identifier: str,
        new_name: str,
        *,
        apply: bool,
        reason: str | None,
    ) -> None:
        _validate_name(new_name)
        emojis = await self.api.list_emojis(guild_id)
        emoji = _resolve_emoji(emojis, identifier)
        old_name = str(emoji["name"])
        if old_name == new_name:
            print(f"No change: emoji {emoji['id']} is already named :{new_name}:")
            return
        if any(str(item.get("name")) == new_name for item in emojis):
            raise EmojiAdminError(f"An emoji named :{new_name}: already exists in guild {guild_id}")
        action = f"RENAME :{old_name}: ({emoji['id']}) -> :{new_name}:"
        if not apply:
            print(f"WOULD {action}")
            print("Dry run only; repeat with --apply and --reason to make changes.")
            return

        audit_reason = _required_reason(reason)
        await self.backup_before_change(guild_id)
        await self.api.rename_emoji(guild_id, str(emoji["id"]), new_name, audit_reason)
        print(action)

    async def restore(
        self,
        guild_id: str,
        backup_path: Path,
        *,
        allow_cross_server: bool,
        apply: bool,
        reason: str | None,
    ) -> int:
        manifest = _load_backup(backup_path)
        source_guild_id = str(manifest["guild"]["id"])
        if source_guild_id != guild_id and not allow_cross_server:
            raise EmojiAdminError(
                f"Backup belongs to guild {source_guild_id}; pass --allow-cross-server "
                f"to copy it to guild {guild_id}"
            )

        existing = {str(item.get("name")) for item in await self.api.list_emojis(guild_id)}
        planned: list[tuple[JsonObject, Path]] = []
        skipped = 0
        for entry in manifest["emojis"]:
            if entry.get("managed"):
                print(f"SKIP managed :{entry['name']}: ({entry['id']})")
                skipped += 1
                continue
            if str(entry["name"]) in existing:
                print(f"SKIP existing :{entry['name']}:")
                skipped += 1
                continue
            asset = backup_path / str(entry["asset"])
            _verify_backup_asset(asset, entry)
            planned.append((entry, asset))
            print(f"{'RESTORE' if apply else 'WOULD RESTORE'} :{entry['name']}: <- {asset}")

        if not planned:
            print("No emojis need to be restored.")
            return 0
        if not apply:
            print("Dry run only; repeat with --apply and --reason to make changes.")
            return 0

        audit_reason = _required_reason(reason)
        await self.backup_before_change(guild_id)
        restored = 0
        for entry, asset in planned:
            await self.api.create_emoji(
                guild_id,
                str(entry["name"]),
                _image_data_uri(asset),
                [str(role) for role in entry.get("roles", [])],
                audit_reason,
            )
            restored += 1
            print(f"RESTORED :{entry['name']}:")
        print(f"Restored {restored} emoji(s); skipped {skipped} managed/existing emoji(s).")
        return restored


def _api_error_detail(payload: Any) -> str:
    if isinstance(payload, dict):
        message = payload.get("message")
        code = payload.get("code")
        if message and code is not None:
            return f"{message} (code {code})"
        if message:
            return str(message)
    if isinstance(payload, str) and payload.strip():
        return payload.strip()[:500]
    return "no error detail returned"


def _validate_snowflake(value: str, label: str) -> str:
    normalized = value.strip()
    if not SNOWFLAKE.fullmatch(normalized):
        raise EmojiAdminError(f"{label} must be a numeric Discord ID")
    return normalized


def _validate_name(name: str) -> str:
    if not EMOJI_NAME.fullmatch(name):
        raise EmojiAdminError(
            f"Invalid emoji name {name!r}; use 2-32 ASCII letters, numbers, or underscores"
        )
    return name


def _required_reason(reason: str | None) -> str:
    normalized = (reason or "").strip()
    if not normalized:
        raise EmojiAdminError("--reason is required when --apply is used")
    if len(normalized.encode("utf-8")) > 512:
        raise EmojiAdminError("--reason must be at most 512 UTF-8 bytes")
    return normalized


def _filesystem_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_-")
    return value[:64] or "emoji"


def _inferred_name(path: Path) -> str:
    stem = re.sub(r"^[0-9]+[-_ ]+", "", path.stem)
    name = re.sub(r"[^A-Za-z0-9_]", "_", stem)
    name = re.sub(r"_+", "_", name).strip("_")[:32]
    if len(name) < 2:
        name = f"e_{name}"[:32]
    return _validate_name(name)


def _image_kind(path: Path, data: bytes) -> str:
    suffix = path.suffix.lower()
    mime = SUPPORTED_IMAGES.get(suffix)
    if mime is None:
        raise EmojiAdminError(f"Unsupported image type for {path}; use PNG, GIF, JPG, or JPEG")
    signatures = {
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/gif": data.startswith((b"GIF87a", b"GIF89a")),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
    }
    if not signatures[mime]:
        raise EmojiAdminError(f"File contents do not match the {suffix} extension: {path}")
    return mime


def _image_data_uri(path: Path) -> str:
    data = path.read_bytes()
    if not data:
        raise EmojiAdminError(f"Emoji image is empty: {path}")
    if len(data) > MAX_EMOJI_BYTES:
        raise EmojiAdminError(
            f"Emoji image exceeds Discord's 256 KiB limit ({len(data)} bytes): {path}"
        )
    mime = _image_kind(path, data)
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _collect_candidates(paths: Sequence[Path], explicit_name: str | None) -> list[tuple[str, Path]]:
    files: list[Path] = []
    for source in paths:
        resolved = source.resolve()
        if resolved.is_dir():
            files.extend(
                item
                for item in sorted(resolved.rglob("*"))
                if item.is_file() and item.suffix.lower() in SUPPORTED_IMAGES
            )
        elif resolved.is_file():
            files.append(resolved)
        else:
            raise EmojiAdminError(f"Emoji image path does not exist: {source}")
    if not files:
        raise EmojiAdminError("No PNG, GIF, JPG, or JPEG emoji images were found")
    if explicit_name is not None and len(files) != 1:
        raise EmojiAdminError("--name can only be used when exactly one image file is selected")

    candidates: list[tuple[str, Path]] = []
    names: dict[str, Path] = {}
    for path in files:
        name = _validate_name(explicit_name) if explicit_name is not None else _inferred_name(path)
        _image_data_uri(path)
        if name in names:
            raise EmojiAdminError(
                f"Multiple input files map to :{name}:: {names[name]} and {path}; "
                "add them separately with explicit --name values"
            )
        names[name] = path
        candidates.append((name, path))
    return candidates


def _resolve_emoji(emojis: list[JsonObject], identifier: str) -> JsonObject:
    matches = [
        emoji
        for emoji in emojis
        if str(emoji.get("id")) == identifier or str(emoji.get("name")) == identifier
    ]
    if not matches:
        raise EmojiAdminError(f"No emoji named or identified by {identifier!r} was found")
    if len(matches) > 1:
        ids = ", ".join(str(emoji.get("id")) for emoji in matches)
        raise EmojiAdminError(
            f"Emoji name {identifier!r} is ambiguous; use one of these IDs: {ids}"
        )
    return matches[0]


def _load_backup(path: Path) -> JsonObject:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise EmojiAdminError(f"Backup manifest does not exist: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmojiAdminError(f"Could not read backup manifest {manifest_path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise EmojiAdminError(f"Unsupported or invalid backup manifest: {manifest_path}")
    guild = payload.get("guild")
    emojis = payload.get("emojis")
    if not isinstance(guild, dict) or not SNOWFLAKE.fullmatch(str(guild.get("id", ""))):
        raise EmojiAdminError(f"Backup manifest has an invalid guild ID: {manifest_path}")
    if not isinstance(emojis, list) or not all(isinstance(entry, dict) for entry in emojis):
        raise EmojiAdminError(f"Backup manifest has an invalid emoji list: {manifest_path}")
    for entry in emojis:
        emoji_id = str(entry.get("id", ""))
        asset = entry.get("asset")
        digest = entry.get("sha256")
        byte_count = entry.get("bytes")
        roles = entry.get("roles", [])
        try:
            _validate_name(str(entry.get("name", "")))
        except EmojiAdminError as exc:
            raise EmojiAdminError(
                f"Backup manifest has an invalid emoji name: {manifest_path}"
            ) from exc
        if not SNOWFLAKE.fullmatch(emoji_id):
            raise EmojiAdminError(f"Backup manifest has an invalid emoji ID: {manifest_path}")
        if not isinstance(asset, str) or Path(asset).name != asset:
            raise EmojiAdminError(f"Backup manifest has an unsafe asset path: {manifest_path}")
        if not isinstance(byte_count, int) or byte_count <= 0:
            raise EmojiAdminError(f"Backup manifest has an invalid asset size: {manifest_path}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise EmojiAdminError(f"Backup manifest has an invalid asset hash: {manifest_path}")
        if not isinstance(roles, list) or not all(SNOWFLAKE.fullmatch(str(role)) for role in roles):
            raise EmojiAdminError(f"Backup manifest has invalid role IDs: {manifest_path}")
    return cast(JsonObject, payload)


def _verify_backup_asset(path: Path, entry: JsonObject) -> None:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise EmojiAdminError(f"Could not read backup asset {path}: {exc}") from exc
    if len(data) != entry.get("bytes") or hashlib.sha256(data).hexdigest() != entry.get("sha256"):
        raise EmojiAdminError(f"Backup asset failed size/hash verification: {path}")
    _image_kind(path, data)


def _load_token(beta: bool) -> str:
    env_path = PROJECT_ROOT / ".env"
    if env_path.is_file() and os.access(env_path, os.R_OK):
        load_dotenv(env_path, override=False)
    key = "BETA_DISCORD_TOKEN" if beta else "LIVE_DISCORD_TOKEN"
    token = os.getenv(key, "").strip()
    if not token or token == "0":
        raise EmojiAdminError(f"{key} is required and must not be a placeholder")
    return token


def _add_mutation_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--apply",
        action="store_true",
        help="perform the mutation; without this flag the command is a dry run",
    )
    parser.add_argument("--reason", help="Discord audit-log reason; required with --apply")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Operator-only Discord server emoji backup and administration"
    )
    parser.add_argument("--beta", action="store_true", help="use BETA_DISCORD_TOKEN")
    parser.add_argument(
        "--backup-root",
        type=Path,
        default=PROJECT_ROOT / ".emoji-backups",
        help="directory for timestamped restorable backups",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("servers", help="list servers accessible to the selected bot")

    list_parser = subparsers.add_parser("list", help="list a server's emojis")
    list_parser.add_argument("--guild", required=True, help="numeric Discord server ID")

    backup_parser = subparsers.add_parser("backup", help="back up one server's emojis")
    backup_parser.add_argument("--guild", required=True, help="numeric Discord server ID")

    subparsers.add_parser("backup-all", help="back up emojis from every accessible server")

    verify_parser = subparsers.add_parser("verify", help="verify every asset in a generated backup")
    verify_parser.add_argument("--from", dest="source", required=True, type=Path)

    add_parser = subparsers.add_parser("add", help="add one image or all images in directories")
    add_parser.add_argument("--guild", required=True, help="numeric Discord server ID")
    add_parser.add_argument("paths", nargs="+", type=Path, help="image files or directories")
    add_parser.add_argument("--name", help="explicit name when adding exactly one image")
    add_parser.add_argument("--role", action="append", default=[], help="allowed role ID")
    _add_mutation_flags(add_parser)

    remove_parser = subparsers.add_parser("remove", help="remove an emoji by exact name or ID")
    remove_parser.add_argument("--guild", required=True, help="numeric Discord server ID")
    remove_parser.add_argument("--emoji", required=True, help="exact emoji name or numeric ID")
    _add_mutation_flags(remove_parser)

    rename_parser = subparsers.add_parser("rename", help="rename an emoji by exact name or ID")
    rename_parser.add_argument("--guild", required=True, help="numeric Discord server ID")
    rename_parser.add_argument("--emoji", required=True, help="exact emoji name or numeric ID")
    rename_parser.add_argument("--name", required=True, help="new emoji name")
    _add_mutation_flags(rename_parser)

    restore_parser = subparsers.add_parser(
        "restore", help="recreate missing emojis from a generated backup"
    )
    restore_parser.add_argument("--guild", required=True, help="numeric destination server ID")
    restore_parser.add_argument("--from", dest="source", required=True, type=Path)
    restore_parser.add_argument(
        "--allow-cross-server",
        action="store_true",
        help="allow copying a backup to a different server ID",
    )
    _add_mutation_flags(restore_parser)
    return parser


async def _run(args: argparse.Namespace, api: EmojiAPI) -> None:
    admin = EmojiAdmin(api, args.backup_root.resolve())
    if args.command == "servers":
        guilds = sorted(await api.list_guilds(), key=lambda item: str(item.get("name", "")).lower())
        for guild in guilds:
            print(f"{guild.get('id')}\t{guild.get('name', '(unnamed)')}")
        print(f"{len(guilds)} server(s)")
        return

    if args.command == "verify":
        source = args.source.resolve()
        count = admin.verify_backup(source)
        print(f"Backup verified: {source} ({count} emoji asset(s))")
        return

    if args.command == "backup-all":
        guilds = await api.list_guilds()
        for guild in guilds:
            guild_id = _validate_snowflake(str(guild.get("id", "")), "guild ID")
            path = await admin.backup(guild_id)
            print(f"BACKED UP {guild.get('name', guild_id)} ({guild_id}) -> {path}")
        print(f"Backed up {len(guilds)} server(s).")
        return

    guild_id = _validate_snowflake(args.guild, "guild ID")
    if args.command == "list":
        emojis = sorted(
            await api.list_emojis(guild_id), key=lambda item: str(item.get("name", "")).lower()
        )
        for emoji in emojis:
            flags = []
            if emoji.get("animated"):
                flags.append("animated")
            if emoji.get("managed"):
                flags.append("managed")
            if not emoji.get("available", True):
                flags.append("unavailable")
            suffix = f"\t{','.join(flags)}" if flags else ""
            print(f"{emoji.get('id')}\t:{emoji.get('name')}:\t{suffix}".rstrip())
        print(f"{len(emojis)} emoji(s)")
    elif args.command == "backup":
        path = await admin.backup(guild_id)
        print(f"Backup complete: {path}")
    elif args.command == "add":
        roles = [_validate_snowflake(role, "role ID") for role in args.role]
        candidates = _collect_candidates(args.paths, args.name)
        await admin.add(
            guild_id,
            candidates,
            roles,
            apply=args.apply,
            reason=args.reason,
        )
    elif args.command == "remove":
        await admin.remove(
            guild_id,
            args.emoji,
            apply=args.apply,
            reason=args.reason,
        )
    elif args.command == "rename":
        await admin.rename(
            guild_id,
            args.emoji,
            args.name,
            apply=args.apply,
            reason=args.reason,
        )
    elif args.command == "restore":
        await admin.restore(
            guild_id,
            args.source.resolve(),
            allow_cross_server=args.allow_cross_server,
            apply=args.apply,
            reason=args.reason,
        )
    else:
        raise EmojiAdminError(f"Unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        token = _load_token(args.beta)
        args.backup_root.resolve().mkdir(parents=True, exist_ok=True)
        return asyncio.run(_run_with_api(args, token))
    except (EmojiAdminError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


async def _run_with_api(args: argparse.Namespace, token: str) -> int:
    async with DiscordAPI(token) as api:
        await _run(args, api)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
