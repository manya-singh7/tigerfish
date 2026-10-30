"""The evidence slip: TigerFish's one card (docs/DESIGN.md).

A crop of the real report page with the quote highlighted (results/pages/, cut by crops.py),
the page number, the grade, the check name, a one-line reason, and "Verified by a person"
only when a person did. Crop and text sit side by side on desktop and stack on a phone (CSS
grid in style.py). Used on Home, in every flag list and in the library's report previews.
"""

import base64
import io
import re

import streamlit as st
from PIL import Image

from tigerfish.ui import crops, data
from tigerfish.ui.style import badge, esc

QUOTE_CHARS = 260
CROP_WIDTH = 820


@st.cache_data(show_spinner=False, max_entries=512)
def _crop_uri(path):
    """A data URI of the highlighted lines on one page image (WebP), or None."""
    png = crops.crop(path)
    if png is None:
        return None
    with Image.open(io.BytesIO(png)) as img:
        img = img.convert("RGB")
        if img.width > CROP_WIDTH:
            img = img.resize((CROP_WIDTH, round(img.height * CROP_WIDTH / img.width)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=80)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


def page_of(rel):
    m = re.search(r"_p(\d+)\.png$", str(rel))
    return int(m.group(1)) if m else None


MAX_CROPS = 2      # a contradiction's two pages; more pages stay in "Show highlighted pages"


def crops_for(finding, limit=MAX_CROPS):
    """[(data URI, page number)] for this finding's page images that have a highlight."""
    out = []
    for rel in dict.fromkeys(finding.get("images") or []):
        path = data.image_path(rel)
        uri = _crop_uri(str(path)) if path else None
        if uri:
            out.append((uri, page_of(rel)))
        if len(out) == limit:
            break
    return out


def crop_for(finding):
    """(data URI, page number) of the first highlighted page image, or (None, None)."""
    found = crops_for(finding)
    return found[0] if found else (None, None)


def page_ref(finding):
    """"p.737" (or "p.737, p.738"), or where the quote is from ("Table 3.16")."""
    pages = [q.get("page") for q in finding.get("quotes") or [] if q.get("page")]
    if pages:
        return ", ".join(f"p.{p}" for p in dict.fromkeys(pages))
    where = next((q.get("where") for q in finding.get("quotes") or [] if q.get("where")), "")
    return where


def quote_of(finding):
    q = next((q for q in finding.get("quotes") or [] if q.get("text")), None)
    if not q:
        return ""
    text = " ".join(str(q["text"]).split())
    return text if len(text) <= QUOTE_CHARS else text[:QUOTE_CHARS].rsplit(" ", 1)[0] + " ..."


GENERIC = ("inconsistency flagged", "possible", "verify")
REASON_CHARS = 240


def _first_sentence(text):
    text = " ".join(str(text or "").split())
    m = re.match(r"(.+?[.;])(\s|$)", text)
    out = m.group(1) if m else text
    if len(out) > REASON_CHARS:
        out = out[:REASON_CHARS].rsplit(" ", 1)[0] + " ..."
    return out


def reason_of(finding, full=False):
    """One line: the reviewer's wording when a person verified it, else the first sentence of
    the message, or of "why" when the message is only the generic "flagged, verify".
    full: the reviewer's or Ultra's whole wording, not its first sentence."""
    v = finding.get("verification") or {}
    if full:
        return " ".join(str(v.get("wording") or finding.get("why") or finding.get("message")).split())
    if v.get("wording"):
        return _first_sentence(v["wording"])
    msg = _first_sentence(finding.get("message"))
    if len(msg) < 40 and msg.lower().startswith(GENERIC):
        return _first_sentence(finding.get("why")) or msg
    return msg


def verified_html(finding, confirmed=None):
    """"Verified by a person" for a hand check; else, given reviewers' decision rows
    (confirmed), who confirmed it in the review queue and when."""
    v = finding.get("verification")
    if v:
        return f'<span class="tf-person">Verified by a person, {esc(v.get("on", ""))}</span>'
    if confirmed:
        names = ", ".join(dict.fromkeys(r["reviewer"] for r in confirmed))
        on = max(str(r.get("time", ""))[:10] for r in confirmed)
        return f'<span class="tf-person">Confirmed by a reviewer ({esc(names)}), {esc(on)}</span>'
    return ""


def html(finding, *, crop=True, extra="", section=None, link=None, photo=None, title=None,
         max_crops=MAX_CROPS, confirmed=None, lead=False):
    """The slip as HTML. extra: HTML added under the reason (badges, notes). link: (href, label)
    for an "open" link. photo: HTML of a species photo used when there is no page crop.
    confirmed: reviewers' decision rows confirming it (review.confirmed_findings).
    lead: the Overview's opening slip: the pages side by side and large, the whole reason."""
    found = crops_for(finding, max_crops) if crop else []
    ref = page_ref(finding) or ", ".join(f"p.{p}" for _, p in found)
    visual = ""
    if found:
        visual = '<div class="tf-slip-crops">' + "".join(
            f'<figure class="tf-slip-crop"><img src="{uri}" alt="Highlighted lines of page '
            f'{esc(page)} of the report"><figcaption>Page {esc(page)}, highlighted</figcaption></figure>'
            for uri, page in found) + "</div>"
    elif photo:
        visual = photo
    head = (f'<div class="tf-slip-head">{badge(finding["grade"])}'
            f'<span class="tf-check">{esc(finding.get("check_name", ""))}'
            + (f' in {esc(section)}' if section else "") + "</span>"
            + (f'<span class="tf-slip-page">{esc(ref)}</span>' if ref else "") + "</div>")
    quote = quote_of(finding)
    foot = [x for x in (verified_html(finding, confirmed),
                        f'<span class="tf-mono">{esc(finding.get("id", ""))}</span>',
                        f'<a class="tf-open" href="{esc(link[0])}" target="_self">{esc(link[1])}</a>'
                        if link else "") if x]
    body = (head + f'<div class="tf-slip-title">{esc(title or finding.get("title", ""))}</div>'
            + (f'<blockquote class="tf-slip-quote">{esc(quote)}</blockquote>' if quote else "")
            + f'<div class="tf-slip-reason">{esc(reason_of(finding, full=lead))}</div>' + extra
            + f'<div class="tf-slip-foot">{"".join(foot)}</div>')
    cls = "tf-slip" + ("" if visual else " tf-slip-noimg") + (" tf-slip-lead" if lead else "")
    return (f'<div class="tf-slipbox"><div class="{cls}">{visual}<div class="tf-slip-text">{body}'
            f'</div></div></div>')


def render(finding, **kw):
    st.markdown(html(finding, **kw), unsafe_allow_html=True)


def pick(findings, n=3):
    """The findings worth showing first: human-verified, then RED before ORANGE, then those with
    a page crop. Dismissed or explained ones are left out."""
    def score(f):
        v = f.get("verification") or {}
        return (bool(v) and v.get("outcome") != "explained", f["grade"] == "RED",
                f["grade"] == "ORANGE", bool(f.get("images")))
    keep = [f for f in findings if (f.get("verification") or {}).get("outcome") != "explained"]
    return sorted(keep, key=score, reverse=True)[:n]
