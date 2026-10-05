#!/usr/bin/env python3
"""Build crags.json for Grip from the SMC routes database facts (data/smc_coast.json) plus manual overrides."""
import json, math, collections, sys, re

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/smc_coast.json"
OVR = sys.argv[2] if len(sys.argv) > 2 else "data/overrides.json"
OUT = sys.argv[3] if len(sys.argv) > 3 else "crags.json"

d = json.load(open(SRC)); R = {r["id"]: r for r in d["records"]}
try:
    overrides = json.load(open(OVR))
except FileNotFoundError:
    overrides = {"walls": {}, "drop": []}
kids = collections.defaultdict(list)
for r in R.values():
    kids[r["parent"]].append(r)
for k in kids:
    kids[k].sort(key=lambda r: r["id"])

ZONES = {
    "aberdeen_south": {"name": "Nigg Bay to Findon", "lat": 57.095, "lon": -2.075, "coast_faces": 112.5},
    "newtonhill": {"name": "Portlethen to Newtonhill", "lat": 57.045, "lon": -2.125, "coast_faces": 112.5},
    "muchalls": {"name": "Newtonhill South to Muchalls", "lat": 57.005, "lon": -2.165, "coast_faces": 112.5},
    "stonehaven": {"name": "Stonehaven and south", "lat": 56.955, "lon": -2.200, "coast_faces": 112.5},
    "collieston": {"name": "Collieston to Whinnyfold", "lat": 57.365, "lon": -1.900, "coast_faces": 112.5},
    "buchan": {"name": "Cruden Bay to Boddam", "lat": 57.44, "lon": -1.81, "coast_faces": 112.5},
    "macduff": {"name": "Macduff to Pennan", "lat": 57.675, "lon": -2.435, "coast_faces": 0},
    "rosehearty": {"name": "Rosehearty", "lat": 57.68, "lon": -2.17, "coast_faces": 0},
    "cullen": {"name": "Cullen and Portsoy", "lat": 57.695, "lon": -2.76, "coast_faces": 0},
}
SECTION_ZONE = {  # section or area id -> zone (nearest ancestor wins; fallback: nearest zone by coordinates)
    4119: "aberdeen_south", 4175: "aberdeen_south", 4208: "aberdeen_south", 4236: "newtonhill", 4301: "muchalls",
    4330: "stonehaven", 4331: "stonehaven", 4332: "stonehaven", 4333: "stonehaven", 7759: "stonehaven", 7760: "stonehaven",
    4335: "collieston", 4357: "buchan", 4400: "buchan", 4428: "buchan", 4449: "buchan",
    4494: "cullen", 4501: "cullen", 4510: "cullen", 4511: "cullen", 4512: "cullen", 4537: "macduff", 4555: "rosehearty", 4493: "cullen",
}
SECTION_LABEL = {4501: "Logie Head and Portsoy", 4510: "Logie Head and Portsoy", 4511: "Logie Head and Portsoy", 4512: "Logie Head and Portsoy"}
REGION_IDS = {9, 4118, 4334, 4468, 4493}

def nearest_zone(lat, lon):
    best = None
    for k, z in ZONES.items():
        dd = (lat - z["lat"]) ** 2 + ((lon - z["lon"]) * math.cos(math.radians(lat))) ** 2
        if best is None or dd < best[0]:
            best = (dd, k)
    return best[1]

ASPECTS = {"north": "N", "north-east": "NE", "northeast": "NE", "east": "E", "south-east": "SE", "southeast": "SE",
           "south": "S", "south-west": "SW", "southwest": "SW", "west": "W", "north-west": "NW", "northwest": "NW",
           "north west": "NW", "south east": "SE", "north east": "NE", "south west": "SW"}

def parse_aspect(s):
    """First compass point named; None for 'all', 'various' or blank."""
    s = (s or "").strip().lower()
    if not s or s.startswith("all") or s.startswith("various"):
        return None, (s or None)
    first = re.split(r"\s*(?:,|&|and|to|/)\s*", s)[0].strip()
    return ASPECTS.get(first), (s if ("and" in s or "&" in s or "to" in s or "," in s) else None)

def parse_tidal(s):
    s = (s or "").lower()
    if not s:
        return None
    if "non" in s:
        return False
    return True  # Tidal, Mainly Tidal, Partially/Partly Tidal

def clean(name):
    return re.sub(r"^The ", "", name).strip()

TOPS = [4118, 4334, 4493]
AREA_LABEL = {4330: "Stonehaven South", 4494: "Findochty to Cullen", 4537: "Macduff to Rosehearty", 4512: "Redhythe Point"}  # areas that act as section headings
BOULDER = re.compile(r"boulder", re.I)

