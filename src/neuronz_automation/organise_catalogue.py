"""File existing items into the agreed catalogue folders with verified receipts."""

import os
from datetime import datetime, timezone
from pathlib import Path

from .catalogue_types import FOLDER_NAMES, PUBLICATIONS, LEGACY_PUBLICATIONS, filing_patch, named_child, source_type
from .config import OUTPUT_DIR, ZOTERO_COLLECTION_KEY, ZOTERO_LIBRARY_ID
from .parsing import parse_extra
from .reports import write_json
from .zotero_client import ZoteroClient
from .zotero_updates import verify_fields


def organise(client, output_dir):
    run_id = (f"{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
              if os.environ.get("GITHUB_RUN_ID") else datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    receipt_dir = Path(output_dir) / "catalogue_organisation" / run_id
    if receipt_dir.exists():
        raise RuntimeError("Receipt directory already exists; retain the earlier snapshot and use a new run")
    roots = client.fetch_child_collections(ZOTERO_COLLECTION_KEY)
    catalogue = named_child(roots, "01 Catalogue Sources")
    children = client.fetch_child_collections(catalogue)
    items = client.fetch_collection_tree_items(ZOTERO_COLLECTION_KEY)
    before = {item["key"]: item for item in items}
    plans = [(item["key"], source_type(item["data"])) for item in items]
    unknown = [key for key, name in plans if not name
               and parse_extra(before[key]["data"].get("extra", "")).get("NeuroNZ Record ID")
               and not parse_extra(before[key]["data"].get("extra", "")).get("NeuroNZ Evidence ID")]
    if unknown:
        raise RuntimeError("Catalogue entries need source-category review before filing: " + ", ".join(unknown))
    for name in FOLDER_NAMES:
        if sum(child["data"]["name"] == name for child in children) > 1:
            raise RuntimeError(f"Duplicate {name} subcollections need review before writing")
    legacy = [child for child in children if child["data"]["name"] == LEGACY_PUBLICATIONS]
    if len(legacy) > 1 or (legacy and any(child["data"]["name"] == PUBLICATIONS for child in children)):
        raise RuntimeError("Conflicting old/new journal article folders require review before writing")
    write_json(receipt_dir / "before.json", {"root_collections": roots, "catalogue_children": children, "items": items})
    receipt = {"github_run_id": os.environ.get("GITHUB_RUN_ID"), "group": ZOTERO_LIBRARY_ID,
               "root": ZOTERO_COLLECTION_KEY, "catalogue": catalogue, "status": "running",
               "folders_created": [], "folders_renamed": [], "items": [], "unique_items_before": len(before)}
    def save():
        write_json(receipt_dir / "receipt.json", receipt)
        # Full item snapshots/receipts stay private on the runner. Publish counts only.
        summary = {key: value for key, value in receipt.items() if key != "items"}
        summary["updated_verified"] = sum(row["status"] == "updated_verified" for row in receipt["items"])
        write_json(Path(output_dir) / "catalogue_organisation_summary.json", summary)
    save()
    try:
        if legacy:
            client.rename_collection(legacy[0], PUBLICATIONS)
            children = client.fetch_child_collections(catalogue)
            if named_child(children, PUBLICATIONS) != legacy[0]["key"]:
                raise RuntimeError("Renamed journal collection did not retain its original key")
            receipt["folders_renamed"].append({"key": legacy[0]["key"], "from": LEGACY_PUBLICATIONS, "to": PUBLICATIONS})
            save()
        for name in FOLDER_NAMES:
            if not any(child["data"]["name"] == name for child in children):
                created = client.create_collection(name, catalogue)
                receipt["folders_created"].append({"name": name, "key": created["key"]})
                save()
                children = client.fetch_child_collections(catalogue)
            named_child(children, name)
        folders = {name: named_child(children, name) for name in FOLDER_NAMES}
        for key, name in plans:
            if not name:
                continue
            current = client.fetch_item(key)
            data = current["data"]
            # A concurrent category edit must be reviewed instead of filed from a stale plan.
            if source_type(data) != name:
                raise RuntimeError(f"Source category changed during organisation: {key}")
            patch = filing_patch(data, folders[name], name)
            row = {"zotero_key": key, "title": data.get("title"), "source_type": name,
                   "folder_key": folders[name], "previous_version": current["version"],
                   "previous_date_modified": data.get("dateModified"),
                   "status": "write_pending" if patch else "unchanged"}
            receipt["items"].append(row)
            save()
            if patch:
                client.patch_item(key, current["version"], patch)
                row["status"] = "written_unverified"
                save()
                verified = client.fetch_item(key)
                verify_fields(verified["data"], patch)
                retained = {field: value for field, value in data.items()
                            if field not in patch and field not in {"version", "dateModified"}}
                verify_fields(verified["data"], retained)
                row.update(status="updated_verified", date_modified=verified["data"].get("dateModified"),
                           version=verified["version"])
                save()
        after = {item["key"]: item for item in client.fetch_collection_tree_items(ZOTERO_COLLECTION_KEY)}
        if set(before) != set(after):
            raise RuntimeError("Item keys changed during organisation; inspect receipt before proceeding")
        for key, original in before.items():
            data = original["data"]
            retained = {field: value for field, value in data.items()
                        if field not in {"collections", "tags", "version", "dateModified"}}
            verify_fields(after[key]["data"], retained)
            if not set(data.get("collections", [])).issubset(after[key]["data"].get("collections", [])):
                raise RuntimeError(f"Existing collection membership lost: {key}")
            old_tags = {(tag["tag"], tag.get("type", 0)) for tag in data.get("tags", [])
                        if not (source_type(data) == PUBLICATIONS and tag["tag"] == f"source-type:{LEGACY_PUBLICATIONS}")}
            new_tags = {(tag["tag"], tag.get("type", 0)) for tag in after[key]["data"].get("tags", [])}
            if not old_tags.issubset(new_tags):
                raise RuntimeError(f"Existing tags lost: {key}")
        counts = {}
        for name, folder_key in folders.items():
            actual = {item["key"] for item in client.fetch_collection_items(folder_key)}
            expected = {key for key, item_type in plans if item_type == name}
            if not expected.issubset(actual):
                raise RuntimeError(f"Missing filed items in {name}")
            counts[name] = {"key": folder_key, "items": len(actual)}
        receipt.update(status="completed_verified", unique_items_after=len(after), folders=counts,
                       updated_verified=sum(row["status"] == "updated_verified" for row in receipt["items"]))
        save()
        return receipt
    except Exception as exc:
        receipt.update(status="failed", error=str(exc))
        save()
        raise


def main():
    if os.environ.get("ZOTERO_WRITE_ENABLED", "false").lower() != "true":
        raise SystemExit("Organisation requires ZOTERO_WRITE_ENABLED=true")
    api_key = os.environ.get("ZOTERO_API_KEY")
    if not api_key:
        raise SystemExit("ZOTERO_API_KEY is required")
    receipt = organise(ZoteroClient(api_key=api_key), OUTPUT_DIR)
    print({"status": receipt["status"], "folders": receipt["folders"],
           "updated_verified": receipt["updated_verified"], "unique_items": receipt["unique_items_after"]})


if __name__ == "__main__":
    main()
