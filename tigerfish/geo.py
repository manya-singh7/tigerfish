"""Approximate country centroids (ISO 3166-1 alpha-2 -> (name, lat, lon)) for the species map.

Rough geographic centres, good enough to draw an arc to "where a species is recorded".
Countries not in this table are listed under the map instead of drawn.
"""

CENTROIDS = {
    "AE": ("United Arab Emirates", 23.9, 54.3), "AF": ("Afghanistan", 33.9, 67.7),
    "AR": ("Argentina", -34.0, -64.0), "AT": ("Austria", 47.6, 14.1),
    "AU": ("Australia", -25.7, 134.5), "BD": ("Bangladesh", 23.7, 90.3),
    "BE": ("Belgium", 50.6, 4.6), "BR": ("Brazil", -10.8, -52.9),
    "BT": ("Bhutan", 27.4, 90.4), "BW": ("Botswana", -22.2, 23.8),
    "CA": ("Canada", 61.4, -98.3), "CH": ("Switzerland", 46.8, 8.2),
    "CL": ("Chile", -35.7, -71.5), "CN": ("China", 35.0, 103.8),
    "CO": ("Colombia", 4.1, -72.9), "CR": ("Costa Rica", 9.9, -84.2),
    "CU": ("Cuba", 21.6, -79.0), "CZ": ("Czechia", 49.8, 15.5),
    "DE": ("Germany", 51.1, 10.4), "DK": ("Denmark", 56.0, 10.0),
    "EC": ("Ecuador", -1.4, -78.4), "EG": ("Egypt", 26.6, 29.9),
    "ES": ("Spain", 40.2, -3.6), "ET": ("Ethiopia", 8.6, 39.6),
    "FI": ("Finland", 64.5, 26.3), "FJ": ("Fiji", -17.4, 178.1),
    "FR": ("France", 46.6, 2.4), "GB": ("United Kingdom", 54.0, -2.5),
    "GR": ("Greece", 39.1, 22.9), "GT": ("Guatemala", 15.7, -90.4),
    "HK": ("Hong Kong", 22.4, 114.1), "ID": ("Indonesia", -2.2, 117.3),
    "IE": ("Ireland", 53.2, -8.1), "IL": ("Israel", 31.4, 35.0),
    "IN": ("India", 22.9, 79.6), "IQ": ("Iraq", 33.0, 43.7),
    "IR": ("Iran", 32.6, 54.3), "IT": ("Italy", 42.8, 12.6),
    "JM": ("Jamaica", 18.1, -77.3), "JO": ("Jordan", 31.2, 36.5),
    "JP": ("Japan", 36.6, 138.3), "KE": ("Kenya", 0.5, 37.9),
    "KH": ("Cambodia", 12.7, 104.9), "KR": ("South Korea", 36.4, 127.8),
    "KW": ("Kuwait", 29.3, 47.6), "LA": ("Laos", 18.5, 103.8),
    "LK": ("Sri Lanka", 7.6, 80.7), "MA": ("Morocco", 31.8, -6.3),
    "MG": ("Madagascar", -19.4, 46.7), "MM": ("Myanmar", 21.2, 96.5),
    "MN": ("Mongolia", 46.8, 103.1), "MV": ("Maldives", 3.7, 73.5),
    "MX": ("Mexico", 23.9, -102.5), "MY": ("Malaysia", 3.8, 109.7),
    "MZ": ("Mozambique", -17.3, 35.5), "NA": ("Namibia", -22.1, 17.2),
    "NG": ("Nigeria", 9.6, 8.1), "NL": ("Netherlands", 52.2, 5.5),
    "NO": ("Norway", 64.6, 12.7), "NP": ("Nepal", 28.3, 84.0),
    "NZ": ("New Zealand", -41.8, 172.5), "OM": ("Oman", 20.6, 56.1),
    "PA": ("Panama", 8.5, -80.1), "PE": ("Peru", -9.2, -75.0),
    "PG": ("Papua New Guinea", -6.5, 145.2), "PH": ("Philippines", 11.8, 122.9),
    "PK": ("Pakistan", 29.9, 69.4), "PL": ("Poland", 52.1, 19.4),
    "PT": ("Portugal", 39.6, -8.0), "QA": ("Qatar", 25.3, 51.2),
    "RU": ("Russia", 61.5, 96.7), "SA": ("Saudi Arabia", 24.1, 44.5),
    "SE": ("Sweden", 62.8, 16.7), "SG": ("Singapore", 1.35, 103.8),
    "TH": ("Thailand", 15.1, 101.0), "TR": ("Turkey", 39.0, 35.2),
    "TW": ("Taiwan", 23.7, 121.0), "TZ": ("Tanzania", -6.3, 34.8),
    "UA": ("Ukraine", 49.0, 31.4), "UG": ("Uganda", 1.3, 32.4),
    "US": ("United States", 39.8, -98.6), "UY": ("Uruguay", -32.8, -56.0),
    "VE": ("Venezuela", 7.1, -66.2), "VN": ("Vietnam", 16.6, 106.3),
    "ZA": ("South Africa", -29.0, 25.1), "ZM": ("Zambia", -13.5, 27.8),
    "ZW": ("Zimbabwe", -19.0, 29.9),
}


def centroid(iso2):
    """(name, lat, lon) or None for codes not in the table (including GBIF's 'ZZ' = unknown)."""
    return CENTROIDS.get((iso2 or "").upper())