def walk_sections():
    """Yield (section_label, crag). A crag is the first node below a section that carries coordinates (or a leaf);
    nodes above that are areas and are descended through; nodes below are its walls."""
    def walk(node, label):
        if node["id"] in AREA_LABEL:
            label = AREA_LABEL[node["id"]]
        if node.get("lat") or not kids[node["id"]]:
            yield label, node
        else:
            for c in kids[node["id"]]:
                yield from walk(c, label)
    for top in TOPS:
        for sec in kids[top]:
            if sec["type"] == "Region":
                for c in kids[sec["id"]]:
                    yield from walk(c, sec["name"])
            else:
                yield from walk(sec, SECTION_LABEL.get(sec["id"], R[top]["name"]))

def inherit(r, key):
    x = r
    while x:
        if x.get(key):
            return x[key]
        x = R.get(x["parent"])
    return None

def coords(r):
    x = r
    while x:
        if x.get("lat"):
            return x["lat"], x["lon"]
        x = R.get(x["parent"])
    return None, None

def leaves(crag):
    out = []
    def rec(x, path):
        ch = kids[x["id"]]
        if not ch:
            out.append((x, path))
        for c in ch:
            rec(c, path + [clean(c["name"])])
    rec(crag, [])
    return out

def merged_flags(r, crag):
    f = dict(crag.get("flags", {}))
    f.update(r.get("flags", {}))
    return f

crags, dropped = [], []
seen_labels = set()
def section_id(crag):
    x = crag
    while x and x["type"] != "Region":
        x = R.get(x["parent"])
    return x["id"] if x else None

for sec_label, crag in walk_sections():
    if BOULDER.search(crag["name"]):
        dropped.append((crag["name"], "bouldering"))
        continue
    zone, x = None, crag
    while x and not zone:
        zone = SECTION_ZONE.get(x["id"])
        x = R.get(x["parent"])
    lat, lon = coords(crag)
    if not zone and lat:
        zone = nearest_zone(lat, lon)
    if not zone:
        dropped.append((crag["name"], "no zone"))
        continue
    items = leaves(crag) if kids[crag["id"]] else [(crag, [])]
    if kids[crag["id"]] and crag.get("aspect"):
        own = parse_aspect(crag["aspect"])[0]
        if own and own not in {parse_aspect(l.get("aspect"))[0] for l, _ in items}:
            items = [(crag, [])] + items  # none of the sub-sectors share the crag's own aspect, so the crag itself counts as a wall
    for r, path in items:
        wall = " – ".join(path) if path else None
        if wall and BOULDER.search(wall):
            continue
        asp, asp_note = parse_aspect(inherit(r, "aspect"))
        tid = parse_tidal(inherit(r, "tidal"))
        wlat, wlon = coords(r)
        f = merged_flags(r, crag)
        e = {"name": crag["name"], "zone": zone, "section": sec_label, "smc_id": r["id"], "smc_crag_id": crag["id"],
             "aspect": asp, "rock": inherit(r, "rock") or None, "type": "trad"}
        if wall:
            e["wall"] = wall
        if asp_note:
            e["aspect_note"] = asp_note
        if tid:
            e["tidal"] = True
        if r.get("tidal") or crag.get("tidal"):
            e["tidal_note"] = inherit(r, "tidal")
        if wlat:
            e["lat"], e["lon"] = wlat, wlon
        if f.get("sheltered"):
            e["sheltered"] = True
        if f.get("inlet"):
            e["inlet"] = True
        if f.get("seaShelter"):
            e["sea_sheltered"] = True
        if f.get("seep"):
            e["seeps"] = True
        if f.get("birds") in ("affected", "restricted", "mixed"):
            e["birds"] = {"months": [4, 5, 6, 7], "level": "restricted" if f["birds"] == "restricted" else "affected",
                          "note": "Birds reported nesting; months not confirmed"}
        elif f.get("birds") == "clear":
            e["birds"] = {"months": [], "level": "clear", "note": "Free of nesting birds (SMC database)"}
        label = e["name"] + (f" ({e['wall']})" if wall else "")
        if label in seen_labels:
            dropped.append((label, "duplicate"))
            continue
        seen_labels.add(label)
        crags.append(e)

# manual overrides by label
for label, ov in overrides.get("walls", {}).items():
    hits = [c for c in crags if (c["name"] + (f" ({c['wall']})" if c.get("wall") else "")) == label]
    if not hits:
        dropped.append((label, "override target not found"))
        continue
    for c in hits:
        for k, v in ov.items():
            if v is None:
                c.pop(k, None)
            else:
                c[k] = v
drop = set(overrides.get("drop", []))
crags = [c for c in crags if (c["name"] + (f" ({c['wall']})" if c.get("wall") else "")) not in drop]

out = {"zones": ZONES, "crags": crags, "source": "Crag details from the SMC routes database (routes.smc.org.uk), with local corrections"}
json.dump(out, open(OUT, "w"), indent=1, ensure_ascii=False)
print(f"{len(crags)} walls across {len({c['name'] for c in crags})} crags in {len({c['section'] for c in crags})} sections; dropped {len(dropped)}")
for x in dropped[:20]:
    print("  dropped:", x)
