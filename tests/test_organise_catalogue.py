import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from neuronz_automation.catalogue_types import FOLDER_NAMES, PUBLICATIONS, LEGACY_PUBLICATIONS, PUBLISHED_RESEARCH, filing_patch, source_type
from neuronz_automation.organise_catalogue import organise


class MemoryClient:
    def __init__(self):
        self.children = []
        self.patches = []
        self.items = {
            "REG": {"key": "REG", "version": 1, "data": {
                "key": "REG", "version": 1, "title": "Registry 2020", "itemType": "webpage",
                "collections": ["CAT", "OTHER"], "tags": [{"tag": "curated", "type": 1}],
                "extra": "NeuroNZ Record ID: NZNEURO-001\nSource category: Registry",
                "dateAdded": "2026-08-01T00:00:00Z", "dateModified": "2026-08-01T00:00:00Z"}},
            "PUB": {"key": "PUB", "version": 1, "data": {
                "key": "PUB", "version": 1, "title": "Stroke outcomes", "itemType": "journalArticle",
                "collections": ["EVID"], "tags": [{"tag": "type:evidence"}],
                "extra": "NeuroNZ Evidence ID: E1\nPMID: 123\nSource candidate ID: pubmed:123",
                "PMID": "123", "publicationTitle": "Journal", "creators": [{"name": "Research team"}],
                "date": "2026", "dateAdded": "2026-10-01T00:00:00Z", "dateModified": "2026-10-01T00:00:00Z"}},
            "OLD": {"key": "OLD", "version": 1, "data": {
                "itemType": "webpage", "title": "Study 2026", "collections": ["EVID"],
                "extra": "NeuroNZ Evidence ID: E2", "tags": []}},
        }

    def fetch_child_collections(self, key):
        if key == "CAT":
            return deepcopy(self.children)
        return [{"key": "CAT", "data": {"name": "01 Catalogue Sources"}}]

    def fetch_collection_tree_items(self, key):
        return deepcopy(list(self.items.values()))

    def fetch_collection_items(self, key):
        return [deepcopy(item) for item in self.items.values() if key in item["data"]["collections"]]

    def create_collection(self, name, parent_key):
        assert parent_key == "CAT"
        item = {"key": f"F{len(self.children)}", "data": {"name": name, "parentCollection": parent_key}}
        self.children.append(item)
        return deepcopy(item)

    def rename_collection(self, collection, name):
        item = next(item for item in self.children if item["key"] == collection["key"])
        item["data"]["name"] = name

    def fetch_item(self, key):
        return deepcopy(self.items[key])

    def patch_item(self, key, version, patch):
        assert version == self.items[key]["version"]
        self.patches.append((key, version, deepcopy(patch)))
        self.items[key]["data"].update(deepcopy(patch))
        # Zotero may reorder memberships in its response; order has no filing meaning.
        self.items[key]["data"]["collections"] = sorted(self.items[key]["data"]["collections"], reverse=True)
        self.items[key]["version"] += 1
        self.items[key]["data"].update(version=self.items[key]["version"], dateModified="2026-10-14T00:00:00Z")


class OrganisationTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict("os.environ", {"GITHUB_RUN_ID": "organisation-test", "GITHUB_RUN_ATTEMPT": "1"})
        environment.start()
        self.addCleanup(environment.stop)

    def test_filing_preserves_metadata_memberships_tags_and_is_idempotent(self):
        client = MemoryClient()
        original = deepcopy(client.items)
        with tempfile.TemporaryDirectory() as directory:
            receipt = organise(client, directory)
            self.assertEqual(receipt["status"], "completed_verified")
            self.assertEqual(receipt["updated_verified"], 2)
            self.assertEqual(set(receipt["folders"]), set(FOLDER_NAMES))
            self.assertEqual(receipt["unique_items_after"], 3)
            self.assertEqual(client.items["OLD"], original["OLD"])
            self.assertTrue(set(original["REG"]["data"]["collections"]).issubset(client.items["REG"]["data"]["collections"]))
            self.assertIn({"tag": "curated", "type": 1}, client.items["REG"]["data"]["tags"])
            self.assertEqual(client.items["PUB"]["data"]["dateAdded"], original["PUB"]["data"]["dateAdded"])
            self.assertIn({"tag": "source:pubmed"}, client.items["PUB"]["data"]["tags"])
            with patch.dict("os.environ", {"GITHUB_RUN_ATTEMPT": "2"}):
                again = organise(client, directory)
            self.assertEqual(again["updated_verified"], 0)
            self.assertEqual(len(client.children), 9)
            self.assertEqual(len(client.patches), 2)

    def test_split_preserves_article_collection_key_and_separates_research_folder(self):
        client = MemoryClient()
        client.children = [{"key": "ARTICLE-FOLDER", "version": 1, "data": {
            "name": LEGACY_PUBLICATIONS, "parentCollection": "CAT"}}]
        client.items["PUB"]["data"]["collections"].append("ARTICLE-FOLDER")
        client.items["PUB"]["data"]["tags"].append({"tag": f"source-type:{LEGACY_PUBLICATIONS}"})
        with tempfile.TemporaryDirectory() as directory:
            receipt = organise(client, directory)
        self.assertEqual(receipt["folders"][PUBLICATIONS]["key"], "ARTICLE-FOLDER")
        self.assertEqual(receipt["folders"][PUBLICATIONS]["items"], 1)
        self.assertEqual(receipt["folders"][PUBLISHED_RESEARCH]["items"], 0)
        self.assertNotIn(LEGACY_PUBLICATIONS, {item["data"]["name"] for item in client.children})
        self.assertNotIn({"tag": f"source-type:{LEGACY_PUBLICATIONS}"}, client.items["PUB"]["data"]["tags"])
        self.assertIn({"tag": f"source-type:{PUBLICATIONS}"}, client.items["PUB"]["data"]["tags"])

    def test_non_journal_research_requires_explicit_category(self):
        data = {"itemType": "report", "extra": "NeuroNZ Record ID: NZNEURO-100\nSource category: Published Research"}
        self.assertEqual(source_type(data), PUBLISHED_RESEARCH)
        patch = filing_patch(data, "RESEARCH", PUBLISHED_RESEARCH)
        self.assertIn({"tag": "type:publication"}, patch["tags"])
        self.assertNotIn({"tag": "source:pubmed"}, patch["tags"])

    def test_same_attempt_cannot_overwrite_earlier_snapshot(self):
        client = MemoryClient()
        with tempfile.TemporaryDirectory() as directory:
            organise(client, directory)
            before = next(Path(directory).rglob("before.json"))
            snapshot = before.read_text()
            with self.assertRaisesRegex(RuntimeError, "Receipt directory already exists"):
                organise(client, directory)
            self.assertEqual(before.read_text(), snapshot)
            self.assertEqual(len(client.patches), 2)

    def test_unknown_category_stops_before_collection_or_item_writes(self):
        client = MemoryClient()
        client.items["REG"]["data"]["extra"] = "NeuroNZ Record ID: NZNEURO-001\nSource category: Unknown"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "category.*review"):
                organise(client, directory)
        self.assertEqual(client.children, [])
        self.assertEqual(client.patches, [])

    def test_readback_metadata_loss_fails_and_keeps_snapshot_and_receipt(self):
        client = MemoryClient()
        patch = client.patch_item
        def corrupt(key, version, fields):
            patch(key, version, fields)
            client.items[key]["data"]["title"] = "Wrong title"
        client.patch_item = corrupt
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "title"):
                organise(client, directory)
            snapshot = json.loads(next(Path(directory).rglob("before.json")).read_text())
            self.assertEqual(snapshot["items"][0]["data"]["title"], "Registry 2020")
            receipt = json.loads(next(Path(directory).rglob("receipt.json")).read_text())
            self.assertEqual(receipt["status"], "failed")
            self.assertEqual(receipt["items"][0]["status"], "written_unverified")

    def test_title_date_or_pmid_alone_does_not_classify_a_publication(self):
        data = MemoryClient().items["PUB"]["data"]
        self.assertEqual(source_type(data), PUBLICATIONS)
        del data["publicationTitle"]
        self.assertIsNone(source_type(data))
        self.assertIsNone(source_type({"title": "Registry report 2026", "itemType": "webpage", "PMID": "123"}))

    def test_tag_normalization_does_not_duplicate_existing_tags(self):
        data = {"collections": ["F"], "tags": [{"tag": f"source-type:{PUBLICATIONS}", "type": 0},
                {"tag": "type:publication"}, {"tag": "category:Journal Article"}, {"tag": "source:pubmed"}]}
        self.assertEqual(filing_patch(data, "F", PUBLICATIONS), {})
