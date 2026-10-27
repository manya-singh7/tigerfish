"""Species photos: Tavily image search on Commons + licence from the Commons file page (mocked)."""

import pytest

from tigerfish import copycheck
from tigerfish import species_photos as sp

FREE_INFO = {
    "File:Nc.jpg": ("CC BY-NC 2.0", "A. Person", "Axis axis"),
    "File:Axis_axis_male.jpg": ("CC BY-SA 4.0", "<a href='u'>B. Person</a>", "Chital stag, Axis axis"),
    "File:Other.jpg": ("CC0", "C", "Axis axis"),
}


class FakeTavily:
    def __init__(self):
        self.kw = []

    def search(self, **kw):
        self.kw.append(kw)
        return {"images": ["https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Nc.jpg/320px-Nc.jpg",
                           "https://upload.wikimedia.org/wikipedia/commons/c/cd/Axis_axis_male.jpg"],
                "results": [{"url": "https://commons.wikimedia.org/wiki/File:Other.jpg"}],
                "usage": {"credits": 1}}


def getter(info):
    def get(url, params, headers, timeout):
        lic, artist, desc = info[params["titles"]]

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return {"query": {"pages": {"1": {"imageinfo": [{
                    "thumburl": f"https://upload.wikimedia.org/thumb/{params['titles']}",
                    "descriptionurl": f"https://commons.wikimedia.org/wiki/{params['titles']}",
                    "extmetadata": {"LicenseShortName": {"value": lic}, "Artist": {"value": artist},
                                    "ImageDescription": {"value": desc},
                                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"}}}]}}}}
        return R()
    return get


@pytest.fixture
def tav(monkeypatch, tmp_path):
    f = FakeTavily()
    monkeypatch.setattr(copycheck, "CACHE_DIR", tmp_path / "tavily")
    monkeypatch.setattr(sp, "COMMONS_CACHE", tmp_path / "commons")
    monkeypatch.setattr(copycheck, "client", lambda: f)
    return f


def test_search_asks_commons_for_images(tav):
    sp.find_photo("Axis axis", copycheck.Budget(5), get=getter(FREE_INFO))
    kw = tav.kw[0]
    assert kw["include_images"] is True and kw["include_domains"] == ["commons.wikimedia.org"]


def test_non_free_licence_skipped_free_one_used_with_credit(tav):
    photo, checked = sp.find_photo("Axis axis", copycheck.Budget(5), get=getter(FREE_INFO))
    assert checked[0]["why"].startswith("licence not free: CC BY-NC")
    assert photo["title"] == "File:Axis_axis_male.jpg" and photo["licence"] == "CC BY-SA 4.0"
    assert photo["author"] == "B. Person"                       # HTML stripped
    assert photo["image_url"].startswith("https://upload.wikimedia.org/")   # a URL, not a file


def test_no_licensed_image_means_none(tav):
    closed = {k: ("All rights reserved", "X", "Axis axis") for k in FREE_INFO}
    photo, checked = sp.find_photo("Axis axis", copycheck.Budget(5), get=getter(closed))
    assert photo is None and len(checked) == 3


@pytest.mark.parametrize("lic,ok", [("CC0", True), ("CC BY 2.0", True), ("CC BY-SA 3.0", True),
                                    ("Public domain", True), ("CC BY-NC-SA 4.0", False),
                                    ("Fair use", False), ("", False)])
def test_free_licences(lic, ok):
    assert sp.is_free(lic) is ok


def test_file_title_from_urls():
    thumb = ("https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Rusa_unicolor.jpg/"
             "320px-Rusa_unicolor.jpg")
    assert sp.file_title(thumb) == "File:Rusa_unicolor.jpg"
    assert sp.file_title("https://commons.wikimedia.org/wiki/File:Felis%20chaus.jpg") == "File:Felis chaus.jpg"
    assert sp.file_title("https://example.org/x.jpg") is None
