"""Species photos for the species cards, with attribution.

1. Tavily search with include_images=True, restricted to commons.wikimedia.org, for each RED
   species and each flagged species of the Table 3.16 check (cached, credit-capped).
2. Each candidate image is mapped to its Commons file page ("File:..."). The licence and the
   author come from that page's own metadata (Wikimedia Commons API, imageinfo/extmetadata;
   free, cached in cache/commons/).
3. An image is used only if its licence is free (CC0, public domain, CC BY, CC BY-SA, GFDL)
   and its file name, description or categories name the species. We store the image URL
   (never the file), the licence, its URL, the author credit and the file page.
No licensed image found: the card shows none.
"""

import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests

from tigerfish import copycheck, knowable

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
COMMONS_CACHE = ROOT / "cache" / "commons"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "TigerFish/0.1 (EIA accuracy checker; https://github.com/manya-singh7/tigerfish)"
THUMB_WIDTH = 480
MAX_CANDIDATES = 8          # Commons files checked per species
MAX_CREDITS = 15
FREE_LICENCE = re.compile(r"^(cc0|cc[- ]by(-sa)?\b|public domain|pd\b|pd-|gfdl|attribution)", re.I)
NOT_FREE = re.compile(r"\b(nc|nd|non-?commercial|no ?deriv|fair use)\b", re.I)

# report id -> finding ids that get a photo, and the name to search for (GBIF-accepted name)
SPECIES = {
    "great_nicobar_2021_draft": {"sp-p954-001": "Panulirus interruptus"},
    "indira_point_table_3_16": {"sp-01": "Axis axis", "sp-02": "Rusa unicolor",
                                "sp-03": "Felis chaus", "sp-04": "Funambulus pennantii",
                                "sp-05": "Muntiacus muntjak", "st-06": "Macaca fascicularis",
                                "st-07": "Rattus rattus"},
}


def is_free(licence):
    return bool(licence) and bool(FREE_LICENCE.search(licence.strip())) and not NOT_FREE.search(licence)


def file_title(url):
    """Commons file title ("File:Axis axis.jpg") for an upload.wikimedia.org image URL or a
    commons.wikimedia.org/wiki/File: page, else None."""
    parts = urlsplit(url or "")
    path = unquote(parts.path)
    if parts.hostname == "upload.wikimedia.org":
        segs = [s for s in path.split("/") if s]
        if "thumb" in segs:                       # /wikipedia/commons/thumb/a/ab/Name.jpg/320px-Name.jpg
            i = segs.index("thumb")
            name = segs[i + 3] if len(segs) > i + 3 else None
        else:                                     # /wikipedia/commons/a/ab/Name.jpg
            name = segs[-1] if segs else None
        return f"File:{name}" if name else None
    if parts.hostname and parts.hostname.endswith("commons.wikimedia.org") and "/wiki/File:" in path:
        return "File:" + path.split("/wiki/File:", 1)[1]
    return None


def strip_html(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


def commons_info(title, get=requests.get):
    """{licence, licence_url, author, description, categories, thumb, page} from the Commons
    API (cached), or None."""
    COMMONS_CACHE.mkdir(parents=True, exist_ok=True)
    path = COMMONS_CACHE / f"{hashlib.sha256(title.encode()).hexdigest()}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        r = get(COMMONS_API, params={"action": "query", "titles": title, "prop": "imageinfo",
                                     "iiprop": "url|extmetadata", "iiurlwidth": THUMB_WIDTH,
                                     "format": "json"},
                headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        data = r.json()
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    pages = (data.get("query") or {}).get("pages") or {}
    page = next(iter(pages.values()), {})
    info = (page.get("imageinfo") or [None])[0]
    if not info:
        return None
    meta = info.get("extmetadata") or {}
    val = lambda k: strip_html((meta.get(k) or {}).get("value"))   # noqa: E731
    return {"licence": val("LicenseShortName"), "licence_url": val("LicenseUrl"),
            "author": val("Artist") or val("Credit"), "description": val("ImageDescription"),
            "categories": val("Categories"), "object_name": val("ObjectName"),
            "thumb": info.get("thumburl") or info.get("url"),
            "page": info.get("descriptionurl")}


def names_species(info, title, name):
    hay = " ".join([title, info.get("description") or "", info.get("categories") or "",
                    info.get("object_name") or ""]).lower().replace("_", " ")
    return name.lower() in hay


def candidates(data):
    """Commons file titles from a Tavily response (images first, then result pages)."""
    urls = [i if isinstance(i, str) else (i or {}).get("url") for i in data.get("images") or []]
    urls += [r.get("url") for r in data.get("results") or []]
    titles = [file_title(u) for u in urls if u]
    return list(dict.fromkeys(t for t in titles if t))


def find_photo(name, budget, get=requests.get, stats=None):
    """(photo dict or None, [checked: {title, why}])."""
    data = knowable.counted_call(stats if stats is not None else {}, "search", budget, 1, query=f"{name} photo", search_depth="basic",
                                 max_results=5, include_images=True,
                                 include_domains=["commons.wikimedia.org"])
    checked = []
    for title in candidates(data)[:MAX_CANDIDATES]:
        info = commons_info(title, get)
        if not info:
            checked.append({"title": title, "why": "no file information on Commons"})
        elif not is_free(info["licence"]):
            checked.append({"title": title, "why": f"licence not free: {info['licence'] or 'none stated'}"})
        elif not names_species(info, title, name):
            checked.append({"title": title, "why": "file does not name the species"})
        elif not info["author"]:
            checked.append({"title": title, "why": "no author credit stated"})
        else:
            return {"species": name, "image_url": info["thumb"], "page": info["page"],
                    "licence": info["licence"], "licence_url": info["licence_url"],
                    "author": info["author"][:200], "title": title,
                    "source": "Wikimedia Commons (found with Tavily image search)"}, checked
    return None, checked


def run(budget=None):
    budget = budget or copycheck.Budget(MAX_CREDITS)
    out, stopped, stats = {}, None, {"credits": 0}
    try:
        for rid, species in SPECIES.items():
            for fid, name in species.items():
                photo, checked = find_photo(name, budget, stats=stats)
                out.setdefault(rid, {})[fid] = {"species": name, "photo": photo, "checked": checked}
    except copycheck.CreditCapReached as e:
        stopped = str(e)
    return {"photos": out, "stopped": stopped,
            "tavily": {"credits": stats["credits"], "credits_by_report": {
                           rid: len(rows) for rid, rows in out.items()},
                       "credits_spent_this_run": budget.used, "cached_calls": budget.cached,
                       "features": ["include_images", "include_domains"]}}


PATH = RESULTS / "species_photos.json"


def load():
    return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else None


def photo_for(report_id, finding_id, data=None):
    data = data if data is not None else load()
    return (((data or {}).get("photos") or {}).get(report_id) or {}).get(finding_id, {}).get("photo")
