"""Who a member of the public writes to about a report, read from official pages only.

hearing     the state pollution control board / committee that holds the public hearing
            (its Member Secretary), from that board's own site (contact / directory pages)
clearance   MoEFCC's Impact Assessment Division (where the Expert Appraisal Committee's
            member secretary sits), from an official document of this project (the address
            block of a MoEFCC letter) and, for an email, an official page that publishes one
            next to the division or the member secretary

Each contact keeps the source URL and the exact quote it was read from (checked against the
extracted text). An email is kept only if it is printed on an official page; nothing is
guessed. A report whose own text names no state gets no state board; one with no proposal
number gets no clearance authority (the appraising authority is not known).

The letter and the RTI pack use these as the addressee, with "check the address before
sending"; without a contact they keep their [placeholders].
"""

import re

from tigerfish import knowable, paper_trail, tavily_usage
from tigerfish.official_record import host

EMAIL = re.compile(r"[\w.\-]+\s*(?:@|\[at\]|\(at\)|\[\s*at\s*\])\s*[\w\-]+"
                   r"(?:\s*(?:\.|\[dot\]|\(dot\))\s*[\w\-]+)+", re.I)
PIN = re.compile(r"\b\d{3}\s?\d{3}\b")
BOARD = re.compile(r"((?:(?:[A-Z][\w.]*|&|and)\s+){1,4}Pollution Control (?:Committee|Board))")
PERSON = re.compile(r"\b(?:Shri|Smt|Sh|Dr|Mr|Ms|Mrs)\.?\s|\b(?:IAS|IFS|DANICS)\b")
CONTACT_URL = re.compile(r"contact|directory|telephone|officer|who.?s.?who|about", re.I)
MOEF_BLOCK = re.compile(r"Ministry of Environment,? Forest and Climate Change\s*\(?\s*Impact Assessment "
                        r"Division\s*\)?[^|]{0,160}?\b\d{3}\s?\d{3}\b", re.I)
CHECK = "Check the address before sending."
WELL_FORMED = re.compile(r"[\w.+-]+@[A-Za-z0-9][\w-]*(?:\.[\w-]+)*\.[A-Za-z]{2,}")


def well_formed(match):
    """The email as printed, if it is well formed; "" for none or a garbled one (e.g. an OCR
    "memsec@-tnpcb.gov.in"): a garbled email is never repaired, that would be a guess.
    Obfuscated forms ("name[at]nic[dot]in") are kept as printed."""
    if not match:
        return ""
    e = " ".join(match.group(0).split())
    if "@" not in e:
        return e
    return e if WELL_FORMED.fullmatch(e) else ""


BOARD_NAMED = re.compile(r"[Pp]ollution [Cc]ontrol|\b[A-Z]{1,4}PC[CB]\b")


def _row_contact(text, role="Member Secretary", must=None):
    """(quote, address, email) from the first table row or text block that names the role
    (and, with `must`, also matches it: e.g. names the board, not another body)."""
    for line in text.split("\n"):
        if role.lower() in line.lower() and "|" in line and (not must or must.search(line)):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # the address: the longest cell that is not the role, an email or a person's name
            options = [c for c in cells if "," in c and role.lower() not in c.lower()
                       and not EMAIL.search(c) and not PERSON.search(c) and len(c) > 15]
            address = max(options, key=len, default="")
            email = EMAIL.search(line)
            quote = " ".join(line.strip().strip("|").split())      # the row as published
            return quote, address, well_formed(email)
    flat = " ".join(text.split())
    for m in re.finditer(re.escape(role), flat, re.I):
        i = m.start()
        block = flat[i:i + 300]
        pin = PIN.search(block)
        quote = block[:pin.end()] if pin else block[:200]
        if must and not must.search(quote):
            continue
        email = EMAIL.search(flat[i:i + 400])
        return quote.strip(), quote[len(role):].strip(" ,:-"), well_formed(email)
    return None, "", ""


def board_name(texts, state):
    """The board's name as its pages print it most often; it must name a word of the state
    (so "Central Pollution Control Board", also mentioned there, is not taken)."""
    words = [w for w in re.findall(r"[a-z]{4,}", (state or "").lower()) if w != "islands"]
    counts = {}
    for t in texts:
        for m in BOARD.finditer(" ".join((t or "").split())):
            name = m.group(1).strip()
            if name[0].isupper() and any(w in name.lower() for w in words):
                counts[name] = counts.get(name, 0) + 1
    return max(counts, key=counts.get) if counts else ""


