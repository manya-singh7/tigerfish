"""Choose up to MAX_PAGES pages of a report for the paid checks. Free: no model calls.

parse_range("23-40, 112")  -> [23, ..., 40, 112] (pages that exist, in order, deduplicated)
headings(pages)            section headings found on the pages themselves: short lines near
                           the top of a page, in capitals or numbered ("4.2 Biodiversity"),
                           not repeated on many pages (running headers are dropped), not on
                           the contents pages (dot leaders)
quick_picks(pages)         one pick per topic (Biodiversity, Baseline, Impacts, ...): the
                           section under a matching heading when the report has one, else the
                           pages that mention the topic most. Each pick holds at most
                           MAX_PAGES pages; a longer section keeps its densest pages.
default_pick(pages)        nothing chosen: the pages with the most numbers + units and Latin
                           species names (names count at most MAX_NAME_POINTS per page, so
                           species lists do not crowd out figure-dense prose) (what the claim and contradiction checks work on),
                           skipping lab sheets, forms and Hindi pages (tigerfish/scope.py)
"""

import re
from collections import Counter

from tigerfish import claims, scope, species_pages

MAX_PAGES = 30
MAX_NAME_POINTS = 6       # species names count at most this much per page
TOPICS = [
    ("Biodiversity", r"biodiversity|biological environment|ecology|flora|fauna|wildlife|"
                     r"forest|marine (?:ecology|biology)|avifauna|mammal"),
    ("Baseline", r"baseline|description of (?:the )?environment|existing environment|"
                 r"environmental setting|physical environment"),
    ("Impacts", r"impacts?|mitigation"),
    ("Project description", r"description of (?:the )?project|project description"),
    ("Management plan", r"environmental management plan|\bEMP\b|monitoring programme|"
                        r"monitoring program"),
    ("Executive summary", r"executive summary"),
]
HEAD_LINES = 8           # lines at the top of a page where a heading may be
MAX_HEADING_WORDS = 10
REPEATED = 3             # a line on more pages than this is a running header, not a heading
NUMBERED = re.compile(r"^(?:chapter\s+[\dIVX]+[:.\-–]?\s*|[\dIVX]+(?:\.\d+){0,2}\.?\s+|[A-H]\.\s+)",
                      re.IGNORECASE)


def parse_range(text, n_pages, limit=MAX_PAGES):
    """"23-40, 112" -> ([pages], error or None). Pages outside 1..n_pages are an error."""
    out, bad = [], []
    for part in re.split(r"[,;\s]+(?=\d)", str(text or "").strip()):
        part = part.strip().strip(",;")
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*[-–to]+\s*(\d+)", part) or re.fullmatch(r"(\d+)", part)
        if not m:
            bad.append(part)
            continue
        a = int(m.group(1))
        b = int(m.group(2)) if m.lastindex == 2 else a
        if a > b:
            a, b = b, a
        if a < 1 or b > n_pages:
            return [], f"pages must be between 1 and {n_pages}"
        out += [p for p in range(a, b + 1) if p not in out]
    if bad:
        return [], f"could not read: {', '.join(bad)} (write e.g. 23-40, 112)"
    if len(out) > limit:
        return out[:limit], f"more than {limit} pages: the first {limit} are used"
    return out, None


def _is_contents(text):
    return len(re.findall(r"\.{5,}", text)) >= 5


def _heading_candidates(page):
    lines = [" ".join(l.split()) for l in (page.get("text") or "").splitlines()]
    lines = [l for l in lines if l][:HEAD_LINES]
    out = []
    for l in lines:
        words = l.split()
        if not (2 <= len(words) <= MAX_HEADING_WORDS) or re.search(r"\.{3,}|\d{3,}", l):
            continue
        letters = [c for c in l if c.isalpha()]
        if len(letters) < 6:
            continue
        caps = sum(c.isupper() for c in letters) / len(letters) > 0.8
        if caps or NUMBERED.match(l):
            out.append(NUMBERED.sub("", l).strip(" :.-–"))
    return out


def headings(pages):
    """[(page, heading)] in page order (contents pages and running headers left out)."""
    found = [(p["page"], h) for p in pages if not _is_contents(p.get("text") or "")
             for h in _heading_candidates(p)]
    seen = Counter(h.lower() for _, h in found)
    return [(n, h) for n, h in found if seen[h.lower()] <= REPEATED and len(h) >= 6]


def page_score(page):
    """Numbers + units (rule claims) and Latin names: what the paid checks work on."""
    text = page.get("text") or ""
    if not text.strip() or scope.skip_reason(page):
        return 0
    nums = len(claims.rule_claims(page["page"], text, []))
    names = len(species_pages.candidate_names(text)) if species_pages.BINOMIAL.search(text) else 0
    # A species list has dozens of names per page but few figures that can disagree with
    # another page; capping the names' share keeps figure-dense prose in the default pick.
    return nums + min(names, MAX_NAME_POINTS)


def densest(pages, numbers, limit=MAX_PAGES):
    by_no = {p["page"]: p for p in pages}
    scored = sorted(numbers, key=lambda n: -page_score(by_no[n]))
    return sorted(scored[:limit])


def default_pick(pages, limit=MAX_PAGES):
    return densest(pages, [p["page"] for p in pages], limit)


def fmt_pages(numbers):
    """[3,4,5,9] -> "3-5, 9"."""
    out, run = [], []
    for n in sorted(numbers):
        if run and n == run[-1] + 1:
            run.append(n)
        else:
            if run:
                out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
            run = [n]
    if run:
        out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
    return ", ".join(out)


def quick_picks(pages, limit=MAX_PAGES):
    """[{"label", "pages", "how"}] for the topics this report has."""
    heads = headings(pages)
    last = pages[-1]["page"] if pages else 0
    starts = sorted({n for n, _ in heads})
    out = []
    for label, pattern in TOPICS:
        rx = re.compile(pattern, re.IGNORECASE)
        hits = [(n, h) for n, h in heads if rx.search(h)]
        chosen, how = [], ""
        for n, h in hits:
            end = next((s for s in starts if s > n), last + 1) - 1
            chosen += [p for p in range(n, end + 1) if p not in chosen]
        if chosen:
            first = hits[0]
            how = (f"under the heading “{first[1]}” (p.{first[0]})"
                   + (f" and {len(hits) - 1} more" if len(hits) > 1 else ""))
        else:
            counts = {p["page"]: len(rx.findall(p.get("text") or "")) for p in pages
                      if not _is_contents(p.get("text") or "") and not scope.skip_reason(p)}
            chosen = [n for n, c in sorted(counts.items(), key=lambda x: -x[1]) if c >= 3][:limit]
            how = "no matching heading found: the pages that mention it most"
        if not chosen:
            continue
        if len(chosen) > limit:
            chosen = densest(pages, chosen, limit)
            how += f"; the {limit} pages with the most figures and species names"
        out.append({"label": label, "pages": sorted(chosen), "how": how})
    return out
