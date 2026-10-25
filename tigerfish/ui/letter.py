"""Draft letter (.docx) from confirmed findings: neutral, factual, with page citations."""

import io
from datetime import date

from docx import Document
from docx.shared import Pt, RGBColor

ACCENT = RGBColor(0x0F, 0x5E, 0x5E)


def where(q):
    return f"page {q['page']}" if q.get("page") else q.get("where", "the report")


def build_letter(report, findings):
    """Return .docx bytes. Wording stays neutral: observations and requests to verify."""
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    doc.add_paragraph(date.today().strftime("%d %B %Y"))
    doc.add_paragraph("To,\nThe Member Secretary\nExpert Appraisal Committee\n"
                      "Ministry of Environment, Forest and Climate Change\n[address]")
    title = doc.add_paragraph()
    run = title.add_run(f"Subject: Observations on {report['title']}, request for clarification")
    run.bold = True
    run.font.color.rgb = ACCENT

    doc.add_paragraph("Sir / Madam,")
    doc.add_paragraph(
        f"I have reviewed {report['title']} ({report.get('source', '')}). The points below are "
        f"statements in the report that appear inconsistent with each other or with public "
        f"records. Each point cites the page and the exact text. I request that the project "
        f"proponent and the consultant verify these points and clarify or correct them before "
        f"the report is relied upon.")

    for i, f in enumerate(findings, 1):
        h = doc.add_paragraph()
        r = h.add_run(f"{i}. {f['check_name']}: {f['title']}")
        r.bold = True
        for q in f["quotes"]:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(f"The report states ({where(q)}): ").italic = True
            p.add_run(f"“{q['text']}”")
        doc.add_paragraph(f"Observation: {f['why']}")
        for e in f["evidence"]:
            line = f"{e['label']}: {e.get('value') or ''}"
            if e.get("url"):
                line += f" ({e['url']})"
            doc.add_paragraph(line, style="List Bullet 2")
        doc.add_paragraph(f"Clarification requested: {f['clear']}")

    doc.add_paragraph(
        "These observations were prepared with the help of TigerFish, an automated accuracy "
        "checker, and each point was reviewed by me before inclusion. They are offered so that "
        "the record can be verified and, where needed, corrected.")
    doc.add_paragraph("Yours faithfully,\n\n[Name]\n[Address / organisation]\n[Contact]")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
