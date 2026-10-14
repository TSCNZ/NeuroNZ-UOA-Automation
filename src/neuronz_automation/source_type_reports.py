"""Track the agreed source-type groups and PubMed publications independently."""

from .catalogue_types import FOLDER_NAMES, PUBLICATIONS, source_type


def classified_records(cache):
    records = {}
    for bucket in cache.values():
        for record in bucket:
            data = {**record.get("bibliography", {}), "itemType": record.get("item_type"),
                    "PMID": record.get("pmid"), "url": record.get("primary_link"),
                    "extra": "\n".join(f"{key}: {value}" for key, value in record.get("extra", {}).items())}
            name = source_type(data)
            if name:
                records[record["zotero_key"]] = {"source_type": name, **record}
    return records


def source_type_reports(previous_cache, cache):
    previous, current = classified_records(previous_cache), classified_records(cache)
    inventory = {name: {"count": 0, "items": []} for name in FOLDER_NAMES}
    source_changes, publication_changes = [], []
    for key in sorted(set(previous) | set(current)):
        record = current.get(key) or previous[key]
        name = record["source_type"]
        if key in current:
            inventory[name]["count"] += 1
            inventory[name]["items"].append({"zotero_key": key, "title": record["title"],
                "stable_id": record["stable_id"], "pmid": record.get("pmid", ""),
                "date_added": record["date_added"], "date_modified": record["date_modified"]})
        fields = []
        if key not in current:
            status = "removed"
        elif key not in previous:
            status = "new"
        else:
            fields = sorted(field for field, value in record.items()
                            if field != "zotero_version" and previous[key].get(field) != value)
            status = "changed" if fields else "unchanged"
        row = {"zotero_key": key, "stable_id": record["stable_id"], "source_type": name,
               "title": record["title"], "change_status": status, "changed_fields": "; ".join(fields)}
        (publication_changes if name == PUBLICATIONS else source_changes).append(row)
    return inventory, source_changes, publication_changes
