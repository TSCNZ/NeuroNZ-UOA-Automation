"""Catalogue source types agreed for the eight subcollections."""

from .parsing import extract_pmid, parse_extra

PUBLICATIONS = "Published Research / Journal Articles"
SOURCE_TYPES = {
    "Administrative": "Administrative Data",
    "National survey": "National Surveys",
    "Research survey/cohort study": "Research Surveys & Cohort Studies",
    "Registry": "Registries",
    "Neurological workforce": "Neurological Workforce Data",
    "International data system": "International Data Systems",
    "Use of NZ neurological data": "Use of NZ Neurological Data",
}
FOLDER_NAMES = (*SOURCE_TYPES.values(), PUBLICATIONS)
PUBLICATION_TAGS = ("type:publication", "category:Journal Article", "source:pubmed")


def source_type(data):
    """Use explicit source categories or verified import provenance, never title dates."""
    extra = parse_extra(data.get("extra", ""))
    pmid = data.get("PMID") or extract_pmid(data.get("url"), data.get("extra"))
    if (data.get("itemType") == "journalArticle" and pmid
            and extra.get("Source candidate ID") == f"pubmed:{pmid}"
            and all(data.get(field) for field in ("publicationTitle", "creators", "date"))):
        return PUBLICATIONS
    # Legacy evidence and taxonomy records are supporting records, not catalogue entries.
    if extra.get("NeuroNZ Evidence ID") or not extra.get("NeuroNZ Record ID"):
        return None
    category = extra.get("Source category", "")
    return SOURCE_TYPES.get(category) or (category if category in FOLDER_NAMES else None)


def filing_patch(data, folder_key, name):
    """Add a membership and tags while retaining all existing memberships and tags."""
    patch = {}
    collections = list(data.get("collections", []))
    if folder_key not in collections:
        patch["collections"] = [*collections, folder_key]
    tags = list(data.get("tags", []))
    known = {tag["tag"] for tag in tags}
    additions = [f"source-type:{name}"]
    if name == PUBLICATIONS:
        additions.extend(PUBLICATION_TAGS)
    tags += [{"tag": tag} for tag in additions if tag not in known]
    if tags != data.get("tags", []):
        patch["tags"] = tags
    return patch


def named_child(children, name):
    matches = [child for child in children if child["data"]["name"] == name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one {name} collection; found {len(matches)}")
    return matches[0]["key"]
