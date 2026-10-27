"""Per-report site profiles: where the project is, which place names locate a species
table, and which regional rules apply. Nothing here carries over between reports.

archipelago_gadm: the GBIF GADM region for the archipelago rule (a mobile taxon recorded
anywhere in that island group is not flagged). None = the rule does not apply (mainland
sites). The mobile-taxa rule (species.apply_mobile_region) applies everywhere.
"""

GREAT_NICOBAR = "great_nicobar_2021_draft_eia"
CUDDALORE = "cuddalore_port_2026_draft_eia"

PROFILES = {
    GREAT_NICOBAR: {
        "site": (6.83, 93.87), "site_label": "Galathea Bay",
        "sites": {"Galathea": (6.82, 93.88), "Campbell Bay": (7.0, 93.93),
                  "Indira Point": (6.75, 93.83)},
        "centre": (7.0, 93.85), "centre_label": "island centre",
        "archipelago_gadm": "IND.1_1",          # Andaman and Nicobar (GBIF GADM id, verified)
        "state": "Andaman and Nicobar Islands",
    },
    CUDDALORE: {
        # The report's own coordinates (p.33, p.35, p.491): latitude 11°42'22.43" N,
        # longitude 79°46'30.52" E (the text layer garbles ° and ' as "0" and "9").
        "site": (11.7062, 79.7751), "site_label": "Cuddalore Port",
        "site_source": "report p.491: latitude 11°42'22.43\" N, longitude 79°46'30.52\" E "
                       "(also p.33, p.35)",
        "sites": {"Cuddalore": (11.7062, 79.7751)},
        "centre": (11.7062, 79.7751), "centre_label": "Cuddalore Port",
        "archipelago_gadm": None,                # mainland coast: no archipelago rule
        "state": "Tamil Nadu",
    },
}


def profile(pdf_stem):
    """The profile for a report (by PDF stem), or None if the report has none."""
    return PROFILES.get(pdf_stem)
