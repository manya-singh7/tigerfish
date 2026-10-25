"""One shape for findings from every check, used by the app, the export and the letter.

finding = {id, check, check_name, grade (RED | ORANGE | INFO), title, message,
           quotes: [{page, text, where?}], evidence: [{label, value, url?}],
           why, clear, known_issue, images: [relative png paths]}
"""

CHECK_NAMES = {
    "contradiction": "Internal contradiction", "recycled_figure": "Recycled figure",
    "species_range": "Species out of range", "iucn_status": "IUCN status",
    "legal_schedule": "Legal schedule", "copy_paste": "Copied text",
    "borrowed_text": "Borrowed text",
}
CLEAR = {
    "contradiction": "A statement in the report that the two passages cover different areas, "
                     "dates or scopes, or a correction of one of them.",
    "recycled_figure": "Separate survey data for each site, or a note that one common "
                       "source covers all of them.",
    "species_range": "A dated record (specimen, photo or publication) of this species within "
                     "100 km of the site.",
    "iucn_status": "The report stating which IUCN assessment it used, or the current category.",
    "legal_schedule": "The species' schedule under the Wild Life (Protection) Act as amended in 2022.",
    "copy_paste": "A citation for the matching text, or site-specific data for this project.",
    "borrowed_text": "A citation to the source near this text.",
}
GRADE_ORDER = {"RED": 0, "ORANGE": 1, "INFO": 2}


def finding(fid, check, grade, title, message, quotes, evidence, why, known_issue=None):
    return {"id": fid, "check": check, "check_name": CHECK_NAMES[check], "grade": grade,
            "title": title, "message": message, "quotes": quotes, "evidence": evidence,
            "why": why, "clear": CLEAR[check], "known_issue": known_issue, "images": []}


def contradiction_findings(con_findings, known=None):
    """Findings from tigerfish.contradictions (RED/ORANGE only). known: {finding id: issue id}."""
    out = []
    for f in con_findings:
        if f["grade"] not in ("RED", "ORANGE"):
            continue
        check = "recycled_figure" if f["type"] == "recycled_figure" else "contradiction"
        pages = ", ".join(map(str, f["pages"]))
        title = (f"Same figure for different places, pages {pages}" if check == "recycled_figure"
                 else f"Pages {' and '.join(map(str, f['pages']))} disagree")
        # The model's reason is shown once, as "Why flagged"; evidence says how it was checked.
        evidence = [{"label": "Checked by",
                     "value": "Nemotron Ultra, reading both full pages"
                              + (f"; {f['explanation_hits']} possible explanation words searched"
                                 if f.get("explanation_hits") else "")}]
        if f.get("breakdown"):
            evidence.append({"label": "Other figures shared by these pages",
                             "value": ", ".join(f"{v:g}" for v in f["breakdown"])})
        if f.get("explanation_quote"):
            evidence.append({"label": f"Possible explanation in the report (p.{f['explanation_page']})",
                             "value": f["explanation_quote"]})
        if f.get("evidence_note"):
            evidence.append({"label": "Note", "value": f["evidence_note"]})
        out.append(finding(f["id"], check, f["grade"], title, f["message"],
                           [{"page": q["page"], "text": q["text"]} for q in f["quotes"]],
                           evidence, f["reason"], (known or {}).get(f["id"])))
    return out


def sort_findings(findings):
    return sorted(findings, key=lambda f: (GRADE_ORDER.get(f["grade"], 9), f["check"], f["id"]))


def highlight_pages(pdf, quotes_by_page, out_dir, prefix, dpi=110):
    """Render pages with their quotes highlighted (PyMuPDF search_for + highlight annotation).

    quotes_by_page: {page number: [quote, ...]}. Writes <out_dir>/<prefix>_p<NNNN>.png and
    returns {page number: Path}. The PDF itself is not modified or saved.
    """
    import pymupdf
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    with pymupdf.open(pdf) as doc:
        for page_no, quotes in sorted(quotes_by_page.items()):
            if not page_no or page_no > doc.page_count:
                continue
            page = doc[page_no - 1]
            for q in quotes:
                quads = page.search_for(q, quads=True)
                if not quads:   # fall back to the first 8 words (e.g. a typo-repaired quote)
                    quads = page.search_for(" ".join(q.split()[:8]), quads=True)
                if quads:
                    page.add_highlight_annot(quads)
            path = out_dir / f"{prefix}_p{page_no:04d}.png"
            page.get_pixmap(dpi=dpi, annots=True).save(path)
            out[page_no] = path
    return out


def attach_images(findings, images, relative_to=None):
    """Set each finding's images from {page: Path} (relative paths if relative_to is given)."""
    for f in findings:
        paths = [images[q["page"]] for q in f["quotes"] if q.get("page") in images]
        f["images"] = [p.relative_to(relative_to).as_posix() if relative_to else str(p)
                       for p in paths]
    return findings
