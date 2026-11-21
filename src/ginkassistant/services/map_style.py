"""
Gink's own map style (0.1.160): what a real map looks like in Gink -- light and calm like the maps people know (soft
land, blue water, green parks, white streets, yellow motorways, quiet grey neighbourhood names), and a dark version.

For vector maps drawn on the device by MapLibre GL (ui/live_media.py) from OpenMapTiles-schema tiles -- OpenFreeMap's
OpenStreetMap data through Gink's server (backend_server: /vmap/style.json, /vmap/t/..., /vmap/fonts/...). No sprite
file: the few pictures the style uses (road number shields "gink-shield", place dots "gink-poi-<group>") are drawn by
the page itself (styleimagemissing), in the colours in the style's metadata.
"""
from __future__ import annotations

import re

FONT = {"regular": ["Noto Sans Regular"], "bold": ["Noto Sans Bold"], "italic": ["Noto Sans Italic"]}
FONT_NAMES = {name for stack in FONT.values() for name in stack}

ATTRIBUTION = ('<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> '
               '<a href="https://www.openmaptiles.org/" target="_blank" rel="noopener">&copy; OpenMapTiles</a> '
               'Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>')

PALETTES = {
    "light": {
        "land": "#F5F4F0", "wood": "#CDE6C1", "grass": "#D9EECF", "farmland": "#EEF1E1", "wetland": "#D6ECE3",
        "sand": "#F3ECD6", "ice": "#FFFFFF", "rock": "#E7E5E0", "commercial": "#F1EEE9", "industrial": "#EEECE7",
        "cemetery": "#DCEAD4", "hospital": "#F8E6E9", "school": "#F2EDDF", "pitch": "#D3EBC9", "park": "#D2ECC4",
        "water": "#A3D3F3", "building": "#EAE8E3", "building_line": "#DCD9D3", "runway": "#E1DFDA",
        "motorway": "#FCD777", "motorway_case": "#E4B24E", "trunk": "#FDE29A", "trunk_case": "#E6C26E",
        "major": "#FFFFFF", "major_case": "#D6D2C9", "minor": "#FFFFFF", "minor_case": "#E2DFD8",
        "path": "#D5CFC3", "rail": "#C8C4BD", "border": "#ADA8BD", "border_state": "#CCC7D6",
        "city": "#1F2225", "town": "#2B2F34", "village": "#3E4349", "hood": "#8A8D93", "road_text": "#5D6168",
        "water_text": "#3D7BAF", "park_text": "#4B7A3F", "halo": "#FFFFFF", "country": "#5B5E66",
        "shield_text": "#3A3E44", "shield": "#FFFFFF", "shield_line": "#C9C5BC",
        "poi_food": "#C2410C", "poi_shop": "#3B5BDB", "poi_culture": "#6741D9", "poi_nature": "#2B8A3E",
        "poi_health": "#C92A2A", "poi_transport": "#1864AB", "poi_lodging": "#9C36B5", "poi_other": "#5C5F66",
    },
    "dark": {
        "land": "#1D2023", "wood": "#1F3224", "grass": "#213529", "farmland": "#22272A", "wetland": "#1E3130",
        "sand": "#2D2A23", "ice": "#2A2F33", "rock": "#26292C", "commercial": "#212428", "industrial": "#202326",
        "cemetery": "#20302A", "hospital": "#2D2326", "school": "#292722", "pitch": "#203327", "park": "#1F3427",
        "water": "#173A56", "building": "#2A2E33", "building_line": "#34393F", "runway": "#2C3034",
        "motorway": "#6B5A2F", "motorway_case": "#4C4024", "trunk": "#5B5131", "trunk_case": "#443C26",
        "major": "#4A4F56", "major_case": "#32363B", "minor": "#3B3F45", "minor_case": "#2C3035",
        "path": "#4B5056", "rail": "#4B4F55", "border": "#6B6680", "border_state": "#4D4A5C",
        "city": "#ECEEF0", "town": "#DADDE1", "village": "#C3C7CC", "hood": "#8E949B", "road_text": "#AEB4BB",
        "water_text": "#80AED4", "park_text": "#88B48E", "halo": "#1D2023", "country": "#B9BEC4",
        "shield_text": "#D6DADF", "shield": "#3A3F45", "shield_line": "#555B62",
        "poi_food": "#FF9B6B", "poi_shop": "#91A7FF", "poi_culture": "#B197FC", "poi_nature": "#69DB7C",
        "poi_health": "#FF8787", "poi_transport": "#74C0FC", "poi_lodging": "#E599F7", "poi_other": "#ADB5BD",
    },
}