def hearing_contact(run, ident):
    """The state board's Member Secretary, from contact pages on the state site."""
    sites = paper_trail.STATE_SITES.get(ident["state"] or "", [])
    if not sites:
        return {"found": False, "why": "the report's own text names no state, so no state board site "
                                        "was searched" if not ident["state"] else
                                        f"no state board site is listed for {ident['state']}"}
    urls = [u for site in sites for u in run.map_urls.get(site, []) if CONTACT_URL.search(u)][:6]
    if not urls:            # the project map listed none: map the site for its contact pages
        for site in sites:
            urls += [u for u in run.map_contacts(site) if CONTACT_URL.search(u)]
        urls = urls[:6]
    if not urls:            # map sees nothing (JavaScript site): one search on the board's site
        urls = run.search_urls("Member Secretary contact address email", sites, "authority contact")[:4]
    if urls:
        run.extract_urls(urls)
    texts = {u: knowable.plain_text(run.raw.get(paper_trail.canonical(u), "")) for u in urls}
    own = [t for k, t in run.raw.items() if any(host(k).endswith(s) for s in sites)]
    name = (board_name(texts.values(), ident["state"])          # only the board's own pages
            or board_name(own, ident["state"]) or f"Pollution control board / committee, {ident['state']}")
    for url, text in texts.items():
        quote, address, email = _row_contact(text, must=BOARD_NAMED)
        if not quote:
            continue
        exact = knowable.verified_quote(quote, text)
        if not exact:
            continue
        tavily_usage.used_text(exact, "shown as evidence")
        return {"found": True, "role": "hearing", "to": f"The Member Secretary\n{name}".strip(),
                "body": name, "address": address, "email": email, "source": url, "host": host(url),
                "quote": exact, "email_source": url if email else "", "note": CHECK}
    return {"found": False, "why": f"no Member Secretary contact found on {', '.join(sites)} "
                                   f"(pages read: {len(urls)})"}


def clearance_contact(run, ident, docs):
    """MoEFCC Impact Assessment Division, from the address block of a MoEFCC letter of this
    project; an email only from an official page that prints one next to the division."""
    if not ident["proposals"]:
        return {"found": False, "why": "the report's own text gives no proposal number, so the "
                                       "appraising authority is not known"}
    for d in docs:
        if not d["host"].endswith(("environmentclearance.nic.in", "parivesh.nic.in", "moef.gov.in")):
            continue
        text = paper_trail.plain(run.raw.get(paper_trail.canonical(d["url"]), ""))
        m = MOEF_BLOCK.search(text)
        if not m:
            continue
        exact = knowable.verified_quote(m.group(0), text)
        if not exact:
            continue
        tavily_usage.used_text(exact, "shown as evidence")
        address = re.sub(r"^.*?Division\s*\)?\s*", "", exact)
        email, email_src, email_quote = find_ia_email(run)
        return {"found": True, "role": "clearance",
                "to": "The Member Secretary\nExpert Appraisal Committee\nImpact Assessment Division\n"
                      "Ministry of Environment, Forest and Climate Change",
                "body": "Ministry of Environment, Forest and Climate Change, Impact Assessment Division",
                "address": address, "email": email, "source": d["url"], "host": d["host"],
                "quote": exact, "email_source": email_src, "email_quote": email_quote, "note": CHECK}
    url, exact = clearance_from_moef_page(run)      # no letter of this project: MoEFCC's own page
    if exact:
        address = re.sub(r"^.*?(?:Division|Wing)\s*\)?\s*,?\s*", "", exact)
        email, email_src, email_quote = find_ia_email(run)
        return {"found": True, "role": "clearance",
                "to": "The Member Secretary\nExpert Appraisal Committee\nImpact Assessment Division\n"
                      "Ministry of Environment, Forest and Climate Change",
                "body": "Ministry of Environment, Forest and Climate Change, Impact Assessment Division",
                "address": address, "email": email, "source": url, "host": host(url), "quote": exact,
                "email_source": email_src, "email_quote": email_quote,
                "note": CHECK + " (Address from a MoEFCC page, not from a letter of this project.)"}
    return {"found": False, "why": "no MoEFCC letter of this project with an address block, and no "
                                   "MoEFCC page with the Impact Assessment Division's address, was found"}


# ---------- an ADB-financed project: the borrower's agency and the bank ----------

ADB_OFFICER = re.compile(r"Responsible ADB Officer\s+(.{3,60}?)\s+Responsible ADB Department\s+(.{3,80}?)"
                         r"\s+Responsible ADB Division\s+(.{3,80}?)(?=\s*Executing Agenc|\s*#|$)")
