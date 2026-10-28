"""Paper trail: the project's own official documents, found on official sites with Tavily.

Who the project is comes only from the report itself (PROFILES): its project name terms,
proposal number(s) and state, each with the report page and quote it was read from. Nothing
carries over between reports: a report whose text gives no proposal number or state is
searched without one.

1. map      Tavily map with natural-language instructions on each official site (MoEFCC's
            PARIVESH / environmentclearance.nic.in, moef.gov.in, and the state pollution
            control board / committee site for the report's state).
2. crawl    Tavily crawl with the same instructions on the same sites (pages + text).
3. search   Tavily search restricted to official domains (those sites plus any .gov.in /
            .nic.in page) for the proposal number and for each document type.
4. links    Document links (PDF / download links) on official pages that name the project
            are followed one step.
5. extract  Every candidate URL is read with Tavily extract (basic, then advanced for pages
            basic extraction cannot read).
6. keep     A document is kept only if its text names the project (all name-term groups in one
            sentence) or its proposal number. Kept: url, title, date (only if the page states
            it, with that text), document type, and the exact quote that names the project,
            checked against the extracted text (the Public record rule). Everything else is
            dropped and counted, with the reason.

The granted Terms of Reference, if found, is split into its pages ("Page N of M") for the
ToR promises check. Contacts of the authorities a member of the public writes to are read
from official pages by tigerfish.authority.

All Tavily calls go through copycheck.tavily_call (cached, credit-capped; credits as Tavily
reports them per response). Results: results/paper_trail_<report>.json (the app reads only that).
"""

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import unquote, urldefrag

from tigerfish import claims as claims_mod
from tigerfish import copycheck, knowable, tavily_usage
from tigerfish.official_record import host

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
PAGES_DIR = ROOT / "cache" / "pages"          # report page text, read at build time only

CENTRAL_SITES = ["parivesh.nic.in", "environmentclearance.nic.in", "moef.gov.in"]
# State pollution control board / committee sites, by the state the report names.
STATE_SITES = {"Andaman and Nicobar Islands": ["dstpcc.andamannicobar.gov.in"],
               "Tamil Nadu": ["tnpcb.gov.in"],
               "Puducherry": ["dste.py.gov.in"]}
OFFICIAL_SUFFIXES = (".gov.in", ".nic.in")
OFFICIAL_EXTRA = ["sansad.in"]                # Parliament (Lok Sabha / Rajya Sabha replies)

MAX_CREDITS = 90            # per report
MAP_LIMIT = 40
CRAWL_LIMIT = 15
MAX_FROM_MAP = 20           # map URLs extracted per site (document-like URLs first)
MAX_LINKS = 12              # document links followed per report
SEARCH_RESULTS = 8
QUOTE_CHARS = 320
HEAD_CHARS = 3000           # start of a document: where its type and date are read

DOC_TYPES = ["ToR letter", "EAC/SEAC minutes", "EAC/SEAC agenda", "Public hearing notice",
             "Public hearing proceedings", "Environmental clearance letter", "Compliance report",
             "Parliament reply", "Press release", "Application (Form 1 / Form 2)", "EIA report", "Pre-feasibility report",
             "Proposal status page", "Other official page"]
SEARCH_TYPES = {   # document type -> words added to the project's name in a search
    "ToR letter": "terms of reference letter",
    "EAC/SEAC minutes": "expert appraisal committee minutes",
    "Public hearing notice": "public hearing notice",
    "Public hearing proceedings": "public hearing proceedings minutes",
    "Environmental clearance letter": "environmental clearance letter",
    "Compliance report": "compliance report environmental clearance conditions",
}

# ---------- report identity: only from the report's own text ----------

