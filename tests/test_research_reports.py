import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

from neuronz_automation.catalogue_types import PUBLISHED_RESEARCH, source_type
from neuronz_automation.organise_catalogue import organise
from neuronz_automation.parsing import parse_extra
from neuronz_automation.research_reports import REVIEWED_REPORTS, reviewed_report_patch
from neuronz_automation.source_type_reports import source_type_reports
from test_organise_catalogue import MemoryClient


def report_data(record_id):
    review = REVIEWED_REPORTS[record_id]
    return {"title": review["title"], "itemType": "webpage", "url": review["old_url"], "date": "",
            "collections": ["CAT", "LEGACY-SOURCE", "OTHER"],
            "tags": [{"tag": "category:Use of NZ neurological data"},
                     {"tag": "source-type:Use of NZ Neurological Data"}, {"tag": "curated", "type": 1}],
            "dateAdded": "2026-08-28T00:00:00Z", "dateModified": "2026-08-28T00:00:00Z",
            "extra": f"NeuroNZ Record ID: {record_id}\nSource category: Use of NZ neurological data\n"
                     f"All source links: {review['old_url']}\nDesign type: Economic analysis"}


class ResearchReportTests(unittest.TestCase):
    def test_verified_role_overrides_legacy_category_without_guessing_from_title(self):
        original = report_data("NZNEURO-062")
        correction = reviewed_report_patch(original)
        corrected = {**original, **correction}
        self.assertEqual(source_type(original), "Use of NZ Neurological Data")
        self.assertEqual(source_type(corrected), PUBLISHED_RESEARCH)
        for field, value in parse_extra(original["extra"]).items():
            self.assertEqual(parse_extra(corrected["extra"])[field], value)
        self.assertEqual(corrected["date"], "2021-09")
        self.assertEqual(corrected["dateAdded"], original["dateAdded"])
        self.assertEqual(reviewed_report_patch(corrected), {})
        unreviewed = {**original, "title": "Research report 2021", "extra": original["extra"].replace("NZNEURO-062", "NZNEURO-099")}
        self.assertEqual(reviewed_report_patch(unreviewed), {})
        self.assertEqual(source_type(unreviewed), "Use of NZ Neurological Data")

    def test_conflicting_identity_or_curated_role_blocks_backfill(self):
        for change in ({"title": "Different report"}, {"itemType": "journalArticle"}, {"url": "https://example.org/curated"}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                reviewed_report_patch({**report_data("NZNEURO-062"), **change})
        data = report_data("NZNEURO-062")
        data["extra"] += "\nRecord role: Data source"
        with self.assertRaisesRegex(RuntimeError, "curated Record role"):
            reviewed_report_patch(data)

    def test_populated_date_and_legacy_supporting_evidence_are_preserved(self):
        data = report_data("NZNEURO-062")
        data["date"] = "2021-09-21"
        self.assertNotIn("date", reviewed_report_patch(data))
        data["extra"] += "\nNeuroNZ Evidence ID: E001"
        self.assertEqual(reviewed_report_patch(data), {})

    def test_organisation_backfills_both_reports_without_duplicates_and_is_idempotent(self):
        client = MemoryClient()
        client.children = [{"key": "LEGACY-SOURCE", "data": {"name": "Use of NZ Neurological Data", "parentCollection": "CAT"}}]
        for record_id in REVIEWED_REPORTS:
            client.items[record_id] = {"key": record_id, "version": 1, "data": report_data(record_id)}
        original = deepcopy(client.items)
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"GITHUB_RUN_ID": "reports-test", "GITHUB_RUN_ATTEMPT": "1"}):
                receipt = organise(client, directory)
            self.assertEqual(receipt["folders"][PUBLISHED_RESEARCH]["items"], 2)
            self.assertEqual(receipt["folders"]["Use of NZ Neurological Data"]["items"], 0)
            self.assertEqual(receipt["unique_items_before"], receipt["unique_items_after"])
            for record_id in REVIEWED_REPORTS:
                updated = client.items[record_id]["data"]
                self.assertIn("CAT", updated["collections"])
                self.assertIn("OTHER", updated["collections"])
                self.assertNotIn("LEGACY-SOURCE", updated["collections"])
                self.assertIn({"tag": "curated", "type": 1}, updated["tags"])
                self.assertIn({"tag": "category:Use of NZ neurological data"}, updated["tags"])
                self.assertEqual(updated["dateAdded"], original[record_id]["data"]["dateAdded"])
            first_writes = len(client.patches)
            with patch.dict("os.environ", {"GITHUB_RUN_ID": "reports-test", "GITHUB_RUN_ATTEMPT": "2"}):
                again = organise(client, directory)
            self.assertEqual(again["updated_verified"], 0)
            self.assertEqual(len(client.patches), first_writes)

    def test_existing_report_reclassification_is_changed_not_new_in_tracking(self):
        data = report_data("NZNEURO-062")
        original = {"zotero_key": "EXISTING", "stable_id": "NZNEURO-062", "title": data["title"],
                    "item_type": "webpage", "primary_link": data["url"], "pmid": "", "date_added": data["dateAdded"],
                    "date_modified": data["dateModified"], "bibliography": {}, "extra": parse_extra(data["extra"])}
        corrected = {**original, "extra": parse_extra(reviewed_report_patch(data)["extra"])}
        inventory, sources, publications = source_type_reports({"catalogue": [original]}, {"catalogue": [corrected]})
        self.assertEqual(inventory[PUBLISHED_RESEARCH]["count"], 1)
        self.assertEqual(publications[0]["change_status"], "changed")
        self.assertIn("source_type", publications[0]["changed_fields"])
        self.assertEqual(sources, [])
