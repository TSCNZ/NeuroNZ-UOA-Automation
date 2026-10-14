# NeuroNZ UOA Automation

Private automation repository for keeping the NeuroNZ Zotero collection, QA reports, and WordPress-facing cache up to date.

## What this repo does first

The pipeline imports validated new PubMed evidence and refreshes monitoring outputs:

1. fetches group `6708514`, collection `25TARGNW` and its descendants,
2. parses stable NeuroNZ IDs from Zotero `extra`,
3. generates a Zotero cache,
4. generates a WordPress-shaped catalogue JSON file,
5. generates a completeness report,
6. validates public-readiness quality gates,
7. creates a review queue for records needing attention,
8. monitors registered source pages,
9. discovers candidate records from PubMed and data.govt.nz,
10. checks catalogue primary links,
11. writes a run summary for dissertation/evaluation evidence.

GitHub Actions enables `ZOTERO_WRITE_ENABLED=true`. New PubMed papers with verified abstracts, clear NZ and neurological relevance, and no matching DOI, PMID, URL, or title in the group library are added to `02 Evidence Log`. Every created item is read back and logged with its Zotero key, evidence ID, `dateAdded`, and `dateModified` in `outputs/zotero_update_manifest.json`. Existing items are preserved. Concurrent pipeline runs are serialized.

Imports require a verified journal title, authors, and publication date in addition to title, abstract, PMID, and relevance checks. PubMed supplies journal abbreviation, ISSN, language, volume, issue, pages, PMCID, and rights when available. Native PMID, library catalogue, and source access date are also recorded. Missing optional source fields are listed in each write receipt; publisher identifiers are not substituted for page numbers. Existing phase2 articles in the target evidence collection with an exact PMID match can have missing bibliography filled using a version-guarded update. Existing populated fields are preserved, and readback verifies both the repair and the retained metadata. These repairs have status metadata_updated_verified in the manifest and run summary.

Candidates that fail relevance checks and data.govt.nz datasets that need catalogue metadata review remain in the review manifest. Source failures are logged and are never imported.

Public data.govt.nz datasets can now be imported into Catalogue Sources when their NZ context, controlled condition, organisation, licence and resource URLs are verified. Condition classification uses actual taxonomy names and reviewed aliases; uncertain conditions remain in review. Existing imported PubMed IDs are rechecked independently of the newest search results. Each run emits metadata_taxonomy_audit.json and includes candidate and taxonomy gaps in review_queue.csv. See docs/gap_register.md for remaining live acceptance and data-review work.

## Zotero target

Source: https://www.zotero.org/groups/6708514/nz_neuro_data_catalogue/collections/25TARGNW/collection

The pipeline reads this collection and its descendants, deduplicates Zotero keys, and classifies records by their NeuroNZ IDs in `extra`. Evidence and condition IDs take precedence over catalogue references. Unclassified records enter catalogue validation so missing IDs remain visible. Attachments, notes, annotations, and descendant collections named `04 Excluded Sources` are excluded. Public API checks confirmed `NeuroNZ_Shared_Collection` and its four child collections in the new group on 13 October 2026. Child collection keys are discovered from the selected collection at runtime. The repository secret must have access to the new group before running the workflow.

## Catalogue source-type folders

The agreed source-type folders sit directly inside `01 Catalogue Sources`:

```text
01 Catalogue Sources
├── Administrative Data
├── National Surveys
├── Research Surveys & Cohort Studies
├── Registries
├── Neurological Workforce Data
├── International Data Systems
├── Use of NZ Neurological Data
├── Published Research
└── Journal Articles
```

The `organise` workflow operation files existing catalogue entries from their explicit source categories and verified PubMed imports from their item type, PMID, import provenance, journal, authors and publication date. It adds memberships and `source-type:*` tags, preserves existing memberships, curated tags, item metadata and original `dateAdded`, and reads every changed item back. It creates no new bibliographic items. The former combined publications folder is renamed to `Journal Articles` without changing its key, and its generated `source-type:*` tag is replaced with the new name. Older category assignments are retained; a publication URL describing a registry or study does not automatically change the source's category.

Future validated PubMed imports are filed in `Journal Articles` and remain in `02 Evidence Log` as the same Zotero item. They carry `type:publication`, `category:Journal Article`, and `source:pubmed` tags. There is no separate PubMed folder. `Published Research` is reserved for non-journal research outputs with an explicit verified category; legacy catalogue categories are not reassigned from title wording alone. An unrecognised dataset category remains in the catalogue for review rather than being assigned an unsupported source type.

`outputs/source_type_inventory.json` counts and lists all nine groups. `outputs/catalogue_source_changes.csv` and `outputs/publication_changes.csv` track the catalogue source groups and verified publications independently against the previous cache. Existing articles are not marked new merely because classification tags were added. `new` means first seen in the cache, rather than recently published or having a year in its title. PubMed search coverage is currently limited to the latest 20 results plus already imported PMIDs; incremental search pagination remains future work.

To apply or verify organisation:

```bash
gh workflow run phase2-automation.yml --repo TSCNZ/NeuroNZ-UOA-Automation --ref main -f operation=organise
```

This operation saves a before-snapshot and per-item receipts privately on the runner under `outputs/catalogue_organisation/<run-id>-<attempt>/`, then refreshes reports with source imports disabled. Full organisation snapshots and item receipts are excluded from Git and uploaded artifacts; `outputs/catalogue_organisation_summary.json` publishes verification counts and folder keys only. The runner's private snapshots are ephemeral. Unknown categories, duplicate named folders, version conflicts or readback mismatches stop the operation. Routine refresh runs require the publications folder to exist before importing articles.

## Repository secrets

Add this GitHub repository secret:

| Secret | Purpose |
|---|---|
| `ZOTERO_API_KEY` | Zotero API key with read and write access to group `6708514` |

Do not commit API keys or WordPress credentials.

## Manual local run

```bash
export ZOTERO_API_KEY="your-read-only-key"
python3 -m neuronz_automation.run_phase2
```

Outputs are written to `outputs/`.
Local runs remain read-only unless `ZOTERO_WRITE_ENABLED=true` is explicitly set.

Main outputs:

| File | Purpose |
|---|---|
| `outputs/zotero_cache.json` | Normalised cache of Zotero catalogue, evidence, and taxonomy records. |
| `outputs/wordpress_neuro_resources.json` | WordPress-shaped catalogue records. |
| `outputs/catalogue_completeness_report.csv` | Field coverage report. |
| `outputs/validation_failures.csv` | Blocker/review issues from quality gates. |
| `outputs/review_queue.csv` | Records requiring human decision before public use. |
| `outputs/changed_records.csv` | New/changed/unchanged catalogue records compared with the previous committed output. |
| `outputs/candidate_records.csv` | New source candidates from PubMed and data.govt.nz for review. |
| `outputs/source_fetch_log.csv` | Status of registered source monitoring checks. |
| `outputs/catalogue_link_status.csv` | Status of primary catalogue URLs. |
| `outputs/latest_run_summary.json` | Top-level run summary for audit and dissertation evidence. |

## GitHub Actions

Workflow:

```text
.github/workflows/phase2-automation.yml
```

It supports:

1. manual runs through `workflow_dispatch`,
2. weekly scheduled runs,
3. artifact upload of generated outputs,
4. optional commit of changed output files.

## Documentation

Planning documents from the project repository are stored in `docs/`.