def _zoom(stops, base=1.4):
    """A width that grows with the zoom: stops = [(zoom, px), ...]."""
    out = ["interpolate", ["exponential", base], ["zoom"]]
    for z, v in stops:
        out += [z, v]
    return out


def _zoom_match(classes, stops, base=1.4):
    """A width that grows with the zoom and depends on the class: stops = [(zoom, px for `classes`, px otherwise)]
    (MapLibre allows only one zoom curve per expression, so the class choice goes inside it)."""
    out = ["interpolate", ["exponential", base], ["zoom"]]
    for z, yes, no in stops:
        out += [z, ["match", ["get", "class"], list(classes), yes, no]]
    return out


def _name(lang: str):
    """The label: the person's language when the map has it, else English, else the local name in Latin letters."""
    keys = [f"name:{lang}"] if lang and lang != "en" else []
    keys += ["name:en", "name_en", "name:latin", "name"]
    return ["coalesce"] + [["get", k] for k in keys]


# Languages not written in Latin letters: their own names come first; otherwise local names in Latin letters.
NON_LATIN = {"ja", "zh", "ko", "ru", "uk", "be", "bg", "mk", "sr", "ar", "fa", "ur", "he", "el", "th", "hi", "bn", "ka",
             "hy", "am", "ta", "te", "kn", "ml", "si", "km", "lo", "my", "mn", "kk", "ky", "tg", "ne", "mr", "gu", "pa"}


def _local_name(lang: str):
    """Streets, stations, shops and parks: their own (local) name, as people there say it -- "Zürich Wiedikon", not
    "Zurich Wiedikon railway station" -- in Latin letters, or in the person's script when it isn't Latin."""
    if lang in NON_LATIN:
        return ["coalesce", ["get", f"name:{lang}"], ["get", "name"]]
    return ["coalesce", ["get", "name:latin"], ["get", "name"]]


def _cls(*names):
    return ["match", ["get", "class"], list(names), True, False]


# Places on the map (shops, cafés, museums...) in a few groups, each with its own colour: the dot ("gink-poi-<group>")
# and its name. Classes from the OpenMapTiles "poi" layer.
POI_GROUPS = {
    "food": ["restaurant", "fast_food", "food_court", "bakery", "ice_cream", "cafe", "bar", "beer", "pub", "biergarten"],
    "shop": ["shop", "grocery", "supermarket", "clothing_store", "department_store", "mall", "books", "gift", "jewelry",
             "florist", "furniture", "mobile_phone", "optician", "shoes", "alcohol_shop", "convenience", "marketplace"],
    "culture": ["museum", "art_gallery", "theatre", "cinema", "music", "library", "castle", "monument", "attraction",
                "arts_centre", "town_hall", "memorial", "historic", "viewpoint"],
    "nature": ["park", "garden", "zoo", "campsite", "playground", "dog_park", "picnic_site", "golf", "stadium",
               "swimming", "pitch", "sports_centre", "nature_reserve"],
    "health": ["hospital", "doctor", "pharmacy", "dentist", "clinic", "veterinary"],
    "transport": ["railway", "bus", "aerialway", "ferry_terminal", "harbor", "airport"],
    "lodging": ["lodging", "hotel", "hostel"],
}
# The page draws each group's dot in these colours (the style's metadata carries them).
POI_DOTS = {"food": "#F76707", "shop": "#4C6EF5", "culture": "#7950F2", "nature": "#37B24D", "health": "#F03E3E",
            "transport": "#1C7ED6", "lodging": "#BE4BDB", "other": "#868E96"}


def _poi_group():
    out = ["match", ["get", "class"]]
    for group, classes in POI_GROUPS.items():
        out += [classes, group]
    return out + ["other"]


