from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from wggbot.emoji_admin import (
    DiscordAPI,
    EmojiAdmin,
    EmojiAdminError,
    _image_data_uri,
    _load_token,
    _required_reason,
    _validate_name,
    _validate_snowflake,
)

PREMIUM_LIMITS = {0: 50, 1: 100, 2: 150, 3: 250}


def load_plan(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmojiAdminError(f"Could not read emoji organization plan {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise EmojiAdminError(f"Unsupported or invalid emoji organization plan: {path}")
    guild = payload.get("guild")
    renames = payload.get("renames")
    uploads = payload.get("uploads")
    expected_after = payload.get("expected_after")
    if not isinstance(guild, dict):
        raise EmojiAdminError("Emoji organization plan is missing its guild")
    _validate_snowflake(str(guild.get("id", "")), "plan guild ID")
    if not isinstance(renames, list) or not all(isinstance(item, dict) for item in renames):
        raise EmojiAdminError("Emoji organization plan has invalid renames")
    if not isinstance(uploads, list) or not all(isinstance(item, dict) for item in uploads):
        raise EmojiAdminError("Emoji organization plan has invalid uploads")
    if not isinstance(expected_after, dict):
        raise EmojiAdminError("Emoji organization plan is missing expected_after")
    return cast(dict[str, Any], payload)


def validate_plan(plan: dict[str, Any], plan_path: Path) -> None:
    renames = cast(list[dict[str, Any]], plan["renames"])
    uploads = cast(list[dict[str, Any]], plan["uploads"])
    ids: set[str] = set()
    names: set[str] = set()
    hashes: set[str] = set()

    for entry in renames:
        emoji_id = _validate_snowflake(str(entry.get("id", "")), "rename emoji ID")
        if emoji_id in ids:
            raise EmojiAdminError(f"Duplicate rename emoji ID in plan: {emoji_id}")
        ids.add(emoji_id)
        _validate_name(str(entry.get("from", "")))
        target = _validate_name(str(entry.get("to", "")))
        if target in names:
            raise EmojiAdminError(f"Duplicate final emoji name in plan: {target}")
        names.add(target)
        validate_asset(entry, plan_path, hashes)

    for entry in uploads:
        target = _validate_name(str(entry.get("name", "")))
        if target in names:
            raise EmojiAdminError(f"Duplicate final emoji name in plan: {target}")
        names.add(target)
        validate_asset(entry, plan_path, hashes)

    expected = cast(dict[str, Any], plan["expected_after"])
    static = sum(not bool(entry.get("animated")) for entry in renames + uploads)
    animated = len(renames) + len(uploads) - static
    actual = {"total": len(names), "static": static, "animated": animated}
    for key, value in actual.items():
        if expected.get(key) != value:
            raise EmojiAdminError(
                f"Plan expected_after.{key} is {expected.get(key)!r}, calculated {value}"
            )


def asset_path(plan_path: Path, entry: dict[str, Any]) -> Path:
    value = entry.get("asset")
    if not isinstance(value, str) or not value:
        raise EmojiAdminError("Plan contains a missing asset path")
    root = plan_path.parent.resolve()
    path = (root / value).resolve()
    if path != root and root not in path.parents:
        raise EmojiAdminError(f"Plan contains an unsafe asset path: {value}")
    return path


def validate_asset(entry: dict[str, Any], plan_path: Path, hashes: set[str]) -> None:
    path = asset_path(plan_path, entry)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise EmojiAdminError(f"Could not read planned emoji asset {path}: {exc}") from exc
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry.get("sha256"):
        raise EmojiAdminError(f"Planned emoji asset hash changed: {path}")
    if digest in hashes:
        raise EmojiAdminError(f"Duplicate planned emoji asset remains: {path}")
    hashes.add(digest)
    _image_data_uri(path)
    animated = bool(entry.get("animated"))
    if animated != (path.suffix.lower() == ".gif"):
        raise EmojiAdminError(f"Planned emoji animation flag disagrees with its asset: {path}")


def emoji_limit(guild: dict[str, Any]) -> int:
    tier = guild.get("premium_tier", 0)
    if not isinstance(tier, int) or tier not in PREMIUM_LIMITS:
        raise EmojiAdminError(f"Discord returned an invalid premium tier: {tier!r}")
    limit = PREMIUM_LIMITS[tier]
    features = guild.get("features", [])
    if isinstance(features, list) and "MORE_EMOJI" in features:
        limit = max(limit, 200)
    return limit


def preflight_live_state(
    plan: dict[str, Any], current: list[dict[str, Any]], per_type_limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    renames = cast(list[dict[str, Any]], plan["renames"])
    uploads = cast(list[dict[str, Any]], plan["uploads"])
    by_id = {str(item.get("id")): item for item in current}
    if len(by_id) != len(current):
        raise EmojiAdminError("Discord returned duplicate live emoji IDs")

    planned_ids = {str(entry["id"]) for entry in renames}
    planned_upload_names = {str(entry["name"]) for entry in uploads}
    unexpected = [
        item
        for item in current
        if str(item.get("id")) not in planned_ids
        and str(item.get("name")) not in planned_upload_names
    ]
    if unexpected:
        rendered = ", ".join(f":{item.get('name')}: ({item.get('id')})" for item in unexpected[:10])
        raise EmojiAdminError(f"Live server contains emoji outside the reviewed plan: {rendered}")

    remaining_renames: list[dict[str, Any]] = []
    for entry in renames:
        live = by_id.get(str(entry["id"]))
        if live is None:
            raise EmojiAdminError(f"Reviewed server emoji is missing live: {entry['id']}")
        live_name = str(live.get("name"))
        if live_name not in {entry["from"], entry["to"]}:
            raise EmojiAdminError(
                f"Reviewed emoji {entry['id']} changed outside this plan: {live_name!r}"
            )
        if bool(live.get("animated")) != bool(entry.get("animated")):
            raise EmojiAdminError(f"Reviewed emoji animation type changed: {entry['id']}")
        if live_name != entry["to"]:
            remaining_renames.append(entry)

    current_by_name: dict[str, dict[str, Any]] = {}
    for item in current:
        name = str(item.get("name"))
        if name in current_by_name:
            raise EmojiAdminError(f"Live server has an ambiguous duplicate emoji name: {name}")
        current_by_name[name] = item

    for entry in remaining_renames:
        holder = current_by_name.get(str(entry["to"]))
        if holder is not None and str(holder.get("id")) != str(entry["id"]):
            raise EmojiAdminError(
                f"Rename target :{entry['to']}: is held by emoji {holder.get('id')}"
            )

    remaining_uploads: list[dict[str, Any]] = []
    for entry in uploads:
        live = current_by_name.get(str(entry["name"]))
        if live is None:
            remaining_uploads.append(entry)
        elif str(live.get("id")) in planned_ids:
            raise EmojiAdminError(f"Upload target :{entry['name']}: is held by a reviewed emoji")
        elif bool(live.get("animated")) != bool(entry.get("animated")):
            raise EmojiAdminError(f"Existing upload has the wrong animation type: {entry['name']}")

    expected = cast(dict[str, Any], plan["expected_after"])
    for key in ("static", "animated"):
        value = expected.get(key)
        if not isinstance(value, int) or value > per_type_limit:
            raise EmojiAdminError(
                f"Planned {key} count {value!r} exceeds Discord's current "
                f"{per_type_limit}-emoji per-type limit"
            )
    return remaining_renames, remaining_uploads


def verify_final_state(plan: dict[str, Any], current: list[dict[str, Any]]) -> None:
    renames = cast(list[dict[str, Any]], plan["renames"])
    uploads = cast(list[dict[str, Any]], plan["uploads"])
    expected_by_id = {str(entry["id"]): str(entry["to"]) for entry in renames}
    expected_names = {str(entry["to"]) for entry in renames} | {
        str(entry["name"]) for entry in uploads
    }
    live_names = [str(item.get("name")) for item in current]
    if len(live_names) != len(set(live_names)):
        raise EmojiAdminError("Live server has duplicate emoji names after synchronization")
    if set(live_names) != expected_names:
        missing = sorted(expected_names - set(live_names))
        extra = sorted(set(live_names) - expected_names)
        raise EmojiAdminError(
            f"Final live names differ from plan; missing={missing}, extra={extra}"
        )
    live_by_id = {str(item.get("id")): item for item in current}
    for emoji_id, name in expected_by_id.items():
        if str(live_by_id.get(emoji_id, {}).get("name")) != name:
            raise EmojiAdminError(f"Reviewed emoji ID {emoji_id} does not have final name :{name}:")
    static = sum(not bool(item.get("animated")) for item in current)
    animated = len(current) - static
    expected = cast(dict[str, Any], plan["expected_after"])
    if (len(current), static, animated) != (
        expected["total"],
        expected["static"],
        expected["animated"],
    ):
        raise EmojiAdminError(
            f"Final live counts are total={len(current)}, static={static}, animated={animated}; "
            f"expected {expected}"
        )


async def run(args: argparse.Namespace) -> None:
    plan_path = args.plan.resolve()
    plan = load_plan(plan_path)
    validate_plan(plan, plan_path)
    guild_id = str(plan["guild"]["id"])
    token = _load_token(args.beta)

    async with DiscordAPI(token) as api:
        current = await api.list_emojis(guild_id)
        guild_payload = await api._request("GET", f"/guilds/{guild_id}")
        if not isinstance(guild_payload, dict):
            raise EmojiAdminError("Discord returned an invalid guild record")
        if str(guild_payload.get("id")) != guild_id:
            raise EmojiAdminError("Discord guild record does not match the plan guild")
        limit = emoji_limit(guild_payload)
        remaining_renames, remaining_uploads = preflight_live_state(plan, current, limit)
        print(
            f"Preflight passed for {guild_payload.get('name', guild_id)} ({guild_id}): "
            f"{len(current)} live, {len(remaining_renames)} renames and "
            f"{len(remaining_uploads)} uploads remaining, {limit} per-type limit"
        )
        if not remaining_renames and not remaining_uploads:
            verify_final_state(plan, current)
            print("Live emoji collection already matches the approved plan.")
            return
        if not args.apply:
            print("Dry run only; repeat with --apply and --reason to synchronize Discord.")
            return

        reason = _required_reason(args.reason)
        admin = EmojiAdmin(api, args.backup_root.resolve())
        await admin.backup_before_change(guild_id)

        for number, entry in enumerate(remaining_renames, start=1):
            result = await api.rename_emoji(guild_id, str(entry["id"]), str(entry["to"]), reason)
            if str(result.get("name")) != str(entry["to"]):
                raise EmojiAdminError(f"Discord did not confirm rename for emoji {entry['id']}")
            print(
                f"RENAMED {number}/{len(remaining_renames)} "
                f":{entry['from']}: -> :{entry['to']}: ({entry['id']})"
            )

        for number, entry in enumerate(remaining_uploads, start=1):
            path = asset_path(plan_path, entry)
            result = await api.create_emoji(
                guild_id,
                str(entry["name"]),
                _image_data_uri(path),
                [],
                reason,
            )
            if str(result.get("name")) != str(entry["name"]):
                raise EmojiAdminError(f"Discord did not confirm upload :{entry['name']}:")
            print(
                f"UPLOADED {number}/{len(remaining_uploads)} :{entry['name']}: ({result.get('id')})"
            )

        final = await api.list_emojis(guild_id)
        verify_final_state(plan, final)
        static = sum(not bool(item.get("animated")) for item in final)
        print(
            f"Synchronization complete and verified: {len(final)} total, "
            f"{static} static, {len(final) - static} animated"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely synchronize Discord with a reviewed emoji organization plan"
    )
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--backup-root", type=Path, default=Path(".emoji-backups"))
    parser.add_argument("--beta", action="store_true", help="use BETA_DISCORD_TOKEN")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reason", help="Discord audit-log reason; required with --apply")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        asyncio.run(run(args))
    except (EmojiAdminError, OSError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