PROFILES = {
    "great_nicobar_2021_draft": {
        "pages": "great_nicobar_2021_draft_eia",
        "name": "Great Nicobar Island holistic development (ICTT, airport, township, power plant)",
        "search_name": "Great Nicobar ANIIDCO International Container Transshipment Terminal",
        # A document names the project if one sentence has a term from every group.
        "name_groups": [["great nicobar"],
                        ["transshipment terminal", "transhipment terminal", "ictt", "aniidco",
                         "greenfield international airport", "holistic development"]],
        "facts": [
            {"fact": "proposal", "value": "IA/AN/NCP/201159/2021", "page": 45,
             "quote": "the recommended TOR for the proposal no: IA/AN/NCP/201159/2021"},
            {"fact": "tor_letter", "value": "F.No.10/17/2021-IA.III dated 25th May 2021", "page": 44,
             "quote": "The EIA report is prepared based on the TOR conditions issued by MoEF&CC vide "
                      "F.No.10/17/2021-IA.III dated 25th May 2021"},
            {"fact": "state", "value": "Andaman and Nicobar Islands", "page": 49,
             "quote": "propose Holistic Development of Great Nicobar Island in Andaman and Nicobar Islands"},
            {"fact": "name", "value": "Holistic Development of Great Nicobar Island", "page": 49,
             "quote": "propose Holistic Development of Great Nicobar Island in Andaman and Nicobar Islands"},
        ],
    },
    "indira_point_table_3_16": {
        "pages": None,       # only the published table and its caption exist
        "name": "Indira Point REIA (WAPCOS)",
        "search_name": "Indira Point WAPCOS rapid environmental impact assessment",
        "name_groups": [["indira point"], ["wapcos", "reia"]],
        "facts": [
            {"fact": "name", "value": "WAPCOS Indira Point REIA", "page": None,
             "quote": "Table 3.16 of the WAPCOS Indira Point REIA (Apr 2026)"},
        ],
        "note": ("Only Table 3.16 and its published caption are available for this report: they "
                 "give no proposal number and no state, so the search uses the project name only "
                 "and no state pollution control board site."),
    },
    # Second report on main (tigerfish/sites.py); runs once it is in results/index.json.
    "cuddalore_port_2026_draft": {
        "pages": "cuddalore_port_2026_draft_eia",
        "name": "Expansion of Cuddalore Port (Mahathi Cuddalore Port and Maritime Pvt Ltd)",
        "search_name": "Cuddalore Port expansion Mahathi",
        "name_groups": [["cuddalore port"], ["expansion", "mahathi", "mcpmpl"]],
        "facts": [
            {"fact": "proposal", "value": "IA/TN/INFRA1/564208/2026", "page": 490, "quote": None},
            {"fact": "proposal", "value": "IA/TN/INFRA1/553077/2025", "page": 486, "quote": None},
            {"fact": "state", "value": "Tamil Nadu", "page": 1,
             "quote": "Expansion of Cuddalore Port, Cuddalore district, Tamil Nadu"},
        ],
    },
}


def load_pages(stem):
    """{page: text} from cache/pages/<stem>/pages.jsonl, or {} if it is not here."""
    path = PAGES_DIR / stem / "pages.jsonl" if stem else None
    if not path or not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {p["page"]: p.get("text") or "" for p in map(json.loads, f)}


def identity(report_id, report=None, pages=None):
    """The project's identity with each fact checked against the report's own text.
    A fact is used only if its value (and quote, when given) is on the stated page; for a
    report without page text (a published table), against its title and source line."""
    prof = PROFILES[report_id]
    if pages is None:
        pages = load_pages(prof.get("pages"))
    if not prof.get("pages") and report is not None:
        pages = {None: f"{report.get('title', '')} {report.get('source', '')}"}
    facts, unchecked = [], []
    for f in prof["facts"]:
        text = claims_mod.normalize(pages.get(f["page"], ""))
        quote = f.get("quote")
        if not quote and f["value"] in text:          # quote = the sentence around the value
            quote = sentence_around(text, text.find(f["value"]), len(f["value"]))
        ok = bool(text) and f["value"].split(" dated")[0] in text and (not quote or
                                                                        claims_mod.normalize(quote) in text)
        if f["fact"] == "state":                       # the quote must name the state
            ok = ok and bool(quote) and f["value"].lower() in quote.lower()
        (facts if ok else unchecked).append({**f, "quote": quote})
    proposals = [f["value"] for f in facts if f["fact"] == "proposal"]
    state = next((f["value"] for f in facts if f["fact"] == "state"), None)
    return {"name": prof["name"], "search_name": prof["search_name"], "name_groups": prof["name_groups"],
            "proposals": proposals, "state": state, "facts": facts, "unchecked": unchecked,
            "note": prof.get("note", "")}


def sites_for(ident):
    return CENTRAL_SITES + STATE_SITES.get(ident["state"] or "", [])


