"""Source-reviewed corrections for legacy catalogue research-report records."""

from .parsing import parse_extra

REVIEWED_REPORTS = {
    "NZNEURO-062": {
        "title": "Dementia Economic Impact Report (DEIR) 2020/2021",
        "old_url": "https://alzheimers.org.nz/explore/advocacy/facts-and-figures/",
        "url": "https://cdn.alzheimers.org.nz/wp-content/uploads/2021/09/Dementia-Economic-Impact-Report-2020.pdf",
        "verification": "https://alzheimers.org.nz/explore/advocacy/research/",
        "publication_title": "Dementia Economic Impact Report 2020",
        "date": "2021-09",
        "note": "Report cover confirms September 2021; 2020 is the report reference year.",
    },
    "NZNEURO-063": {
        "title": "NZIER Economic Burden of Stroke (2021)",
        "old_url": "https://www.stroke.org.nz/understanding-stroke/statistics-data/",
        "url": "https://www.nzier.org.nz/publications/the-social-and-economic-costs-of-stroke-in-new-zealand-2020-update",
        "verification": "https://www.stroke.org.nz/stories-and-articles/articles/strokes-will-cost-new-zealand-11-billion-this-year/",
        "publication_title": "The social and economic costs of stroke in New Zealand: 2020 update",
        "date": "2020-07-29",
        "note": "Publisher lists 29 July 2020; the existing title refers to 2021 media coverage. Publisher entry verified; full report PDF not located.",
    },
}


def reviewed_report_patch(data):
    """Apply only explicit reviewed identities; preserve existing Extra and curated dates."""
    extra = parse_extra(data.get("extra", ""))
    if extra.get("NeuroNZ Evidence ID"):
        return {}
    review = REVIEWED_REPORTS.get(extra.get("NeuroNZ Record ID"))
    if not review:
        return {}
    if (data.get("title") != review["title"] or data.get("itemType") == "journalArticle"
            or data.get("url") not in {review["old_url"], review["url"]}
            or review["old_url"] not in extra.get("All source links", "")):
        raise RuntimeError("Reviewed research-report identity changed; inspect source before reclassification")
    additions = {
        "Record role": "Published Research",
        "Publication format": "Research report",
        "Verified publication title": review["publication_title"],
        "Publication verification source": review["url"],
        "Publication verification context": review["verification"],
        "Publication verification note": review["note"],
        "Publication classification reviewed": "2026-10-15",
    }
    missing = []
    for field, value in additions.items():
        if extra.get(field) and extra[field] != value:
            raise RuntimeError(f"Existing curated {field} conflicts with reviewed research-report correction")
        if not extra.get(field):
            missing.append(f"{field}: {value}")
    patch = {}
    if missing:
        patch["extra"] = "\n".join(filter(None, [data.get("extra", ""), *missing]))
    if data.get("url") != review["url"]:
        patch["url"] = review["url"]
    if not data.get("date"):
        patch["date"] = review["date"]
    return patch
