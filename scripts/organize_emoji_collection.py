from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EMOJI_ROOT = ROOT / "emojis"
REVIEW_FILE = EMOJI_ROOT / "review.html"
PLAN_FILE = EMOJI_ROOT / "organization-plan.json"
CATALOG_FILE = EMOJI_ROOT / "catalog.csv"
SERVER_ROOT = EMOJI_ROOT / "server_emojis"
IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png"}
EMOJI_NAME = re.compile(r"^[a-z0-9_]{2,32}$")


class ReviewParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        if tag == "button" and "emoji-card" in values.get("class", "").split():
            self.items.append(values)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_review() -> list[dict[str, str]]:
    parser = ReviewParser()
    parser.feed(REVIEW_FILE.read_text(encoding="utf-8"))
    if len(parser.items) != 275:
        raise RuntimeError(f"Expected 275 reviewed assets, found {len(parser.items)}")
    return parser.items


def load_backup(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    entries = manifest.get("emojis")
    if not isinstance(entries, list) or len(entries) != 169:
        raise RuntimeError("The selected backup is not the reviewed 169-emoji server state")
    by_id = {str(entry["id"]): entry for entry in entries}
    if len(by_id) != len(entries):
        raise RuntimeError("The backup contains duplicate emoji IDs")
    for entry in entries:
        asset = path / str(entry["asset"])
        if not asset.is_file() or digest(asset) != entry["sha256"]:
            raise RuntimeError(f"Backup asset failed verification: {asset}")
    return manifest, by_id


def local_source(item: dict[str, str]) -> Path:
    path = (ROOT / item["data-current-file"]).resolve()
    if ROOT not in path.parents:
        raise RuntimeError(f"Unsafe reviewed path: {path}")
    return path


def local_target(item: dict[str, str]) -> Path:
    source = local_source(item)
    return source.with_name(f"{item['data-proposed-name']}{source.suffix.lower()}")


def validate_review(items: list[dict[str, str]], backup_entries: dict[str, dict[str, Any]]) -> None:
    kept = [item for item in items if item["data-duplicate-action"] != "remove"]
    proposed_names = [item["data-proposed-name"] for item in kept]
    invalid = [name for name in proposed_names if not EMOJI_NAME.fullmatch(name)]
    if invalid:
        raise RuntimeError(f"Invalid proposed emoji names: {invalid}")
    if len(proposed_names) != len(set(proposed_names)):
        raise RuntimeError("Reviewed final emoji names are not globally unique")
    if len(kept) != 273:
        raise RuntimeError(f"Expected 273 unique reviewed assets, found {len(kept)}")

    server_items = [item for item in items if item["data-source"] == "server"]
    if len(server_items) != 169:
        raise RuntimeError("Reviewed server set does not contain 169 assets")
    for item in server_items:
        emoji_id = item["data-discord-id"]
        entry = backup_entries.get(emoji_id)
        if entry is None or entry["name"] != item["data-current-name"]:
            raise RuntimeError(f"Backup no longer matches reviewed emoji {emoji_id}")

    for item in items:
        if item["data-source"] == "server":
            continue
        source = local_source(item)
        if not source.is_file() or digest(source) != item["data-sha256"]:
            raise RuntimeError(f"Local reviewed asset changed: {source}")

    duplicate_groups: dict[str, list[dict[str, str]]] = {}
    for item in items:
        group = item["data-duplicate-group"]
        if group:
            duplicate_groups.setdefault(group, []).append(item)
    if len(duplicate_groups) != 2:
        raise RuntimeError("Expected exactly two reviewed duplicate groups")
    for group, members in duplicate_groups.items():
        if len(members) != 2 or {item["data-duplicate-action"] for item in members} != {
            "keep",
            "remove",
        }:
            raise RuntimeError(f"Invalid duplicate disposition for {group}")
        if len({item["data-sha256"] for item in members}) != 1:
            raise RuntimeError(f"Duplicate group is not byte-identical: {group}")


def apply_local_changes(
    items: list[dict[str, str]], backup_path: Path, backup_entries: dict[str, dict[str, Any]]
) -> None:
    for item in items:
        if item["data-source"] == "server" or item["data-duplicate-action"] != "remove":
            continue
        source = local_source(item)
        if source.exists():
            source.unlink()

    for item in items:
        if item["data-source"] == "server" or item["data-duplicate-action"] == "remove":
            continue
        source = local_source(item)
        target = local_target(item)
        if target.exists():
            if source.exists() or digest(target) != item["data-sha256"]:
                raise RuntimeError(f"Conflicting organized target: {target}")
            continue
        source.rename(target)

    SERVER_ROOT.mkdir(exist_ok=True)
    for item in items:
        if item["data-source"] != "server":
            continue
        entry = backup_entries[item["data-discord-id"]]
        source = backup_path / str(entry["asset"])
        target = SERVER_ROOT / f"{item['data-proposed-name']}{source.suffix.lower()}"
        if target.exists():
            if digest(target) != entry["sha256"]:
                raise RuntimeError(f"Conflicting server dump target: {target}")
            continue
        shutil.copy2(source, target)


def build_plan(
    items: list[dict[str, str]],
    backup_path: Path,
    backup_manifest: dict[str, Any],
    backup_entries: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    renames = []
    uploads = []
    duplicate_removals = []
    for item in items:
        source = item["data-source"]
        if source == "server":
            entry = backup_entries[item["data-discord-id"]]
            asset = (
                SERVER_ROOT
                / f"{item['data-proposed-name']}{Path(str(entry['asset'])).suffix.lower()}"
            )
            renames.append(
                {
                    "id": item["data-discord-id"],
                    "from": item["data-current-name"],
                    "to": item["data-proposed-name"],
                    "animated": bool(entry["animated"]),
                    "asset": str(asset.relative_to(EMOJI_ROOT)),
                    "sha256": digest(asset),
                }
            )
        elif item["data-duplicate-action"] == "remove":
            duplicate_removals.append(
                {
                    "source": source,
                    "original_file": item["data-current-file"],
                    "sha256": item["data-sha256"],
                    "canonical": item["data-duplicate-canonical"],
                }
            )
        else:
            asset = local_target(item)
            uploads.append(
                {
                    "name": item["data-proposed-name"],
                    "source": source,
                    "original_file": item["data-current-file"],
                    "asset": str(asset.relative_to(EMOJI_ROOT)),
                    "animated": item["data-animated"] == "true",
                    "sha256": digest(asset),
                }
            )

    static_before = sum(not bool(entry["animated"]) for entry in backup_entries.values())
    animated_before = len(backup_entries) - static_before
    static_uploads = sum(not entry["animated"] for entry in uploads)
    animated_uploads = len(uploads) - static_uploads
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "guild": backup_manifest["guild"],
        "review_file": str(REVIEW_FILE.relative_to(ROOT)),
        "source_backup": str(backup_path.relative_to(ROOT)),
        "expected_before": {
            "total": len(renames),
            "static": static_before,
            "animated": animated_before,
        },
        "expected_after": {
            "total": len(renames) + len(uploads),
            "static": static_before + static_uploads,
            "animated": animated_before + animated_uploads,
        },
        "renames": sorted(renames, key=lambda entry: entry["id"]),
        "uploads": sorted(uploads, key=lambda entry: entry["name"]),
        "duplicates_removed": duplicate_removals,
    }


def write_catalog(plan: dict[str, Any]) -> None:
    rows = []
    for entry in plan["renames"]:
        rows.append(
            {
                "collection": "wheresgang_server",
                "discord_id": entry["id"],
                "original_name": entry["from"],
                "organized_name": entry["to"],
                "asset": entry["asset"],
                "sha256": entry["sha256"],
            }
        )
    for entry in plan["uploads"]:
        rows.append(
            {
                "collection": f"local_{entry['source']}",
                "discord_id": "",
                "original_name": Path(entry["original_file"]).stem,
                "organized_name": entry["name"],
                "asset": entry["asset"],
                "sha256": entry["sha256"],
            }
        )
    with CATALOG_FILE.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the approved emoji review locally")
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    backup_path = args.backup.resolve()
    items = load_review()
    manifest, backup_entries = load_backup(backup_path)
    validate_review(items, backup_entries)
    print("Validated 275 reviewed assets: 273 unique, 2 duplicate copies")
    print("Planned: 169 server dump assets, 104 local uploads, 2 local duplicate removals")
    if not args.apply:
        print("Dry run only; repeat with --apply to organize the local collection")
        return

    apply_local_changes(items, backup_path, backup_entries)
    plan = build_plan(items, backup_path, manifest, backup_entries)
    PLAN_FILE.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    write_catalog(plan)
    print(f"Wrote {PLAN_FILE.relative_to(ROOT)} and {CATALOG_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