ROADS = [  # class, min zoom, fill widths, casing widths, colour keys
    ("service", 14, [(14, 0.6), (16, 2.6), (18, 8)], [(14, 1.2), (16, 4), (18, 10)], "minor", "minor_case"),
    ("minor", 12, [(12, 0.5), (14, 1.8), (16, 6), (18, 16)], [(12, 0.9), (14, 3), (16, 8), (18, 19)], "minor", "minor_case"),
    ("tertiary", 10, [(10, 0.5), (13, 1.8), (15, 5), (17, 12), (18, 18)], [(10, 0.9), (13, 2.8), (15, 6.8), (17, 14.5), (18, 21)], "major", "major_case"),
    ("secondary", 9, [(9, 0.5), (12, 1.6), (14, 3.8), (16, 10), (18, 24)], [(9, 1), (12, 2.6), (14, 5.4), (16, 12.5), (18, 27)], "major", "major_case"),
    ("primary", 7, [(7, 0.4), (10, 1.3), (13, 3.8), (16, 11.5), (18, 27)], [(7, 0.8), (10, 2.2), (13, 5.4), (16, 14), (18, 30)], "major", "major_case"),
    ("trunk", 6, [(6, 0.5), (10, 1.7), (13, 4.6), (16, 12.5), (18, 29)], [(6, 0.9), (10, 2.7), (13, 6.4), (16, 15), (18, 32)], "trunk", "trunk_case"),
    ("motorway", 5, [(5, 0.6), (10, 2.1), (13, 5.2), (16, 14), (18, 32)], [(5, 1), (10, 3.2), (13, 7), (16, 16.5), (18, 35)], "motorway", "motorway_case"),
]


