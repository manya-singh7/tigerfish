"""Per-report site profiles: where the project is, which place names locate a species
table, and which regional rules apply. Nothing here carries over between reports.

archipelago_gadm: the GBIF GADM region for the archipelago rule (a mobile taxon recorded
anywhere in that island group is not flagged). None = the rule does not apply (mainland
sites). The mobile-taxa rule (species.apply_mobile_region) applies everywhere.
region_gadm (optional): the species tables list a whole state; a species with GBIF records
anywhere in that GADM region is not flagged (any taxon).
not_applicable (optional): {check: reason}; those checks are not run for the report and the
app shows "not applicable to this report" with the reason.
pairing (optional): the report's own places for subject keys (tigerfish/pairing.py).
"""

NOT_APPLICABLE = "not applicable to this report"

GREAT_NICOBAR = "great_nicobar_2021_draft_eia"
CUDDALORE = "cuddalore_port_2026_draft_eia"
KARNATAKA = "karnataka_rural_roads_2026_adb_eia"

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
    KARNATAKA: {
        # Everything below is from the report's own text (Part 1 of 4, Main Report, July 2026).
        "project": "Karnataka Rural Roads Improvement Project (RRP IND 59160-001)",   # p.1
        "project_source": "report p.1: \"India: Karnataka Rural Roads Improvement Project\", "
                          "\"RRP IND 59160-001\", July 2026",
        "scope": "1,335 existing rural roads (about 5,178 km) and 51 bridges in all 31 districts "
                 "of Karnataka (p.11)",
        "prepared_by": "Karnataka Rural Roads Development Agency (KRRDA), Government of "
                       "Karnataka (p.1); executing agency RDPR Department through KRRDA (p.310)",
        "consultant": None,     # no EIA consultant firm is named (DPR consultants are unnamed)
        "funding": "Asian Development Bank (p.1: \"for the Asian Development Bank\"; p.2: "
                   "\"a document of the borrower\"); ADB SPS 2009 Category A (p.11, p.26)",
        # Statewide road network: no single project point. The state's extent is given on
        # p.23 (also p.56, p.83): 11.5-18.5 N, 74-78.5 E. Its midpoint stands for the state.
        "site": (15.0, 76.25), "site_label": "Karnataka (statewide road network)",
        "site_source": "report p.23 (also p.56, p.83): Karnataka lies between 11.5° N and "
                       "18.5° N and between 74° E and 78.5° E; 1,335 roads in all 31 districts "
                       "(p.11), so there is no single project site; the midpoint of that "
                       "extent is used",
        "sites": {"Karnataka": (15.0, 76.25)},
        "centre": (15.0, 76.25), "centre_label": "Karnataka (midpoint of the state's extent, p.23)",
        "archipelago_gadm": None,                # mainland state: no A&N archipelago rule
        # The species tables (pp.144-193) are statewide lists: "recorded from the state of
        # Karnataka" (p.171), "List of Fish species in Karnataka" (p.192), species "within
        # the state and the Project's AoI" (p.142). A species with GBIF records anywhere in
        # the state is not flagged.
        "region_gadm": "IND.16_1",               # GBIF GADM id, "Karnataka" (verified)
        "region_label": "Karnataka",
        "state": "Karnataka",
        "languages": ["kn"],                     # letter: English + Kannada
        # Checks that do not fit this report: shown as "not applicable", never run.
        "not_applicable": {
            "omission": "No single project site: 1,335 roads across all 31 districts (p.11). "
                        "The check looks for threatened species recorded within 25 km of one "
                        "site, so it does not fit a statewide road network.",
            "accreditation": "No Indian EIA consultant is named: the report was prepared by "
                             "KRRDA, Government of Karnataka, for the Asian Development Bank "
                             "(p.1), under ADB SPS 2009 (p.11). Rural roads need no prior "
                             "environmental clearance under the EIA Notification, 2006 (p.11, "
                             "p.357), and NABET/QCI is not mentioned anywhere in the report.",
            "promise": "No Indian Terms of Reference: the project needs no environmental "
                       "clearance under the EIA Notification, 2006 (p.11, p.357), and we hold "
                       "no ToR for it.",
            "public_consultation": "No public hearing under the EIA Notification, 2006: the "
                                   "project needs no environmental clearance (p.11, p.357). Its "
                                   "consultations follow ADB SPS 2009 (e.g. Udupi and Uttara "
                                   "Kannada, 6-11 July 2026, p.17).",
        },
        # Letter: to the borrower's agency, copied to the lender (not the MoEFCC EAC)
        "letter_addressee": "lender",
        "letter_to": "The Chief Operating Officer and Project Director\n"            # p.23, p.310
                     "Karnataka Rural Roads Development Agency (KRRDA), Government of Karnataka\n"
                     "Copy: Asian Development Bank, project team, Karnataka Rural Roads "
                     "Improvement Project (RRP IND 59160-001)",
        # Subject keys for pairing (tigerfish/pairing.py): this report's own places.
        "pairing": {
            "project": "a programme of 1,335 rural roads and 51 bridges across all 31 districts "
                       "of Karnataka, India, financed by the Asian Development Bank",
            "places": ["karnataka", "project roads", "study area"],
            "place_note": "a figure for the whole state is \"karnataka\"; a figure for the "
                          "project's roads, bridges or corridor is \"project roads\"; name a "
                          "district, taluk, protected area or road ID as given",
            "same_place": ["", "project roads", "project site"],
            "merged_place": "project roads",
            "inside": {"karnataka": ["project roads"]},
        },
    },
}


def profile(pdf_stem):
    """The profile for a report (by PDF stem), or None if the report has none."""
    return PROFILES.get(pdf_stem)


def not_applicable(pdf_stem, check):
    """The reason a check does not apply to this report, or None if it applies."""
    return ((profile(pdf_stem) or {}).get("not_applicable") or {}).get(check)