def is_official(url):
    h = host(url)
    return h.endswith(OFFICIAL_SUFFIXES) or any(h == d or h.endswith("." + d) for d in OFFICIAL_EXTRA)


def canonical(url):
    u = unquote(urldefrag(url or "")[0]).strip()
    return re.sub(r"^http://", "https://", u)


# ---------- reading a document ----------

def plain(raw):
    """Normalized plain text of extracted markdown (quotes are copied from this)."""
    return claims_mod.normalize(knowable.plain_text(raw or ""))


SHORT_QUOTE_WORDS = 8      # a "sentence" shorter than this ("Proposal No. X.") gets context
CONTEXT_CHARS = 140


def _snap(text, left, right):
    """Move left / right inward to word boundaries."""
    while 0 < left < len(text) and text[left - 1] != " ":
        left += 1
    while left < right < len(text) and text[right] != " ":
        right -= 1
    return left, right


def sentence_around(text, start, length, limit=QUOTE_CHARS, widen=True):
    """The sentence containing text[start:start+length], cut to `limit` characters around it.
    If that sentence is very short (an abbreviation like "No." ends it early), a window of
    words around the match is used instead, so the quote can be checked on the page."""
    left = max(text.rfind(". ", 0, start), text.rfind("| ", 0, start))
    left = 0 if left < 0 else left + 2
    right = text.find(". ", start + length)
    right = len(text) if right < 0 else right + 1
    if widen and len(text[left:right].split()) < SHORT_QUOTE_WORDS:
        left, right = _snap(text, max(0, start - CONTEXT_CHARS),
                            min(len(text), start + length + CONTEXT_CHARS))
    elif right - left > limit:
        mid = start + length // 2
        left, right = _snap(text, max(left, mid - limit // 2), min(right, mid + limit // 2))
    return text[left:right].strip()


def names_project(text, ident):
    """(how, quote) if the text names the project, else (None, None). how: "proposal number"
    or "project name". The quote is copied from the text."""
    for p in ident["proposals"]:
        for form in (p, p.replace("/", "%2F")):
            i = text.find(form)
            if i >= 0:
                return "proposal number", sentence_around(text, i, len(form))
    low = text.lower()
    groups = ident["name_groups"]
    for m in re.finditer(re.escape(groups[0][0]), low):
        strict = sentence_around(text, m.start(), m.end() - m.start(), widen=False).lower()
        if all(any(term in strict for term in g) for g in groups):     # all in one sentence
            return "project name", sentence_around(text, m.start(), m.end() - m.start())
    return None, None


MON = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
       r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
MONTH_NUM = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                         "sep", "oct", "nov", "dec"], 1)}
D = r"(\d{1,2})\s*(?:st|nd|rd|th)?"
DATE_FORMS = [   # (regex, order): day month year | month day year | numeric
    (rf"{D}(?:\s*[-–&]\s*\d{{1,2}}\s*(?:st|nd|rd|th)?)?[\s,.-]*({MON})[a-z]*[\s,.-]*((?:19|20)\d\d)", "dmy"),
    (rf"({MON})[a-z]*\.?\s+{D},?\s*((?:19|20)\d\d)", "mdy"),
    (r"(\d{1,2})[./-](\d{1,2})[./-]((?:19|20)\d\d)", "num"),
]
# A date counts only after a label of the document's own date: "Dated: ...", "Date: ...",
# "held on / during ..." (a date quoted in the text, "Notification ... dated 14.03.2017", does not).
DATE_LABEL = r"(?:(?:dated|date of issue|date)\s*[:\-]|held on|held during|held from|issued on)"


def _to_date(groups, order):
    try:
        if order == "dmy":
            d, m, y = int(groups[0]), MONTH_NUM[groups[1][:3].lower()], int(groups[2])
        elif order == "mdy":
            m, d, y = MONTH_NUM[groups[0][:3].lower()], int(groups[1]), int(groups[2])
        else:
            d, m, y = int(groups[0]), int(groups[1]), int(groups[2])
        return date(y, m, d)
    except (ValueError, KeyError):
        return None


