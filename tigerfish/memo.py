"""Reviewer's memo: Nemotron Ultra reads the whole report in one call and writes the memo a senior
EIA reviewer would: up to MAX_ISSUES cross-chapter issues, each with page citations and quotes.

Every quote is checked against the page text (fulltext.verify). An issue keeps only its
verified citations; an issue with none moves to "Unverified reasoning (not checked)". The
reasoning text of an issue is the model's and is labelled as not checked.
"""

import re
import time

from tigerfish import fulltext, llm

MAX_ISSUES = 10
MAX_TOKENS = 20_000          # reasoning + the JSON memo
UNVERIFIED_TITLE = "Unverified reasoning (not checked)"
# Words a neutral accuracy check never uses about a report or its authors.
ACCUSATORY = re.compile(r"\b(fraud\w*|lie|lies|lying|liars?|deliberate(?:ly)?|intentional(?:ly)?|"
                        r"cover[- ]?up|mislead\w*|deceiv\w*|decept\w*|falsif\w*|fabricat\w*|"
                        r"dishonest\w*|sham|bogus)\b", re.IGNORECASE)

TASK = f"""Write the memo a senior reviewer would write after reading this whole report.
List up to {MAX_ISSUES} issues that a reviewer should verify, most important first. Prefer
cross-chapter issues: a figure, finding or commitment on one page that disagrees with, or is not
supported by, another part of the report; baseline studies that do not cover what the impact
chapters rely on; impacts that are asserted but not assessed; mitigation that does not match
the impact it is meant to address.

For each issue give 2 to 4 citations, each a page number and a quote copied character for
character from that page. Use neutral wording ("the report states ... ; p.N states ... ; verify
which applies"). Return JSON only:
{{"issues": [{{"title": "short neutral title",
  "category": "contradiction | baseline_gap | missing_assessment | unsupported_claim | other",
  "summary": "2-4 sentences: what the report states, where, and what to verify",
  "citations": [{{"page": 123, "quote": "exact words from p.123"}}],
  "reasoning": "1-3 sentences on why this matters for the review"}}]}}"""


def run(pages, log=print):
    """Call Ultra once (estimate printed first) and return the checked memo dict."""
    rt = fulltext.report_text(pages)
    msgs = fulltext.messages(rt["text"], TASK)
    started = time.time()
    reply = fulltext.call(msgs, MAX_TOKENS, "memo", cached_share=1.0, log=log)
    raw = fulltext.parse_json(reply["content"])
    memo = check(raw, fulltext.page_texts(pages))
    memo.update(raw_reply=raw, model=llm.ULTRA, pages_included=len(rt["pages"]), first_page=rt["pages"][0],
                last_page=rt["pages"][-1], skipped=rt["skipped"], cost=reply["cost"],
                latency_s=reply.get("seconds") or round(time.time() - started, 1),
                finish_reason=reply.get("finish_reason"))
    return memo


def check(raw, texts):
    """Verify every citation; split issues into verified ones and unverified reasoning."""
    issues, unverified, n_cites, n_ok, n_moved = [], [], 0, 0, 0
    for item in (raw.get("issues") or [])[:MAX_ISSUES]:
        cites = [fulltext.verify(c, texts) for c in item.get("citations") or []]
        ok = [c for c in cites if c["verified"]]
        n_cites += len(cites)
        n_ok += len(ok)
        n_moved += sum(1 for c in ok if "cited_page" in c)
        base = {"title": str(item.get("title") or "").strip(),
                "category": str(item.get("category") or "other").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "reasoning": str(item.get("reasoning") or "").strip()}
        base["wording_flags"] = sorted({m.lower() for m in ACCUSATORY.findall(
            " ".join((base["title"], base["summary"], base["reasoning"])))})
        if ok:
            issues.append({**base, "citations": ok,
                           "unverified_citations": [c for c in cites if not c["verified"]],
                           "pages": sorted({c["page"] for c in ok})})
        else:
            unverified.append({**base, "citations_tried": cites})
    return {"issues": issues, "unverified_reasoning": unverified,
            "stats": {"issues_returned": len(raw.get("issues") or []), "issues_verified": len(issues),
                      "moved_to_unverified": len(unverified), "citations": n_cites,
                      "citations_verified": n_ok, "page_corrected": n_moved}}