def style(theme: str = "light", base: str = "", lang: str = "en") -> dict:
    """The style JSON. base: this server's address (tiles and fonts come from it); lang: the label language."""
    c = PALETTES["dark" if theme == "dark" else "light"]
    lang = lang if re.fullmatch(r"[a-z]{2,3}", lang or "") else "en"
    base = (base or "").rstrip("/")
    name, local = _name(lang), _local_name(lang)
    tunnel_opacity = ["case", ["==", ["get", "brunnel"], "tunnel"], 0.55, 1]
    layers = [
        {"id": "land", "type": "background", "paint": {"background-color": c["land"]}},
        {"id": "landcover", "type": "fill", "source": "omt", "source-layer": "landcover",
         "filter": _cls("wood", "grass", "farmland", "wetland", "sand", "ice", "rock"),
         "paint": {"fill-color": ["match", ["get", "class"], "wood", c["wood"], "grass", c["grass"], "farmland", c["farmland"],
                                  "wetland", c["wetland"], "sand", c["sand"], "ice", c["ice"], c["rock"]],
                   "fill-opacity": ["interpolate", ["linear"], ["zoom"], 4, 0.5, 9, 0.85, 13, 1]}},
        {"id": "landuse", "type": "fill", "source": "omt", "source-layer": "landuse", "minzoom": 10,
         "filter": _cls("commercial", "retail", "industrial", "cemetery", "hospital", "school", "university", "college",
                        "stadium", "pitch", "playground", "zoo", "theme_park"),
         "paint": {"fill-color": ["match", ["get", "class"], ["commercial", "retail"], c["commercial"], "industrial", c["industrial"],
                                  "cemetery", c["cemetery"], "hospital", c["hospital"], ["school", "university", "college"], c["school"],
                                  c["pitch"]],
                   "fill-opacity": ["interpolate", ["linear"], ["zoom"], 10, 0, 12, 0.9]}},
        {"id": "park", "type": "fill", "source": "omt", "source-layer": "park",
         "paint": {"fill-color": c["park"], "fill-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.4, 10, 0.85]}},
        {"id": "water", "type": "fill", "source": "omt", "source-layer": "water",
         "filter": ["!=", ["get", "brunnel"], "tunnel"], "paint": {"fill-color": c["water"]}},
        {"id": "waterway", "type": "line", "source": "omt", "source-layer": "waterway", "minzoom": 9,
         "filter": ["!=", ["get", "brunnel"], "tunnel"],
         "layout": {"line-cap": "round", "line-join": "round"},
         "paint": {"line-color": c["water"], "line-width": _zoom_match(["river", "canal"], [(9, 0.8, 0.2), (13, 2.5, 0.8),
                                                                                           (17, 9, 3)])}},
        {"id": "runway", "type": "line", "source": "omt", "source-layer": "aeroway", "minzoom": 11,
         "filter": _cls("runway", "taxiway"),
         "paint": {"line-color": c["runway"], "line-width": _zoom_match(["runway"], [(11, 2, 0.3), (14, 12, 2.5),
                                                                                    (17, 50, 10)])}},
        {"id": "building", "type": "fill", "source": "omt", "source-layer": "building", "minzoom": 13,
         "paint": {"fill-color": c["building"], "fill-outline-color": c["building_line"],
                   "fill-opacity": ["interpolate", ["linear"], ["zoom"], 13, 0, 14.5, 0.7, 16, 1]}},
        {"id": "path", "type": "line", "source": "omt", "source-layer": "transportation", "minzoom": 15,
         "filter": _cls("path", "track"),
         "paint": {"line-color": c["path"], "line-dasharray": [1.6, 1.4], "line-width": _zoom([(15, 0.6), (18, 1.6)]),
                   "line-opacity": ["interpolate", ["linear"], ["zoom"], 15, 0.45, 17, 0.8]}},
    ]
    for cls, minz, fill, case, fill_key, case_key in ROADS:
        filt = ["all", ["==", ["get", "class"], cls]]
        layers.append({"id": f"{cls}-case", "type": "line", "source": "omt", "source-layer": "transportation",
                       "minzoom": max(minz, 11) if cls not in ("motorway", "trunk") else minz, "filter": filt,
                       "layout": {"line-cap": "round", "line-join": "round"},
                       "paint": {"line-color": c[case_key], "line-width": _zoom(case), "line-opacity": tunnel_opacity}})
    for cls, minz, fill, case, fill_key, case_key in ROADS:
        layers.append({"id": cls, "type": "line", "source": "omt", "source-layer": "transportation", "minzoom": minz,
                       "filter": ["==", ["get", "class"], cls],
                       "layout": {"line-cap": "round", "line-join": "round"},
                       "paint": {"line-color": c[fill_key], "line-width": _zoom(fill), "line-opacity": tunnel_opacity}})
    layers += [
        {"id": "rail", "type": "line", "source": "omt", "source-layer": "transportation", "minzoom": 11,
         "filter": _cls("rail", "transit"),
         "paint": {"line-color": c["rail"], "line-width": _zoom([(11, 0.6), (16, 2.2)]),
                   "line-opacity": ["case", ["==", ["get", "brunnel"], "tunnel"], 0.3, 1]}},
        {"id": "border-state", "type": "line", "source": "omt", "source-layer": "boundary", "minzoom": 4,
         "filter": ["all", ["==", ["get", "admin_level"], 4], ["!=", ["get", "maritime"], 1]],
         "paint": {"line-color": c["border_state"], "line-dasharray": [3, 2], "line-width": _zoom([(4, 0.6), (10, 1.4)])}},
        {"id": "border", "type": "line", "source": "omt", "source-layer": "boundary",
         "filter": ["all", ["==", ["get", "admin_level"], 2], ["!=", ["get", "maritime"], 1]],
         "paint": {"line-color": c["border"], "line-width": _zoom([(2, 0.7), (8, 1.6), (14, 2.4)])}},
        # ---- names ----
        {"id": "water-name", "type": "symbol", "source": "omt", "source-layer": "water_name",
         "filter": ["!=", ["geometry-type"], "LineString"],
         "layout": {"text-field": name, "text-font": FONT["italic"], "text-size": _zoom([(4, 10), (10, 12), (14, 14)], 1.2),
                    "text-letter-spacing": 0.08, "text-max-width": 8},
         "paint": {"text-color": c["water_text"], "text-halo-color": c["halo"], "text-halo-width": 1}},
        {"id": "water-name-line", "type": "symbol", "source": "omt", "source-layer": "water_name",
         "filter": ["==", ["geometry-type"], "LineString"],
         "layout": {"text-field": name, "text-font": FONT["italic"], "text-size": _zoom([(8, 10), (14, 13)], 1.2),
                    "symbol-placement": "line", "text-letter-spacing": 0.08},
         "paint": {"text-color": c["water_text"], "text-halo-color": c["halo"], "text-halo-width": 1}},
        {"id": "park-name", "type": "symbol", "source": "omt", "source-layer": "park", "minzoom": 13,
         "filter": ["has", "name"],
         "layout": {"text-field": local, "text-font": FONT["regular"], "text-size": 11, "text-max-width": 7,
                    "symbol-sort-key": ["coalesce", ["get", "rank"], 99]},
         "paint": {"text-color": c["park_text"], "text-halo-color": c["halo"], "text-halo-width": 1.2}},
        {"id": "road-shield", "type": "symbol", "source": "omt", "source-layer": "transportation_name", "minzoom": 8,
         "filter": ["all", ["has", "ref"], ["<=", ["coalesce", ["get", "ref_length"], 9], 6],
                    ["match", ["get", "class"], ["motorway", "trunk", "primary"], True, False]],
         "layout": {"text-field": ["get", "ref"], "text-font": FONT["bold"], "text-size": 9.5,
                    "icon-image": "gink-shield", "icon-text-fit": "both", "icon-text-fit-padding": [1.5, 4, 1.5, 4],
                    "symbol-placement": "line", "symbol-spacing": 420, "text-rotation-alignment": "viewport",
                    "icon-rotation-alignment": "viewport"},
         "paint": {"text-color": c["shield_text"]}},
        {"id": "road-name", "type": "symbol", "source": "omt", "source-layer": "transportation_name", "minzoom": 13,
         "filter": ["match", ["get", "class"], ["motorway", "trunk", "primary", "secondary", "tertiary", "minor", "service"], True, False],
         "layout": {"text-field": local, "text-font": FONT["regular"], "symbol-placement": "line",
                    "text-size": _zoom([(13, 9.5), (16, 12), (18, 13)], 1.2), "text-max-angle": 30, "symbol-spacing": 320},
         "paint": {"text-color": c["road_text"], "text-halo-color": c["halo"], "text-halo-width": 1.2}},
        # ---- places: big stations and airports early, the rest close up ----
        {"id": "airport", "type": "symbol", "source": "omt", "source-layer": "aerodrome_label", "minzoom": 9,
         "filter": ["has", "iata"],
         "layout": {"text-field": name, "text-font": FONT["regular"], "text-size": _zoom([(9, 10.5), (13, 12)], 1.2),
                    "icon-image": "gink-poi-transport", "text-variable-anchor": ["left", "right"],
                    "text-radial-offset": 0.75, "text-justify": "auto", "text-max-width": 8},
         "paint": {"text-color": c["poi_transport"], "text-halo-color": c["halo"], "text-halo-width": 1.2}},
        {"id": "station", "type": "symbol", "source": "omt", "source-layer": "poi", "minzoom": 12,
         "filter": ["all", ["==", ["get", "class"], "railway"], ["has", "name"],
                    ["match", ["get", "subclass"], ["station", "halt"], True, False]],
         "layout": {"text-field": local, "text-font": FONT["bold"], "text-size": _zoom([(12, 10), (16, 12)], 1.2),
                    "icon-image": "gink-poi-transport", "text-variable-anchor": ["left", "right", "top"],
                    "text-radial-offset": 0.75, "text-justify": "auto", "text-max-width": 8,
                    "symbol-sort-key": ["coalesce", ["get", "rank"], 99]},
         "paint": {"text-color": c["poi_transport"], "text-halo-color": c["halo"], "text-halo-width": 1.2}},
        {"id": "poi", "type": "symbol", "source": "omt", "source-layer": "poi", "minzoom": 15,
         "filter": ["all", ["has", "name"], ["!=", ["get", "class"], "railway"],
                    ["match", ["get", "class"], ["parking", "toilets", "atm", "drinking_water", "information", "entrance",
                                                 "bicycle_parking", "bicycle_rental", "waste_basket", "bench", "fuel",
                                                 "car", "post", "telephone"], False, True]],
         "layout": {"text-field": local, "text-font": FONT["regular"], "text-size": _zoom([(15, 10.5), (18, 12)], 1.2),
                    "icon-image": ["concat", "gink-poi-", _poi_group()], "text-variable-anchor": ["left", "right"],
                    "text-radial-offset": 0.75, "text-justify": "auto", "text-max-width": 8,
                    "symbol-sort-key": ["coalesce", ["get", "rank"], 99]},
         "paint": {"text-color": ["match", _poi_group(), "food", c["poi_food"], "shop", c["poi_shop"],
                                  "culture", c["poi_culture"], "nature", c["poi_nature"], "health", c["poi_health"],
                                  "transport", c["poi_transport"], "lodging", c["poi_lodging"], c["poi_other"]],
                   "text-halo-color": c["halo"], "text-halo-width": 1.2}},
        {"id": "hood", "type": "symbol", "source": "omt", "source-layer": "place", "minzoom": 11,
         "filter": _cls("suburb", "neighbourhood", "quarter"),
         "layout": {"text-field": name, "text-font": FONT["bold"], "text-transform": "uppercase", "text-letter-spacing": 0.12,
                    "text-size": _zoom([(11, 9), (14, 10.5), (16, 12)], 1.2), "text-max-width": 8,
                    "symbol-sort-key": ["coalesce", ["get", "rank"], 99]},
         "paint": {"text-color": c["hood"], "text-halo-color": c["halo"], "text-halo-width": 1.2}},
        {"id": "village", "type": "symbol", "source": "omt", "source-layer": "place", "minzoom": 10,
         "filter": _cls("village", "hamlet", "isolated_dwelling"),
         "layout": {"text-field": name, "text-font": FONT["regular"], "text-size": _zoom([(10, 10.5), (14, 13)], 1.2),
                    "text-max-width": 8, "symbol-sort-key": ["coalesce", ["get", "rank"], 99]},
         "paint": {"text-color": c["village"], "text-halo-color": c["halo"], "text-halo-width": 1.3}},
        {"id": "town", "type": "symbol", "source": "omt", "source-layer": "place", "minzoom": 6,
         "filter": _cls("town"),
         "layout": {"text-field": name, "text-font": FONT["regular"], "text-size": _zoom([(6, 10.5), (10, 13), (14, 16)], 1.2),
                    "text-max-width": 8, "symbol-sort-key": ["coalesce", ["get", "rank"], 99]},
         "paint": {"text-color": c["town"], "text-halo-color": c["halo"], "text-halo-width": 1.4}},
        {"id": "city", "type": "symbol", "source": "omt", "source-layer": "place", "minzoom": 3, "maxzoom": 16,
         "filter": _cls("city"),
         "layout": {"text-field": name, "text-font": FONT["bold"], "text-size": _zoom([(3, 10.5), (8, 14), (12, 19), (15, 22)], 1.2),
                    "text-max-width": 8, "symbol-sort-key": ["coalesce", ["get", "rank"], 99]},
         "paint": {"text-color": c["city"], "text-halo-color": c["halo"], "text-halo-width": 1.6}},
        {"id": "state", "type": "symbol", "source": "omt", "source-layer": "place", "minzoom": 4, "maxzoom": 8,
         "filter": _cls("state"),
         "layout": {"text-field": name, "text-font": FONT["regular"], "text-transform": "uppercase", "text-letter-spacing": 0.1,
                    "text-size": _zoom([(4, 9), (7, 11)]), "text-max-width": 8},
         "paint": {"text-color": c["hood"], "text-halo-color": c["halo"], "text-halo-width": 1.2}},
        {"id": "country", "type": "symbol", "source": "omt", "source-layer": "place", "maxzoom": 8,
         "filter": _cls("country"),
         "layout": {"text-field": name, "text-font": FONT["bold"], "text-size": _zoom([(1, 10), (4, 13), (7, 16)]),
                    "text-max-width": 8, "symbol-sort-key": ["coalesce", ["get", "rank"], 99]},
         "paint": {"text-color": c["country"], "text-halo-color": c["halo"], "text-halo-width": 1.5}},
    ]
    return {
        "version": 8, "name": f"Gink {('dark' if theme == 'dark' else 'light')}",
        "metadata": {"gink:theme": "dark" if theme == "dark" else "light", "gink:halo": c["halo"], "gink:land": c["land"],
                     "gink:shield": [c["shield"], c["shield_line"]], "gink:poi": POI_DOTS},
        "sources": {"omt": {"type": "vector", "tiles": [f"{base}/vmap/t/{{z}}/{{x}}/{{y}}.pbf"], "minzoom": 0, "maxzoom": 14,
                            "attribution": ATTRIBUTION}},
        "glyphs": f"{base}/vmap/fonts/{{fontstack}}/{{range}}.pbf",
        "layers": layers,
    }