def stated_date(text):
    """(iso date, quote) for the date the document states in its first HEAD_CHARS characters
    after a label like "Dated" or "held on"; (None, None) if it states none."""
    head = text[:HEAD_CHARS]
    for form, order in DATE_FORMS:
        for m in re.finditer(rf"\b{DATE_LABEL}\s*(?:the\s+)?{form}", head, re.IGNORECASE):
            d = _to_date(m.groups(), order)
            if d and 1990 <= d.year <= date.today().year + 1:
                return d.isoformat(), m.group(0).strip()
    return None, None


def doc_type(url, title, text):
    """Document type from its URL, title and opening text (first rule that matches)."""
    h = host(url)
    head = f"{unquote(url)} {title or ''} {text[:HEAD_CHARS]}".lower()
    top = f"{title or ''} {text[:400]}".lower()
    if h == "sansad.in" or h.endswith(".sansad.in") or "lok sabha" in head or "rajya sabha" in head:
        return "Parliament reply"
    if h.endswith("pib.gov.in"):
        return "Press release"
    if re.search(r"\bform[- ]?(?:1|2|i)\b|application for prior environmental clearance", top):
        return "Application (Form 1 / Form 2)"
    if "proposal no" in head and re.search(r"proposal (?:name|details)", head):
        return "Proposal status page"
    if "pre-feasibility report" in top or "prefeasibility report" in top:
        return "Pre-feasibility report"
    if re.search(r"eia[ _-]?(?:report|uncompressed|emp)\b|environmental impact assessment report",
                 head) and "minutes" not in top:
        return "EIA report"
    committee = re.search(r"expert appraisal committee|\beac\b|\bseac\b|appraisal committee", head)
    if "minutes" in head and committee:
        return "EAC/SEAC minutes"
    if "agenda" in head and committee:
        return "EAC/SEAC agenda"
    if "public hearing" in head and re.search(r"proceeding|minutes", head):
        return "Public hearing proceedings"
    if "public hearing" in head and re.search(r"notice|notification", head):
        return "Public hearing notice"
    subject = re.search(r"\bsub(?:ject)?\s*[:.-]", head)
    if subject and "terms of reference" in head and "dated" in head:
        return "ToR letter"
    if subject and re.search(r"environment(?:al)? clearance", head) and "dated" in head:
        return "Environmental clearance letter"
    if re.search(r"compliance report|six[- ]monthly|half[- ]yearly compliance", head):
        return "Compliance report"
    return "Other official page"


GRANTED = re.compile(r"(?:prescribed|granted|accorded|issued)\b[^.]{0,80}\b(?:TOR|Terms of Reference)"
                     r"|(?:TOR|Terms of Reference)\b[^.]{0,80}\b(?:prescribed|granted|accorded)", re.I)


def is_granted_tor(doc, text, ident):
    """A ToR letter for this proposal that states the ToR is prescribed / granted."""
    return (doc["type"] == "ToR letter" and doc["match"] == "proposal number"
            and bool(GRANTED.search(text)))


PAGE_MARK = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)", re.I)


RUNNING_HEADER = re.compile(r"Proposal No\.?\s*[\w/%-]+\s*(?=Page\s+\d+\s+of\s+\d+)", re.I)
LIST_ITEM = re.compile(r"\s(?=\(?(?:[ivxl]{1,7}|\d{1,2}|[a-h])\)\s)")


def split_pages(text):
    """[{page, text}] of a letter extracted as one text, split at its "Page N of M" marks.
    Text before the first mark belongs to that mark's page. The running header ("Proposal
    No. ... Page N of M") is dropped and each numbered condition ("xxxvii) ...") starts a new
    item (a bullet), so one condition's numbers are never read as another's."""
    text = RUNNING_HEADER.sub(" ", text)
    text = LIST_ITEM.sub(" • ", text)
    marks = list(PAGE_MARK.finditer(text))
    if not marks:
        return [{"page": 1, "text": text}]
    pages, start = {}, 0
    for i, m in enumerate(marks):
        n = int(m.group(1))
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        pages[n] = (pages.get(n, "") + " " + text[start:end]).strip()
        start = end
    return [{"page": n, "text": " ".join(PAGE_MARK.sub(" ", t).split())}
            for n, t in sorted(pages.items())]


# ---------- Tavily steps ----------