ADB_HQ = re.compile(r"Headquarters\s+(.{10,120}?Philippines)")
AM_BLOCK = re.compile(r"Complaint Receiving Officer\W+Accountability Mechanism\W+Asian Development Bank"
                      r"\W+(.{10,120}?Philippines)")


def _adb_text(run, url):
    return paper_trail.plain(run.raw.get(paper_trail.canonical(url), ""))


def lender_contact(run, ident, docs):
    """The project's contact as listed on its ADB project page (role and division; ADB's
    headquarters address from the same page). An email only if printed in the page text."""
    pages = [d["url"] for d in docs if d["type"] == "ADB project page"]
    for url in pages:
        text = _adb_text(run, url)
        m, hq = ADB_OFFICER.search(text), ADB_HQ.search(text)
        if not m:
            continue
        exact = knowable.verified_quote(m.group(0), text)
        hq_exact = knowable.verified_quote(hq.group(0), text) if hq else None
        if not exact:
            continue
        tavily_usage.used_text(exact, "shown as evidence")
        division = " ".join(m.group(3).split())
        return {"found": True, "role": "lender",
                "to": f"The Responsible ADB Officer\n{division}\nAsian Development Bank",
                "body": f"Asian Development Bank, {division}",
                "address": hq.group(1) if hq_exact else "", "email": "", "source": url,
                "host": host(url), "quote": exact + (f" … {hq_exact}" if hq_exact else ""),
                "note": CHECK + " No email is printed on the project page (ADB links to a web form)."}
    return {"found": False, "why": "no ADB project page listing the project's contact was found"}


def accountability_contact(run):
    """ADB's Accountability Mechanism (Complaint Receiving Officer), from ADB's own page."""
    urls = run.search_urls("Accountability Mechanism complaint receiving officer contact address",
                           ["adb.org"], "authority contact")[:3]
    run.extract_urls(urls)
    for url in urls:
        text = _adb_text(run, url)
        m = AM_BLOCK.search(text)
        exact = knowable.verified_quote(m.group(0), text) if m else None
        if not exact:
            continue
        tavily_usage.used_text(exact, "shown as evidence")
        email = EMAIL.search(text[m.start():m.end() + 200])
        return {"found": True, "role": "accountability",
                "to": "The Complaint Receiving Officer\nAccountability Mechanism\nAsian Development Bank",
                "body": "Asian Development Bank, Accountability Mechanism (Complaint Receiving Officer)",
                "address": m.group(1), "email": well_formed(email), "source": url,
                "host": host(url), "quote": exact,
                "note": CHECK + ("" if email else " No email is printed on the page (ADB links to a web form).")}
    return {"found": False, "why": "no ADB page with the Accountability Mechanism's address was found"}


def borrower_contact(run, ident):
    """The executing agency named in the report (KRRDA), from its own government site."""
    b = ident.get("borrower") or {}
    sites = b.get("sites") or []
    urls = [u for s in sites for u in run.map_urls.get(s, []) if CONTACT_URL.search(u)][:6]
    if not urls:
        for s in sites:
            urls += [u for u in run.map_contacts(s, paper_trail.AGENCY_CONTACT_INSTRUCTIONS)
                     if CONTACT_URL.search(u)]
        urls = urls[:6]
    if not urls and sites:  # map sees nothing: one search on the agency's own sites
        urls = run.search_urls(f"{b.get('body', '')} contact address email "
                               f"{' '.join((b.get('roles') or [])[:2])}", sites, "authority contact")[:4]
    run.extract_urls(urls)
    for url in urls:
        text = knowable.plain_text(run.raw.get(paper_trail.canonical(url), ""))
        for role in b.get("roles") or []:
            quote, address, email = _row_contact(text, role)
            exact = knowable.verified_quote(quote, text) if quote else None
            if not exact:
                continue
            tavily_usage.used_text(exact, "shown as evidence")
            return {"found": True, "role": "borrower", "to": f"The {role}\n{b['body']}",
                    "body": b["body"], "address": address, "email": email, "source": url,
                    "host": host(url), "quote": exact, "note": CHECK}
    return {"found": False, "why": f"no contact of the {', '.join(b.get('roles') or ['agency'])} found on "
                                   f"{', '.join(sites)} (pages read: {len(urls)})"}


MOEF_SITES = ["moef.gov.in", "parivesh.nic.in", "environmentclearance.nic.in"]
IA_ADDRESS = re.compile(r"Impact Assessment (?:Division|Wing)[^|]{0,200}?\b110\s?003\b", re.I)


