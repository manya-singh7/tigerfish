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


def _row_contact(text, role="Member Secretary"):
    """(quote, address, email) from the table row or text block that names the role."""
    for line in text.split("\n"):
        if role.lower() in line.lower() and "|" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # the address: the longest cell that is not the role, an email or a person's name
            options = [c for c in cells if "," in c and role.lower() not in c.lower()
                       and not EMAIL.search(c) and not PERSON.search(c) and len(c) > 15]
            address = max(options, key=len, default="")
            email = EMAIL.search(line)
            quote = " ".join(line.strip().strip("|").split())      # the row as published
            return quote, address, email.group(0) if email else ""
    flat = " ".join(text.split())
    i = flat.lower().find(role.lower())
    if i < 0:
        return None, "", ""
    block = flat[i:i + 300]
    pin = PIN.search(block)
    quote = block[:pin.end()] if pin else block[:200]
    email = EMAIL.search(flat[i:i + 400])
    return quote.strip(), quote[len(role):].strip(" ,:-"), email.group(0) if email else ""


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
    if urls:
        run.extract_urls(urls)
    texts = {u: knowable.plain_text(run.raw.get(paper_trail.canonical(u), "")) for u in urls}
    own = [t for k, t in run.raw.items() if any(host(k).endswith(s) for s in sites)]
    name = (board_name(texts.values(), ident["state"])          # only the board's own pages
            or board_name(own, ident["state"]) or f"Pollution control board / committee, {ident['state']}")
    for url, text in texts.items():
        quote, address, email = _row_contact(text)
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
    return {"found": False, "why": "no MoEFCC letter of this project with an address block was found"}


def find_ia_email(run):
    """(email, url, quote) from an official MoEFCC page that prints an email in the same
    sentence as "Impact Assessment" or "Member Secretary"; ("", "", "") if none."""
    try:
        run.search("Impact Assessment Division Ministry of Environment Forest and Climate Change "
                   "member secretary email contact", "authority contact")
    except Exception:       # noqa: BLE001 (credit cap: leave the email out)
        return "", "", ""
    urls = [v["url"] for v in run.found.values() if v["detail"] == "authority contact"
            and host(v["url"]).endswith(("moef.gov.in", "parivesh.nic.in", "environmentclearance.nic.in"))][:3]
    run.extract_urls(urls)
    for u in urls:
        text = paper_trail.plain(run.raw.get(paper_trail.canonical(u), ""))
        for m in EMAIL.finditer(text):
            window = text[max(0, m.start() - 200):m.end() + 50]
            if re.search(r"impact assessment|member secretary", window, re.I):
                quote = paper_trail.sentence_around(text, m.start(), m.end() - m.start(), 260)
                exact = knowable.verified_quote(quote, text)
                if exact:
                    tavily_usage.used_text(exact, "shown as evidence")
                    return m.group(0), u, exact
    return "", "", ""


def find(run, ident, docs):
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


def rti_to(report, default):
    """The RTI addressee text: the PIO of the clearance authority found, else `default`."""
    c = contact((report or {}).get("id", ""), "clearance")
    if not c:
        return default
    lines = ["To,", "The Public Information Officer", c["body"]]
    lines += [x for x in (c.get("address"), f"Email: {c['email']}" if c.get("email") else "") if x]
    lines.append(f"(Address as published on {c['host']}. {CHECK})")
    return "\n".join(lines)