def instructions(ident):
    pid = f" (proposal {', '.join(ident['proposals'])})" if ident["proposals"] else ""
    return (f"Find official documents about {ident['name']}{pid}: the terms of reference letter, "
            f"expert appraisal committee meeting minutes, public hearing notice and proceedings, "
            f"environmental clearance letter and compliance reports. Skip unrelated projects.")


CONTACT_INSTRUCTIONS = ("Contact pages of this pollution control board / committee: contact us, "
                        "telephone directory, officers, with postal address and email")

DOC_URL = re.compile(r"\.pdf\b|download|writereaddata|filename=|\.docx?\b|minutes|notice|hearing|"
                     r"proceeding|clearance|tor", re.I)
LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)(?:\s+\"([^\"]*)\")?\)")


def doc_links(raw):
    """[(url, anchor text)] of document-like links in extracted markdown."""
    out = []
    for m in LINK.finditer(raw or ""):
        url, label = m.group(2), (m.group(3) or m.group(1) or "").strip()
        if is_official(url) and re.search(r"\.pdf\b|download|writereaddata|filename=|\.docx?\b", url, re.I):
            out.append((url, label))
    return list(dict.fromkeys(out))


class Run:
    """One report's paper-trail run: candidates, texts, and a step log."""

    def __init__(self, ident, budget):
        self.ident, self.budget = ident, budget
        self.found = {}       # canonical url -> {"url", "via", "detail", "title"}
        self.raw = {}         # canonical url -> raw extracted text
        self.steps = []
        self.credits = 0
        self.map_urls = {}    # site -> every official URL its map returned
        self.errors = []      # map / crawl calls that failed twice

    def call(self, endpoint, est, **params):
        """A cached Tavily call. A dropped connection on map / crawl is retried once, then
        logged as an empty result with its error (the run goes on)."""
        for attempt in (1, 2):
            try:
                data = copycheck.tavily_call(endpoint, self.budget, est, **params)
                break
            except copycheck.CreditCapReached:
                raise
            except Exception as e:      # noqa: BLE001 (network / API error)
                if endpoint not in ("map", "crawl") or attempt == 2:
                    if endpoint in ("map", "crawl"):
                        self.errors.append(f"{endpoint} {params.get('url')}: {type(e).__name__}")
                        return {"results": [], "error": type(e).__name__}, 0
                    raise
        c = knowable.credits_of(data, est)
        self.credits += c
        return data, c

    def add(self, url, via, detail="", title=""):
        key = canonical(url)
        if key not in self.found:
            self.found[key] = {"url": url, "via": via, "detail": detail, "title": title}

    def map_site(self, site):
        data, c = self.call("map", 2 * -(-MAP_LIMIT // 10), url=f"https://{site}", max_depth=2,
                            limit=MAP_LIMIT, instructions=instructions(self.ident))
        urls = [u for u in data.get("results") or [] if isinstance(u, str) and is_official(u)]
        self.map_urls[site] = urls
        ranked = sorted(urls, key=lambda u: not DOC_URL.search(u))[:MAX_FROM_MAP]
        for u in ranked:
            self.add(u, "map", site)
        self.steps.append({"tool": "map", "site": site, "results": len(urls), "kept": len(ranked),
                           "credits": c, **({"error": data["error"]} if data.get("error") else {})})

    def crawl_site(self, site):
        data, c = self.call("crawl", 2 * -(-CRAWL_LIMIT // 10) + -(-CRAWL_LIMIT // 5),
                            url=f"https://{site}", max_depth=2, limit=CRAWL_LIMIT,
                            instructions=instructions(self.ident), extract_depth="basic")
        n = 0
        for r in data.get("results") or []:
            if isinstance(r, dict) and r.get("url") and is_official(r["url"]):
                self.add(r["url"], "crawl", site)
                if r.get("raw_content"):
                    self.raw.setdefault(canonical(r["url"]), r["raw_content"])
                n += 1
        self.steps.append({"tool": "crawl", "site": site, "results": n, "credits": c,
                           **({"error": data["error"]} if data.get("error") else {})})

    def search(self, query, label):
        domains = sites_for(self.ident) + ["gov.in", "nic.in"] + OFFICIAL_EXTRA
        data, c = self.call("search", 1, query=query, search_depth="basic", max_results=SEARCH_RESULTS,
                            include_domains=domains)
        n = 0
        for r in data.get("results") or []:
            if is_official(r.get("url")):
                self.add(r["url"], "search", label, r.get("title") or "")
                n += 1
        self.steps.append({"tool": "search", "query": query, "results": n, "credits": c})

    def map_contacts(self, site):
        """Tavily map of a board's site for its contact pages (for tigerfish.authority)."""
        data, c = self.call("map", 2 * -(-MAP_LIMIT // 10), url=f"https://{site}", max_depth=2,
                            limit=MAP_LIMIT, instructions=CONTACT_INSTRUCTIONS)
        urls = [u for u in data.get("results") or [] if isinstance(u, str) and is_official(u)]
        self.steps.append({"tool": "map", "site": site, "purpose": "contact pages",
                           "results": len(urls), "credits": c})
        return urls

    def extract_all(self):
        self.extract_urls([v["url"] for k, v in self.found.items() if k not in self.raw])

    def extract_urls(self, todo):
        """Read URLs not read yet: basic extraction, then advanced for those basic could not read."""
        todo = [u for u in dict.fromkeys(todo) if not self.raw.get(canonical(u))]
        for depth in ("basic", "advanced"):
            pending = [u for u in todo if not self.raw.get(canonical(u))]
            for i in range(0, len(pending), 5):
                chunk = sorted(pending[i:i + 5])
                data, c = self.call("extract", (1 if depth == "basic" else 2), urls=chunk,
                                    extract_depth=depth)
                got = 0
                for r in data.get("results") or []:
                    if r.get("raw_content"):
                        self.raw[canonical(r["url"])] = r["raw_content"]
                        got += 1
                self.steps.append({"tool": f"extract ({depth})", "urls": len(chunk), "results": got,
                                   "credits": c})


def classify(found, raw, ident):
    """(documents, dropped) from the extracted texts."""
    docs, dropped = [], []
    for key, f in found.items():
        url = f["url"]
        base = {"url": url, "host": host(url), "found_via": f["via"], "via_detail": f["detail"]}
        if not is_official(url):
            dropped.append({**base, "why": "not an official site"})
            continue
        text = plain(raw.get(key, ""))
        if len(text) < 40:
            dropped.append({**base, "why": "no readable text (JavaScript-only page or scan)"})
            continue
        how, quote = names_project(text, ident)
        if not how:
            dropped.append({**base, "why": "does not name the project or its proposal number"})
            continue
        exact = knowable.verified_quote(quote, text)
        if not exact:
            dropped.append({**base, "why": "quote not found in the extracted text"})
            continue
        title = f.get("title") or title_of(raw.get(key, ""), url)
        d, d_quote = stated_date(text)
        doc = {**base, "title": title, "type": doc_type(url, title, text), "date": d,
               "date_quote": d_quote, "match": how, "quote": exact, "chars": len(text)}
        doc["granted_tor"] = is_granted_tor(doc, text, ident)
        docs.append(doc)
    docs.sort(key=lambda d: (d["date"] or "9999", d["type"]))
    return docs, dropped


def title_of(raw, url):
    for line in (raw or "").splitlines():
        t = re.sub(r"[#*_|]", " ", line)
        t = " ".join(knowable.plain_text(t).split())
        if len(t) >= 12 and not t.lower().startswith(("image", "toggle", "skip")):
            return t[:120]
    return host(url)


def research_sources(report_id):
    """Official sources of the saved Public record timeline (Tavily research), if any."""
    from tigerfish import public_record
    rec = public_record.load(report_id) or {}
    return sorted({e["source"] for e in rec.get("timeline", []) + rec.get("timeline_dropped", [])
                   if is_official(e.get("source"))})


def run(report_id, report=None, budget=None, pages=None, say=print):
    """The paper trail of one report. Stops (and says so) before the credit cap."""
    ident = identity(report_id, report, pages)
    budget = budget or copycheck.Budget(MAX_CREDITS)
    start_used = budget.used
    r = Run(ident, budget)
    tavily_usage.reset()
    stopped = None
    try:
        for url in research_sources(report_id):
            r.add(url, "research", "Public record timeline")
        for site in sites_for(ident):
            r.map_site(site)
            say(f"  map {site}: {r.steps[-1]['results']} URLs ({r.steps[-1]['credits']} credits)")
            r.crawl_site(site)
            say(f"  crawl {site}: {r.steps[-1]['results']} pages ({r.steps[-1]['credits']} credits)")
        for p in ident["proposals"]:
            r.search(f'"{p}"', "proposal number")
        for kind, words in SEARCH_TYPES.items():
            r.search(f"{ident['search_name']} {words}", kind)
        say(f"  searches: {sum(s['results'] for s in r.steps if s['tool'] == 'search')} official results")
        r.extract_all()
        # one step of links from official pages that name the project
        followed = 0
        for key, f in list(r.found.items()):
            text = plain(r.raw.get(key, ""))
            if not text or not names_project(text, ident)[0]:
                continue
            for url, label in doc_links(r.raw.get(key, "")):
                if followed >= MAX_LINKS or canonical(url) in r.found:
                    continue
                r.add(url, "link", host(f["url"]), label)
                followed += 1
        if followed:
            r.extract_all()
        say(f"  links followed: {followed}")
    except copycheck.CreditCapReached as e:
        stopped = str(e)
        say(f"  stopped: {e}")
    docs, dropped = classify(r.found, r.raw, ident)
    for d in docs:      # the quotes (and stated dates) are what the app shows as evidence
        tavily_usage.used_text(d["quote"], "shown as evidence")
        if d["date_quote"]:
            tavily_usage.used_text(d["date_quote"], "shown as evidence")
    from tigerfish import authority
    try:
        contacts = authority.find(r, ident, docs)
    except copycheck.CreditCapReached as e:
        stopped = stopped or str(e)
        contacts = {}
    tor = next((d for d in docs if d["granted_tor"]), None)
    unusable = [{"site": s["site"], "tool": s["tool"], "error": s.get("error", "")} for s in r.steps
                if s["tool"] in ("map", "crawl") and not s["results"]]
    out = {"report_id": report_id, "searched_on": date.today().isoformat(),
           "identity": ident, "sites": sites_for(ident), "steps": r.steps,
           "documents": docs, "dropped": dropped,
           "drop_counts": count_by(dropped, "why"),
           "unusable": unusable,
           "granted_tor": ({"found": True, "url": tor["url"], "date": tor["date"], "quote": tor["quote"],
                            "title": tor["title"]} if tor else {"found": False}),
           "contacts": contacts,
           "stopped": stopped,
           "tavily": {"credits": r.credits, "credits_spent_this_run": budget.used - start_used,
                      "cached_calls": budget.cached,
                      "features": ["map + instructions", "crawl + instructions", "search include_domains",
                                   "extract basic / advanced"]}}
    out["tavily"]["credits"] = r.credits
    out["efficiency"] = tavily_usage.snapshot()
    out["_raw"] = {canonical(d["url"]): r.raw.get(canonical(d["url"]), "") for d in docs}
    return out


def count_by(rows, key):
    out = {}
    for r in rows:
        out[r[key]] = out.get(r[key], 0) + 1
    return out


def path(report_id):
    return RESULTS / f"paper_trail_{report_id}.json"


def load(report_id):
    p = path(report_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


FOUND_VIA = {"map": "Found via Tavily map", "crawl": "Found via Tavily crawl",
             "search": "Found via Tavily search", "research": "Found via Tavily research",
             "link": "Found via Tavily extract (link on an official page)"}


def timeline(report_id, rec=None, trail=None):
    """One dated list: the Public record timeline events plus every paper-trail document whose
    page states a date. [{date, event, source, host, quote, kind, via}]"""
    from tigerfish import public_record
    rec = rec if rec is not None else (public_record.load(report_id) or {})
    trail = trail if trail is not None else (load(report_id) or {})
    rows = [{"date": e["date"], "event": e["event"], "source": e["source"], "host": e["host"],
             "quote": e["quote"], "kind": "Timeline event", "via": FOUND_VIA["research"]}
            for e in rec.get("timeline", [])]
    for d in trail.get("documents", []):
        if d.get("date"):
            rows.append({"date": d["date"], "event": f"{d['type']}: {d['title']}", "source": d["url"],
                         "host": d["host"], "quote": d["date_quote"], "kind": d["type"],
                         "via": FOUND_VIA.get(d["found_via"], d["found_via"])})
    return sorted(rows, key=lambda x: x["date"])
