from __future__ import annotations

import json
import urllib.parse
import urllib.request

from config import NOMINATIM_URL, OSM_USER_AGENT

PLACE_TYPES = {"city", "town", "village", "hamlet", "suburb", "quarter", "neighbourhood"}


def _name_parts(item: dict) -> set[str]:
    address = item.get("address", {}) if isinstance(item.get("address"), dict) else {}
    values = [item.get("name", ""), item.get("display_name", "")]
    values.extend(str(address.get(k, "")) for k in ["city", "town", "village", "hamlet", "suburb", "municipality"])
    return {str(v).strip().lower() for v in values if str(v).strip()}


def _score(item: dict, query: str) -> int:
    q = query.strip().lower()
    osm_class = str(item.get("class", ""))
    typ = str(item.get("type", ""))
    addresstype = str(item.get("addresstype", ""))
    names = _name_parts(item)
    score = 0
    if q in names:
        score += 260
    elif any(name.startswith(q) for name in names):
        score += 70
    if osm_class == "place" or typ in PLACE_TYPES or addresstype in PLACE_TYPES:
        score += 90
    if item.get("osm_type") == "node" and (osm_class == "place" or typ in PLACE_TYPES):
        score += 320
    if addresstype in {"village", "town", "city", "hamlet"}:
        score += 40
    if osm_class == "boundary" or typ == "administrative" or item.get("osm_type") == "relation":
        score -= 420
    if item.get("importance"):
        score += int(float(item.get("importance", 0)) * 15)
    return -score


def _make_request(params: dict) -> list[dict]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{NOMINATIM_URL}?{query}", headers={"User-Agent": OSM_USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch(query: str, limit: int) -> list[dict]:
    base = {
        "format": "jsonv2",
        "limit": str(limit),
        "polygon_geojson": "0",
        "addressdetails": "1",
        "namedetails": "1",
        "countrycodes": "de",
        "dedupe": "1",
    }
    payloads = []
    for q in [query, f"{query}, Sachsen, Deutschland", f"{query}, Deutschland"]:
        payloads.extend(_make_request({**base, "q": q, "featureType": "settlement"}))
        payloads.extend(_make_request({**base, "q": q}))
    if len(query.split()) == 1:
        payloads.extend(_make_request({**base, "city": query, "country": "Deutschland"}))
    seen = set()
    ordered = []
    for item in sorted(payloads, key=lambda it: _score(it, query)):
        key = (item.get("osm_type"), item.get("osm_id"), item.get("lat"), item.get("lon"))
        if key in seen:
            continue
        seen.add(key)
        bbox = item.get("boundingbox", [])
        named = item.get("namedetails", {}) if isinstance(item.get("namedetails"), dict) else {}
        ordered.append({
            "name": item.get("display_name", ""),
            "short_name": named.get("name") or item.get("name", ""),
            "lat": float(item.get("lat", 0.0)),
            "lon": float(item.get("lon", 0.0)),
            "bbox": [float(v) for v in bbox] if len(bbox) == 4 else [],
            "class": item.get("class", ""),
            "type": item.get("type", ""),
            "addresstype": item.get("addresstype", ""),
        })
    return ordered[:limit]


def search_places(query: str, limit: int = 8) -> list[dict]:
    text = query.strip()
    if not text:
        return []
    variants = [text]
    if " " in text:
        variants.append(text.replace(" ", ""))
    for variant in dict.fromkeys(variants):
        results = _fetch(variant, limit)
        if results:
            return results
    return []