def clearance_from_moef_page(run):
    """The IA Division's address from an official MoEFCC page (not a letter of this project):
    used when no MoEFCC letter of the project was found."""
    urls = run.search_urls("Impact Assessment Division Ministry of Environment Forest and Climate "
                           "Change Indira Paryavaran Bhawan address", MOEF_SITES, "authority contact")[:3]
    run.extract_urls(urls)
    for u in urls:
        text = paper_trail.plain(run.raw.get(paper_trail.canonical(u), ""))
        m = MOEF_BLOCK.search(text) or IA_ADDRESS.search(text)
        exact = knowable.verified_quote(m.group(0), text) if m else None
        if exact:
            tavily_usage.used_text(exact, "shown as evidence")
            return u, exact
    return None, None


def find_ia_email(run):
    """(email, url, quote) from an official MoEFCC page that prints an email in the same
    sentence as "Impact Assessment" or "Member Secretary"; ("", "", "") if none."""
    try:
        urls = run.search_urls("Impact Assessment Division Ministry of Environment Forest and Climate "
                               "Change member secretary email contact", MOEF_SITES, "authority contact")[:3]
    except Exception:       # noqa: BLE001 (credit cap: leave the email out)
        return "", "", ""
    run.extract_urls(urls)
    for u in urls:
        text = paper_trail.plain(run.raw.get(paper_trail.canonical(u), ""))
        # only a page about this project (e.g. the EAC meeting that considered it), and only the
        # email printed right after "Member Secretary" / the division, with no other email between
        if not paper_trail.names_project(text, run.ident)[0]:
            continue
        for m in EMAIL.finditer(text):
            before = text[max(0, m.start() - 80):m.start()]
            if EMAIL.search(before.split("Member Secretary")[-1].split("Impact Assessment")[-1]):
                continue
            if re.search(r"(?:member secretary|impact assessment division)\W[^@]{0,60}$", before, re.I):
                quote = paper_trail.sentence_around(text, m.start(), m.end() - m.start(), 260)
                exact = knowable.verified_quote(quote, text)
                if exact:
                    tavily_usage.used_text(exact, "shown as evidence")
                    return m.group(0), u, exact
    return "", "", ""


def find(run, ident, docs):
    if paper_trail.is_adb(ident):     # no public hearing / clearance under the EIA Notification
        return {"borrower": borrower_contact(run, ident), "lender": lender_contact(run, ident, docs),
                "accountability": accountability_contact(run)}
    return {"hearing": hearing_contact(run, ident), "clearance": clearance_contact(run, ident, docs)}


# ---------- for the letter and the RTI pack ----------

def contact(report_id, role):
    """The saved contact ({to, address, email, source, ...}) or None."""
    c = ((paper_trail.load(report_id) or {}).get("contacts") or {}).get(role) or {}
    return c if c.get("found") else None


def address_lines(c):
    """Addressee block text: name, address and email as published, the source and the check note."""
    lines = [c["to"]]
    if c.get("address"):
        lines.append(c["address"])
    if c.get("email"):
        lines.append(f"Email: {c['email']}")
    lines.append(f"(As published on {c['host']}. {CHECK})")
    return "\n".join(lines)


def to_blocks(report, role, default):
    """Letter blocks for the addressee: the saved contact (name as text, address and email as
    data, never translated, then where it was published and the check note), or `default`
    (the [placeholder] text) when none was found."""
    c = contact((report or {}).get("id", ""), role)
    if not c:
        return [("text", default)]
    data = "\n".join(x for x in (c.get("address"), f"Email: {c['email']}" if c.get("email") else "") if x)
    out = [("text", "To,\n" + c["to"])]
    if data:
        out.append(("data", data))
    out.append(("text", f"(Address as published on {c['host']}. {CHECK})"))
    return out


def lender_letter_blocks(report, default):
    """Addressee for a report prepared for a development bank: the borrower's agency (as
    found), copied to the bank's project contact (as found); else `default`."""
    out = to_blocks(report, "borrower", default)
    c = contact((report or {}).get("id", ""), "lender")
    if c:
        out.append(("text", "Copy: " + c["to"].replace("\n", ", ")))
        if c.get("address"):
            out.append(("data", c["address"]))
    return out


def rti_to(report, default):
    """The RTI addressee text: the PIO of the clearance authority found, else `default`."""
    c = contact((report or {}).get("id", ""), "clearance")
    if not c:
        return default
    lines = ["To,", "The Public Information Officer", c["body"]]
    lines += [x for x in (c.get("address"), f"Email: {c['email']}" if c.get("email") else "") if x]
    lines.append(f"(Address as published on {c['host']}. {CHECK})")
    return "\n".join(lines)
