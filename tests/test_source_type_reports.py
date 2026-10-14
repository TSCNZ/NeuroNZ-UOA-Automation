import unittest
from copy import deepcopy

from neuronz_automation.catalogue_types import PUBLICATIONS
from neuronz_automation.source_type_reports import source_type_reports


def record(key, article=False):
    return {"zotero_key": key, "stable_id": key, "title": key, "item_type": "journalArticle" if article else "webpage",
            "pmid": "123" if article else "", "primary_link": "", "date_added": "2026-01-01", "date_modified": "2026-01-01",
            "zotero_version": 1, "tags": [], "bibliography": {"publicationTitle": "Journal", "creators": [{"name": "Author"}], "date": "2026"},
            "extra": {"NeuroNZ Evidence ID": key, "Source candidate ID": "pubmed:123"} if article else {
                "NeuroNZ Record ID": key, "Source category": "Registry"}}


class SourceTypeReportTests(unittest.TestCase):
    def test_independent_change_reports_include_new_updated_and_removed_items(self):
        source, publication = record("S"), record("P", True)
        updated = deepcopy(source)
        updated["title"] = "Updated registry"
        inventory, sources, publications = source_type_reports(
            {"catalogue": [source, record("REMOVED")]}, {"catalogue": [updated], "evidence": [publication]})
        self.assertEqual(inventory[PUBLICATIONS]["count"], 1)
        self.assertEqual(inventory["Registries"]["count"], 1)
        self.assertEqual({row["change_status"] for row in sources}, {"removed", "changed"})
        self.assertEqual(publications[0]["change_status"], "new")

    def test_existing_article_is_not_new_when_classification_tags_are_added(self):
        original = record("P", True)
        updated = deepcopy(original)
        updated["tags"] = ["source:pubmed"]
        inventory, sources, publications = source_type_reports({"evidence": [original]}, {"evidence": [updated, updated]})
        self.assertEqual(inventory[PUBLICATIONS]["count"], 1)
        self.assertEqual(sources, [])
        self.assertEqual(publications[0]["change_status"], "changed")
