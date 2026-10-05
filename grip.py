#!/usr/bin/env python3
"""Grip: a dry-rock forecast for the sea cliffs of north-east Scotland.

Pulls Open-Meteo forecasts (Met Office, ECMWF, ICON) and the Open-Meteo marine
forecast, estimates the state of the rock hour by hour for every wall, and
writes a static page to ./site/index.html. Optionally sends a daily ntfy push.

Standard library only. Run: python grip.py
Set GRIP_FAKE=1 to run offline with synthetic data (for testing).
"""
import json
import math
import os
import random
import re
import shutil
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/London")
HERE = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.join(HERE, "site")
STATE_FILE = os.path.join(HERE, "state.json")
PAGE_URL = os.environ.get("GRIP_PAGE_URL", "")

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
ARCHIVE_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"  # archived model runs, for days more than ~80 days ago
REANALYSIS_URL = "https://archive-api.open-meteo.com/v1/archive"  # ERA5 reanalysis: the best record of what the weather actually did

# id, label, forecast days requested, weight in the blend (Met Office drops to 1 beyond 48 h)
MODELS = [
    ("ukmo_seamless", "Met Office", 7, 2.5),
    ("ecmwf_ifs025", "ECMWF", 8, 1.0),
    ("icon_seamless", "ICON", 7, 1.0),
]
HOURLY_FULL = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m", "vapour_pressure_deficit",
    "precipitation", "cloud_cover", "cloud_cover_2m", "visibility",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "sunshine_duration",
]
HOURLY_SAFE = [v for v in HOURLY_FULL if v not in ("cloud_cover_2m", "visibility", "vapour_pressure_deficit")]
MARINE_FULL = ["wave_height", "wave_direction", "wave_period", "sea_surface_temperature", "sea_level_height_msl"]
MARINE_SAFE = ["wave_height", "wave_direction"]
PAST_DAYS = 3

# Logging form (Google Form, anonymous) and its published response sheet
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSems6Y-X4CypSu96Vt8DuGh4yH1bWv05wjYPxsN8fnhKPMWBA/viewform"
FORM_POST = "https://docs.google.com/forms/d/e/1FAIpQLSems6Y-X4CypSu96Vt8DuGh4yH1bWv05wjYPxsN8fnhKPMWBA/formResponse"
FORM_ENTRIES = {"crag": "entry.769015387", "wall": "entry.1131909785", "date": "entry.2085482145",
                "from": "entry.764556216", "until": "entry.1083400377", "feel": "entry.1126435114",
                "problems": "entry.525175392", "initials": "entry.1772081994", "other": "entry.960162223",
                "contact": "entry.1160807926"}  # the page log form submits into the Google Form by these IDs
FORM_CRAGS_FILE = os.path.join(HERE, "data", "form_crags.json")  # the Google Form's crag options, in order
FORM_ELSEWHERE = "Somewhere else on the coast"
LOG_FEELS = ["Soaked: wet rock", "Greasy: damp and slippery, training at best", "Climbable: fine with care",
             "Grippy: good friction", "Prime: as dry as this coast gets"]  # exact option strings on the Google Form
FEEL_ALIASES = {"Climbable": "Usable", "Grippy": "Crisp"}  # band names as people see them -> the internal keys logs are stored under
LOG_PROBLEMS = ["Wet from rain", "Greasy or sweating", "Seepage", "Haar or fog", "Spray from the sea",
                "Still wet from the night before", "Fine until the sun left the face"]
NOTES_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeFKYLfOJ5V7yZiKIyMd9RxH9yiBWbQ27h_CLWvUP52EbOWPg/viewform"
NOTES_CRAG = "entry.1230562053"
NOTES_WALL = "entry.763167181"
FEEDBACK_URL = "https://docs.google.com/forms/d/e/1FAIpQLSc7K1EeOhs2swtdZqFqffm3A02RSLHIn01_sKwN85Xlw-7qGQ/viewform"
POPULAR_FILE = os.path.join(HERE, "data", "popular.json")  # the crags people climb most, in order, for the front page table
LOG_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTJvP_UEtYosrIGLGEKbwuYLZn64xxAUlsedFZoAk5iESNDN9MBM2bgpkyYODvse42nNa-1JIuqZBDf/pub?output=csv"
CAL_FILE = os.path.join(HERE, "calibration.json")
MODEL_VERSION = "3.7"  # bump when the scoring or crag details change; logged days are then re-scored
CAL_CSV = os.path.join(HERE, "calibration.csv")
FEEL = {"Soaked": 0.5, "Greasy": 2.5, "Usable": 4.5, "Crisp": 6.5, "Prime": 8.5}  # band centres, used only to order the bands
LABEL_ALIASES = {  # names used in logs before the crag list was rebuilt from the SMC database
    "Souter Head (Grassy Pinnacle South Wall)": "Souter Head (Grassy Pinnacle – South Wall)",
    "Souter Head (Grassy Pinnacle East Wall)": "Souter Head (Grassy Pinnacle – East Wall)",
    "Souter Head (Jade Buttress)": "Souter Head (Jade Buttress Area – Overhanging Gully)",
    "Newtonhill (Backdoor Wall)": "Newtonhill North (Back Door Wall)",
    "Newtonhill (Harbour Wall)": "Newtonhill North (Harbour Wall)",
    "Logie Head (Embankment)": "Logie Head (Embankment One)",
    "Murray Heugh (Everready Slab)": "Murray Heugh (Eveready Slab)",
    "Murray Heugh (Main walls)": "Murray Heugh (Main Face)",
    "Murdoch Head (Round Tower)": "The Round Tower",
    "Murdoch Head (East Wall)": "The Warlord Cliff",
    "Murdoch Head (Revision Slab and Broke Back Wall)": "North Glash Quarry",
    "Rosehearty": "Murcurry",
    "Red Wall": "The Red Wall",
    "Meackie Point": "Meackie Point (Point Wall)",
    "Redhythe Point": "Redhythe Point Eastern Area",
}
FEEL_RANGE = {"Soaked": (0, 2), "Greasy": (2, 4), "Usable": (4, 6), "Crisp": (6, 8), "Prime": (8, 11)}  # lower edge included, upper excluded
FEEL_NAME = {"Soaked": "Soaked", "Greasy": "Greasy", "Usable": "Climbable", "Crisp": "Grippy", "Prime": "Prime"}  # internal key -> name shown

COMPASS = {"N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5,
           "SE": 135, "SSE": 157.5, "S": 180, "SSW": 202.5, "SW": 225,
           "WSW": 247.5, "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5}
POINTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# Grip index 0-10. (min index, name, note, css class, range label)
BANDS = [
    (8, "Prime", "As dry as this coast gets", "b5", "8 to 10"),
    (6, "Grippy", "Good friction", "b4", "6 to 7"),
    (4, "Climbable", "Fine with care; choose the wall well", "b3", "4 to 5"),
    (2, "Greasy", "Damp and slippery; training at best", "b2", "2 to 3"),
    (0, "Soaked", "Wet rock", "b1", "0 to 1"),
]
USABLE = 4  # index at or above this counts as a climbable hour


# ---------------------------------------------------------------- utilities
def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get_json(url, params, tries=3):
    q = urllib.parse.urlencode(params, safe=",")
    full = f"{url}?{q}"
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "grip-forecast/2.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            last = e
            body = ""
            if hasattr(e, "read"):
                try:
                    body = e.read().decode()[:300]
                except Exception:  # noqa: BLE001
                    pass
            log(f"  request failed ({i + 1}/{tries}): {e} {body}")
            if hasattr(e, "code") and e.code == 400:
                break
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"request failed: {last}")


def rnd(x):
    return int(math.floor(x + 0.5))


def band(index):
    s = rnd(index)
    for lo, name, note, css, rng in BANDS:
        if s >= lo:
            return name, note, css
    return BANDS[-1][1:4]


def to_index(points):
    return max(0.0, min(10.0, 3.0 + points / 2.0))


def compass(deg):
    if deg is None:
        return "?"
    return POINTS[int(((deg % 360) + 22.5) // 45) % 8]


def ang_diff(a, b):
    d = abs((a - b) % 360)
    return 360 - d if d > 180 else d


def fpt(v):
    return "-" if v is None else f"{v:+.0f}"


# ---------------------------------------------------------------- sun position
def sun_position(dt_utc, lat, lon):
    """Return (azimuth deg clockwise from north, elevation deg). NOAA approximation."""
    n = (dt_utc - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400.0
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    gmst = (18.697374558 + 24.06570982441908 * n) % 24
    lst = math.radians((gmst * 15 + lon) % 360)
    ha = lst - ra
    la = math.radians(lat)
    el = math.asin(math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(ha))
    az = math.atan2(-math.sin(ha), math.tan(dec) * math.cos(la) - math.sin(la) * math.cos(ha))
    return (math.degrees(az) % 360, math.degrees(el))


# ---------------------------------------------------------------- data fetch
def has_values(data, var="relative_humidity_2m"):
    """True if any location in an Open-Meteo reply has a value for var."""
    for d in data if isinstance(data, list) else [data]:
        if any(v is not None for v in d.get("hourly", {}).get(var, [])):
            return True
    return False


def fetch_models(zones, start=None, end=None):
    """Hourly model data per zone. With start/end (ISO dates) it fetches that past window instead."""
    lats = ",".join(str(z["lat"]) for z in zones.values())
    lons = ",".join(str(z["lon"]) for z in zones.values())
    keys = list(zones.keys())
    out = {k: {} for k in keys}
    for mid, label, days, _w in MODELS:
        data = None
        for hourly in (HOURLY_FULL, HOURLY_SAFE):
            log(f"Fetching {label} ({mid}, {len(hourly)} variables{', ' + start + ' to ' + end if start else ''})")
            try:
                params = {"latitude": lats, "longitude": lons, "models": mid, "hourly": ",".join(hourly),
                          "timezone": "Europe/London", "wind_speed_unit": "kmh"}
                url = FORECAST_URL
                if start:
                    params.update({"start_date": start, "end_date": end})
                    if (datetime.now(TZ).date() - date.fromisoformat(start)).days > 80:
                        url = ARCHIVE_URL
                else:
                    params.update({"past_days": PAST_DAYS, "forecast_days": days})
                data = get_json(url, params)
                if start and url == FORECAST_URL and not has_values(data):
                    log(f"  {label}: no data on the forecast API from {start}, using the archive")
                    data = get_json(ARCHIVE_URL, params)
                break
            except Exception as e:  # noqa: BLE001
                log(f"  {label}: {e}")
        if data is None:
            log(f"  skipping {label}")
            continue
        if isinstance(data, dict):
            data = [data]
        for k, d in zip(keys, data):
            out[k][mid] = d.get("hourly", {})
    return out


def fetch_marine(zones, start=None, end=None):
    lats = ",".join(str(z["lat"]) for z in zones.values())
    lons = ",".join(str(z["lon"]) for z in zones.values())
    keys = list(zones.keys())
    for vars_ in (MARINE_FULL, MARINE_SAFE):
        log(f"Fetching marine ({','.join(vars_)})")
        try:
            params = {"latitude": lats, "longitude": lons, "hourly": ",".join(vars_),
                      "timezone": "Europe/London", "cell_selection": "sea"}
            if start:
                params.update({"start_date": start, "end_date": end})
            else:
                params.update({"past_days": PAST_DAYS, "forecast_days": 7})
            data = get_json(MARINE_URL, params)
        except Exception as e:  # noqa: BLE001
            log(f"  marine failed: {e}")
            continue
        if isinstance(data, dict):
            data = [data]
        return {k: d.get("hourly", {}) for k, d in zip(keys, data)}
    return {k: {} for k in keys}


def fake_data(zones):
    """Synthetic data so the page can be built and checked offline."""
    random.seed(4)
    start = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=PAST_DAYS)
    times = [(start + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M") for h in range(24 * 15)]
    models = {}
    marine = {}
    for k in zones:
        models[k] = {}
        base = random.uniform(-2, 2)
        for mid, _l, days, _w in MODELS:
            n = 24 * (days + PAST_DAYS)
            h = {"time": times[:n]}
            h["temperature_2m"] = [12 + base + 4 * math.sin((i % 24 - 9) / 24 * 2 * math.pi) + random.gauss(0, 0.6) for i in range(n)]
            h["relative_humidity_2m"] = [max(45, min(98, 78 + 12 * math.sin(i / 37) - 8 * math.sin((i % 24 - 9) / 24 * 2 * math.pi) + random.gauss(0, 3))) for i in range(n)]
            h["dew_point_2m"] = [t - (100 - r) / 5 for t, r in zip(h["temperature_2m"], h["relative_humidity_2m"])]
            h["vapour_pressure_deficit"] = [None] * n
            h["precipitation"] = [max(0, random.gauss(-0.6, 0.6)) for _ in range(n)]
            h["cloud_cover"] = [max(0, min(100, 55 + 40 * math.sin(i / 19) + random.gauss(0, 15))) for i in range(n)]
            h["cloud_cover_2m"] = [max(0, min(100, 60 * math.sin(i / 53) - 20)) for i in range(n)]
            h["visibility"] = [None] * n
            h["wind_speed_10m"] = [max(0, 14 + 10 * math.sin(i / 23) + random.gauss(0, 3)) for i in range(n)]
            h["wind_direction_10m"] = [(220 + 90 * math.sin(i / 50) + random.gauss(0, 10)) % 360 for i in range(n)]
            h["wind_gusts_10m"] = [w * 1.6 for w in h["wind_speed_10m"]]
            h["sunshine_duration"] = [None] * n
            models[k][mid] = h
        n = 24 * (7 + PAST_DAYS)
        marine[k] = {
            "time": times[:n],
            "wave_height": [max(0.1, 0.8 + 0.6 * math.sin(i / 30) + random.gauss(0, 0.05)) for i in range(n)],
            "wave_direction": [(120 + 40 * math.sin(i / 40)) % 360 for i in range(n)],
            "wave_period": [6 + 3 * math.sin(i / 45) for i in range(n)],
            "sea_surface_temperature": [12.5] * n,
            "sea_level_height_msl": [1.2 * math.cos(2 * math.pi * (i + 3) / 12.42) for i in range(n)],
        }
    return models, marine


# ---------------------------------------------------------------- the model
def f_air(rh, margin=None):
    """Air moisture. Reward for dry air as before. The penalty for humid air bites in full when the rock is
    within 2 degrees of the dew point and eases to half when it is 4 or more degrees clear, because damp air
    greases rock through condensation; the salt step at 75% follows the same scaling."""
    if rh is None:
        return None
    if rh <= 76:
        return min(4.0, (76 - rh) / 4)
    pts = max(-4.0, (76 - rh) / 5) - 1
    if margin is None:
        return pts
    scale = 1.0 if margin <= 2 else 0.5 if margin >= 4 else 1.0 - 0.25 * (margin - 2)
    return pts * scale


def f_fog(fog_frac, vis_m):
    """Haar. Fog fraction (Met Office 2 km) or visibility."""
    if fog_frac is not None and fog_frac >= 50:
        return -4
    if vis_m is not None and vis_m < 1000:
        return -4
    if fog_frac is not None and fog_frac >= 20:
        return -2
    if vis_m is not None and vis_m < 4000:
        return -2
    return 0


def f_sun(sunshine_s, cloud, az, el, aspect):
    if el < 3:
        return 0, "night"
    sunny = sunshine_s >= 1800 if sunshine_s is not None else (cloud is not None and cloud <= 40)
    if not sunny:
        return 0, "cloud"
    if aspect is not None and ang_diff(az, aspect) <= 60:
        if el >= 10:
            return 3, "on the face"
        if el >= 5:
            return 2, "low sun on the face"
    return 1, "sun"


def rock_temp(t_air, t_mean24, sst, sun_pts, cloud, wind, el, tidal=False):
    """Rock surface temperature estimate: lags the air, pulled towards the sea (hard, for walls that stand in it),
    warmed by direct sun, and radiating heat away under a clear sky when the sun is low or gone."""
    if t_air is None or t_mean24 is None:
        return None
    base = 0.4 * t_air + 0.6 * t_mean24
    if sst is not None:
        pull = 0.6 if tidal else 0.3
        base = (1 - pull) * base + pull * sst
    base += {3: 3.0, 2: 2.0, 1: 0.5}.get(sun_pts, 0.0)
    if el < 15 and (cloud is None or cloud < 50) and (wind or 0) < 15:
        base -= 1.5
    return base


def f_condensation(margin):
    """Rock temperature minus dew point."""
    if margin is None:
        return None
    if margin <= 0: return -4
    if margin <= 1: return -3
    if margin <= 2: return -2
    if margin <= 3: return -1
    if margin >= 5: return 1
    return 0


def onshore(deg, coast_faces):
    return deg is not None and ang_diff(deg, coast_faces) <= 90


def f_wind_dir(deg, kmh, coast_faces):
    """Air-mass hint from wind direction: -1 straight onshore, +1 straight offshore, 0 along the shore,
    scaled down to nothing in a calm (full effect from 15 km/h)."""
    if deg is None:
        return None
    strength = min(1.0, (kmh or 0) / 15.0)
    return -math.cos(math.radians(ang_diff(deg, coast_faces))) * strength


def in_shelter(sheltered, wind_dir, aspect, inlet=False):
    """A sheltered wall at the back of a bay feels the wind only when it blows onto the face;
    a wall in a narrow inlet is sheltered from every direction, its own walls break the wind up."""
    if not sheltered:
        return False
    if inlet or wind_dir is None or aspect is None:
        return True
    return ang_diff(wind_dir, aspect) > 60


def f_wind(kmh, is_onshore, sheltered, calm_matters=True):
    """Drying by wind at the rock. The speed is halved at sheltered crags. Onshore wind from force 4 up carries salt and spray."""
    if kmh is None:
        return None
    k = kmh * 0.5 if sheltered else kmh
    pts = (-1 if calm_matters else 0) if k < 5 else 1 if k <= 15 else 2 if k <= 35 else 1
    if is_onshore:
        pts -= 2 if kmh >= 40 else 1 if kmh >= 25 else 0
    return pts


def f_sea(h_m, wave_dir, period, aspect, inlet=False, sea_sheltered=False):
    """Sea state at the wall. Waves from behind or along the face are discounted, less so for long swell.
    In a narrow inlet the swell funnels and reflects: the height counts 1.5 times and no direction discount applies.
    A wall protected from the open sea by offshore rock counts the swell at half height."""
    if h_m is None:
        return None, None, None
    eff = h_m * 1.5 if inlet else h_m * 0.5 if sea_sheltered else h_m
    if not inlet and aspect is not None and wave_dir is not None and ang_diff(wave_dir, aspect) > 90:
        eff = h_m * (0.7 if (period or 0) >= 9 else 0.4)
    ft = eff * 3.281
    pts = -2 if ft >= 5 else -1 if ft >= 2.5 else 0 if ft >= 1 else 1
    return pts, ft, eff


def vpd_kpa(t, rh):
    es = 0.6108 * math.exp(17.27 * t / (t + 237.3))
    return es * (1 - rh / 100)


def drying_rate(vpd, wind_kmh, sun_pts):
    """Evaporation from a wet rock face, mm per hour: Dalton-type term plus direct sun."""
    sun = 0.1 if sun_pts >= 2 else 0.05 if sun_pts == 1 else 0.0
    return (0.05 + 0.01 * (wind_kmh or 0)) * max(vpd or 0, 0) + sun


def f_wet(rain_now, film):
    if rain_now is not None and rain_now >= 0.2:
        return -5, "raining"
    if film > 0.5:
        return -3, f"wet, {film:.1f} mm on the rock"
    if film > 0.1:
        return -2, f"damp, {film:.1f} mm on the rock"
    if film > 0.02:
        return -1, "drying"
    return 0, ""


def f_seep(r24, r72):
    pts = 0
    if r24 is not None:
        pts = -3 if r24 >= 10 else -2 if r24 >= 5 else 0
    if r72 is not None and r72 >= 25:
        pts -= 1
    return max(pts, -4)


def baseline_points(rh, wd, ws, sunny, az, el, aspect, tmax, ymax, sea_pts):
    """The simple additive table this project started from, kept for comparison only: humidity steps,
    fixed compass wind rule, sun within 80 degrees, day-on-day temperature change, sea state."""
    if rh is None:
        return None
    hum = -3 if rh >= 90 else -2 if rh >= 85 else 0 if rh >= 80 else 1 if rh >= 76 else 2 if rh >= 70 else 3 if rh >= 65 else 4 if rh >= 61 else 5
    wdir = (-1 if 22.5 <= (wd % 360) < 202.5 else 1) if wd is not None else 0
    wamt = (-1 if ws < 5 else 1 if ws <= 15 else 2) if ws is not None else 0
    sun = 0
    if sunny and el >= 3:
        sun = 3 if (aspect is not None and el > 5 and ang_diff(az, aspect) < 80) else 1
    temp = 0
    if tmax is not None and ymax is not None:
        temp = -3 if tmax - ymax > 5 else 1 if tmax - ymax < -5 else 0
    return hum + wdir + wamt + sun + temp + (sea_pts or 0)


def baseline_index(pts):
    """Map the baseline's roughly -10 to 13 range onto 0 to 10."""
    if pts is None:
        return None
    return max(0.0, min(10.0, 10.0 * (pts + 10) / 23.0))


def series(h, var):
    return h.get(var) or [None] * len(h.get("time", []))


def model_weight(mid, base, dt, now):
    if mid == "ukmo_seamless" and dt > now + timedelta(hours=48):
        return 1.0
    return base


# ---------------------------------------------------------------- build
def drying_note(hs):
    """When the Met Office figures expect wet rock to dry: '' if it starts the day dry."""
    first = hs[0]["d"]
    if first["film"] <= 0.1:
        return ""
    for h in hs:
        if h["d"]["film"] <= 0.1 and h["d"]["f"]["wet"] > -5:
            return f"Starts the day wet ({first['film']:.1f} mm on the rock); expected to be dry by about {h['t'][11:16]}"
    return f"Wet all day ({first['film']:.1f} mm on the rock at the start, {hs[-1]['d']['film']:.1f} mm at the end)"


def best_window(hs):
    """A day's best window: the highest mean of three consecutive hours (two at the end of the day), the first on a tie.
    hs: hour dicts with "t" and "index", in time order. Returns (mean, [hours]), or None with fewer than two hours."""
    best = None
    for i in range(len(hs)):
        win = hs[i:i + 3]
        if len(win) < 2:
            continue
        s = sum(x["index"] for x in win) / len(win)
        if best is None or s > best[0]:
            best = (s, win)
    return best


def hour_of(hr):
    return int(hr["t"][11:13])


def end_of(hr):
    return (datetime.fromisoformat(hr["t"]) + timedelta(hours=1)).strftime("%H:%M")


def usable_from(hs):
    """The first hour from which the score, as shown, stays climbable for at least two consecutive hours; None if none."""
    for a, b in zip(hs, hs[1:]):
        if rnd(a["index"]) >= USABLE and rnd(b["index"]) >= USABLE and hour_of(b) == hour_of(a) + 1:
            return a
    return None


def plain_line(hs, now_hour=None, tomorrow=False):
    """The plain-words line beside a wall's strip on its crag page, for one wall's daylight hours of the day shown (earlier hours included),
    one short sentence per point: "Grippy now. Best 16:00 to 18:00."
    Today: the band this hour, when it becomes climbable and the best window still to come. A later day (tomorrow=True): the whole day;
    the heading above the strip names the day."""
    rest = hs if tomorrow else [x for x in hs if hour_of(x) >= now_hour]
    if not rest:
        return "No daylight hours left today." if not tomorrow else "No hours scored."
    start = usable_from(rest)
    if tomorrow:
        parts = [f"climbable from {start['t'][11:16]}" if start else "not climbable"]
    else:
        cur = rest[0] if hour_of(rest[0]) == now_hour else None
        parts = [f"{band(cur['index'])[0]} now"] if cur else []
        if not (cur and rnd(cur["index"]) >= USABLE):
            parts.append(f"climbable from {start['t'][11:16]}" if start else "not climbable today")
    bw = best_window(rest)
    if bw:
        parts.append(f"best {bw[1][0]['t'][11:16]} to {end_of(bw[1][-1])}")
    return " ".join(x[0].upper() + x[1:] + "." for x in parts)


def day_hours(r, day_iso):
    """One wall's scored daylight hours on a date, including today's earlier hours."""
    return [hr for hr in r.get("earlier", []) + r["hours"] if hr["t"][:10] == day_iso]


def coast_day(results, now):
    """The day the Coast panel and the crag search show: today until its daylight is over, then tomorrow."""
    today = now.date()
    if any(hr["t"][:10] == today.isoformat() for r in results for hr in r["hours"]):
        return today, False
    return today + timedelta(days=1), True


def coast_rows(results, zones, day_iso):
    """One row per weather point, in coast order: (zone key, name, {hour: median blended index across its walls})."""
    order, by_zone = [], {}
    for r in results:
        z = r["crag"]["zone"]
        if z not in by_zone:
            order.append(z)
            by_zone[z] = {}
        for hr in day_hours(r, day_iso):
            by_zone[z].setdefault(hour_of(hr), []).append(hr["index"])
    return [(z, zones[z]["name"], {h: statistics.median(v) for h, v in sorted(by_zone[z].items())}) for z in order]


def score_crag(zones, crag, models, marine, now, since=None, trace=None):
    """Hourly Grip for one wall: each model scored separately, then blended. Hours before since (default now) are skipped.
    trace: an optional dict that receives the first model's water film for every hour, for the crag page; it does not affect the score."""
    cutoff = now if since is None else since
    z = zones[crag["zone"]]
    asp = COMPASS.get(crag.get("aspect") or "", None)
    coast = z.get("coast_faces", 112.5)
    sheltered = bool(crag.get("sheltered"))
    inlet = bool(crag.get("inlet"))
    zm = models.get(crag["zone"], {})
    mar = marine.get(crag["zone"], {})
    mar_idx = {t: i for i, t in enumerate(mar.get("time", []))}

    def marine_at(t, var):
        mi = mar_idx.get(t)
        s = mar.get(var)
        return s[mi] if mi is not None and s else None

    per_model = {}
    for mid, label, _d, weight in MODELS:
        h = zm.get(mid)
        if not h or not h.get("time"):
            continue
        times = h["time"]
        T, RH, TD, VP = (series(h, v) for v in ("temperature_2m", "relative_humidity_2m", "dew_point_2m", "vapour_pressure_deficit"))
        PR, CC, FG, VIS = (series(h, v) for v in ("precipitation", "cloud_cover", "cloud_cover_2m", "visibility"))
        WS, WD, SS = (series(h, v) for v in ("wind_speed_10m", "wind_direction_10m", "sunshine_duration"))

        dmax = {}
        for t, v in zip(times, T):
            if v is not None:
                dmax[t[:10]] = max(dmax.get(t[:10], -99), v)

        # pass 1: sun, sea and the water film on the rock, for every hour including the past
        suns, seas, films = [], [], []
        film = 0.0
        for i, t in enumerate(times):
            dt = datetime.fromisoformat(t).replace(tzinfo=TZ)
            az, el = sun_position(dt.astimezone(timezone.utc), z["lat"], z["lon"])
            sun_pts, sun_note = f_sun(SS[i], CC[i], az, el, asp)
            suns.append((sun_pts, sun_note, az, el))
            sea = f_sea(marine_at(t, "wave_height"), marine_at(t, "wave_direction"), marine_at(t, "wave_period"), asp, bool(crag.get("inlet")), bool(crag.get("sea_sheltered")))
            seas.append(sea)
            vpd = VP[i]
            if vpd is None and T[i] is not None and RH[i] is not None:
                vpd = vpd_kpa(T[i], RH[i])
            film += PR[i] or 0
            fog_pts = f_fog(FG[i], VIS[i])
            if fog_pts <= -4:
                film += 0.1  # thick haar wets the rock much as drizzle does
            elif fog_pts <= -2:
                film += 0.05
            if RH[i] is not None and RH[i] >= 85 and film < 0.15:
                film += 0.02  # salt on the rock drawing in water: a thin brine film, never more than damp
            if sea[2] is not None and sea[2] >= (2.0 if crag.get("tidal") else 2.5):
                film += 0.05  # spray: a big sea wets the rock a little, more readily at tidal walls
            film = min(2.0, film)
            film = max(0.0, film - drying_rate(vpd, WS[i] or 0, sun_pts))
            films.append(film)
        if trace is not None and "film" not in trace:
            trace["film"], trace["model"] = dict(zip(times, films)), label

        # pass 2: score the daylight hours still to come
        rows = {}
        for i, t in enumerate(times):
            dt = datetime.fromisoformat(t).replace(tzinfo=TZ)
            if dt + timedelta(hours=1) <= cutoff:
                continue
            sun_pts, sun_note, az, el = suns[i]
            if el < 5 or (RH[i] is None and WS[i] is None):
                continue
            past = [v for v in T[max(0, i - 24):i] if v is not None]
            tmean = sum(past) / len(past) if len(past) >= 12 else None
            rock = rock_temp(T[i], tmean, marine_at(t, "sea_surface_temperature"), sun_pts, CC[i], WS[i], el, bool(crag.get("tidal")))
            margin = (rock - TD[i]) if rock is not None and TD[i] is not None else None
            r24 = sum(v for v in PR[max(0, i - 24):i] if v is not None) if i >= 24 else None
            r72 = sum(v for v in PR[max(0, i - 72):i] if v is not None) if i >= 72 else None
            is_on = onshore(WD[i], coast)
            f = {
                "air": f_air(RH[i], margin),
                "fog": f_fog(FG[i], VIS[i]),
                "dew": f_condensation(margin),
                "wdir": f_wind_dir(WD[i], WS[i], coast),
                "wind": f_wind(WS[i], is_on, in_shelter(sheltered, WD[i], asp, inlet), calm_matters=(RH[i] is None or RH[i] >= 80 or (margin is not None and margin < 3))),
                "sun": sun_pts,
                "sea": seas[i][0],
            }
            f["wet"], wnote = f_wet(PR[i], films[i])
            # dry-rock credit: full in humid air (76%+), fading to nothing at 60%, where the air reward already says the rock is dry
            dry_ok = films[i] <= 0.02 and (PR[i] or 0) < 0.2 and f_fog(FG[i], VIS[i]) == 0 and margin is not None and margin >= 3
            f["dry"] = 2.0 * min(1.0, max(0.0, ((RH[i] or 0) - 60) / 16)) if dry_ok else 0.0
            if films[i] > 0.1:  # wind and sun are already working through the film; count them at half weight on wet rock
                if f["wind"] is not None and f["wind"] > 0:
                    f["wind"] = f["wind"] / 2
                f["sun"] = f["sun"] / 2
            f["seep"] = f_seep(r24, r72)
            pts = sum(v for v in f.values() if v is not None)
            wet = (PR[i] or 0) >= 0.2 or films[i] > 0.1 or f["fog"] <= -2
            yd = (dt.date() - timedelta(days=1)).isoformat()
            base = baseline_index(baseline_points(RH[i], WD[i], WS[i], sun_pts > 0, az, el, asp,
                                                  dmax.get(dt.date().isoformat()), dmax.get(yd), seas[i][0]))
            rows[t] = {
                "pts": pts, "index": to_index(pts), "base": base, "f": f, "wet": wet, "margin": margin, "rock": rock,
                "rh": RH[i], "ws": WS[i], "wd": WD[i], "sun": sun_note, "ft": seas[i][1], "film": films[i],
                "note": wnote, "fog": FG[i], "vis": VIS[i], "w": model_weight(mid, weight, dt, now),
            }
        per_model[mid] = rows

    # blend
    all_times = sorted({t for rows in per_model.values() for t in rows})
    hours = []
    for t in all_times:
        vals, bases, wsum, weighted, bweighted, nwet, detail = [], [], 0.0, 0.0, 0.0, 0, None
        for mid, mlabel, _d, _w in MODELS:
            r = per_model.get(mid, {}).get(t)
            if r is None:
                continue
            vals.append((mlabel, r["index"]))
            bases.append((mlabel, r["base"]))
            weighted += r["index"] * r["w"]
            bweighted += (r["base"] or 0) * r["w"]
            wsum += r["w"]
            nwet += 1 if r["wet"] else 0
            if detail is None:
                detail = r
        if not vals:
            continue
        hours.append({"t": t, "index": weighted / wsum, "spread": max(v for _l, v in vals) - min(v for _l, v in vals),
                      "n": len(vals), "wet": nwet / len(vals), "models": vals, "d": detail,
                      "base": bweighted / wsum, "base_models": bases})

    return hours


def build(cfg, models, marine):
    zones = cfg["zones"]
    now = datetime.now(TZ)
    today = now.date()
    results = []
    tides = {}

    for zk, m in marine.items():
        tides[zk] = {}
        sl = m.get("sea_level_height_msl")
        t = m.get("time")
        if not sl or not t or all(v is None for v in sl):
            continue
        for i in range(1, len(sl) - 1):
            a, b, c = sl[i - 1], sl[i], sl[i + 1]
            if None in (a, b, c) or not (b <= a and b < c):
                continue
            den = a - 2 * b + c
            off = 0.5 * (a - c) / den if den else 0
            tt = datetime.fromisoformat(t[i]) + timedelta(hours=off)
            tides[zk].setdefault(tt.date().isoformat(), []).append(tt.strftime("%H:%M"))

    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for crag in cfg["crags"]:
        # today's earlier hours are scored too, for the Coast panel only; everything else starts at the current hour
        trace = {}
        scored = score_crag(zones, crag, models, marine, now, since=day0, trace=trace)
        hours = [hr for hr in scored if datetime.fromisoformat(hr["t"]).replace(tzinfo=TZ) + timedelta(hours=1) > now]
        earlier = scored[:len(scored) - len(hours)]
        days = {}
        for hr in hours:
            days.setdefault(hr["t"][:10], []).append(hr)
        daily = {}
        for d, hs in days.items():
            best = best_window(hs)
            if best:
                win = best[1]
                pm = {}
                for x in win:
                    for lab, sc in x["models"]:
                        pm.setdefault(lab, []).append(sc)
                daily[d] = {
                    "index": best[0], "start": win[0]["t"][11:16],
                    "end": (datetime.fromisoformat(win[-1]["t"]) + timedelta(hours=1)).strftime("%H:%M"),
                    "spread": max(x["spread"] for x in win), "n": min(x["n"] for x in win),
                    "wet": sum(x["wet"] for x in win) / len(win),
                    "usable": sum(1 for x in hs if rnd(x["index"]) >= USABLE), "hours": len(hs),  # as shown, so it agrees with the hour blocks
                    "drying": drying_note(hs),
                    "models": [(lab, sum(v) / len(v)) for lab, v in pm.items()],
                }
        film = trace.get("film", {}).get(now.strftime("%Y-%m-%dT%H:00"))
        results.append({"crag": crag, "hours": hours, "earlier": earlier, "daily": daily,
                        "film_now": (trace["model"], film) if film is not None else None})
    return results, tides, now


# ---------------------------------------------------------------- calibration against logged days
def fetch_log():
    """Logged days from the published response sheet. Returns a list of dicts, or [] on any failure."""
    import csv
    import io
    try:
        req = urllib.request.Request(LOG_CSV_URL, headers={"User-Agent": "grip-forecast/2.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8-sig")
    except Exception as e:  # noqa: BLE001
        log(f"Log sheet not available: {e}")
        return []
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return []
    head = [h.strip().lower() for h in rows[0]]

    def col(prefix):
        for i, h in enumerate(head):
            if h.startswith(prefix):
                return i
        return None

    ic, idate, ifrom, ito, ifeel, iprob, iwall = (col(x) for x in ("crag", "date", "on the rock from", "on the rock until", "how did", "if it was poor", "wall or sector"))
    out = []
    for r in rows[1:]:
        try:
            crag = r[ic].strip()
            d = parse_date(r[idate])
            t1, t2 = parse_time(r[ifrom]), parse_time(r[ito])
            feel = parse_feel(r[ifeel])
            if not crag or d is None or t1 is None or t2 is None or feel is None:
                continue
            if t2 <= t1:
                t2 = t1 + 1
            wall = r[iwall].strip() if iwall is not None and iwall < len(r) else ""
            out.append({"crag": crag, "wall": wall, "date": d.isoformat(), "from": t1, "to": t2, "feel": feel,
                        "problems": r[iprob].strip() if iprob is not None and iprob < len(r) else ""})
        except Exception:  # noqa: BLE001
            continue
    return out


def parse_feel(x):
    """The internal band key for a logged feel option, old or new wording ("Usable: ..." and "Climbable: ..." both give "Usable"); None if unknown."""
    name = (x or "").split(":")[0].strip()
    name = FEEL_ALIASES.get(name, name)
    return name if name in FEEL else None


def parse_date(x):
    x = x.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(x, fmt).date()
        except ValueError:
            pass
    return None


def parse_time(x):
    x = x.strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
        try:
            return datetime.strptime(x, fmt).hour
        except ValueError:
            pass
    return None


def fetch_reanalysis(zone, start, end):
    """ERA5 reanalysis for one zone and date window, shaped like a model's hourly data. None if unavailable."""
    z = list(zone.values())[0]
    hourly = [v for v in HOURLY_FULL if v not in ("cloud_cover_2m", "visibility")]
    log(f"Fetching reanalysis ({start} to {end})")
    try:
        data = get_json(REANALYSIS_URL, {"latitude": z["lat"], "longitude": z["lon"], "hourly": ",".join(hourly),
                                          "start_date": start, "end_date": end, "timezone": "Europe/London",
                                          "wind_speed_unit": "kmh"})
    except Exception as e:  # noqa: BLE001
        log(f"  reanalysis failed: {e}")
        return None
    h = data.get("hourly", {})
    rh = h.get("relative_humidity_2m") or []
    if not any(v is not None for v in rh[-24:]):
        return None  # the last day is not in the archive yet
    return h


def window_mean(hours, entry, key):
    win = [h for h in hours if entry["from"] <= int(h["t"][11:13]) < entry["to"] and h.get(key) is not None]
    return sum(h[key] for h in win) / len(win) if win else None


LOG_PINS = {  # logs made before the form had a wall box, pinned to the wall the logger later confirmed
    ("Craig Stirling", "2026-09-26"): "Craig Stirling (East Buttress)",
    ("Craig Stirling", "2026-10-01"): "Craig Stirling (East Buttress)",
}


def resolve_wall(cfg, entry, crags):
    """Match a logged crag (and optional wall text) to a wall in the crag list. Old names are mapped; a wall
    typed by hand is matched loosely within its crag; a bare crag name means its first listed wall."""
    pin = LOG_PINS.get((entry["crag"], entry["date"]))
    if pin and pin in crags:
        return crags[pin]
    name = LABEL_ALIASES.get(entry["crag"], entry["crag"])
    wall = (entry.get("wall") or "").strip().lower()
    if wall:
        mine = [c for c in cfg["crags"] if c["name"] == name]
        for c in mine:
            if (c.get("wall") or "").lower() == wall:
                return c
        words = set(re.findall(r"[a-z0-9]+", wall)) - {"the", "wall", "of", "and"}
        best = max(mine, key=lambda c: len(words & set(re.findall(r"[a-z0-9]+", (c.get("wall") or "").lower()))), default=None)
        if best and words & set(re.findall(r"[a-z0-9]+", (best.get("wall") or "").lower())):
            return best
    return crags.get(name)


def backscore(cfg, entry):
    """Grip for a logged window, scored from the archived forecasts for that date. None if it cannot be done."""
    crags = {label(c): c for c in cfg["crags"]}
    for c in cfg["crags"]:  # a bare crag name in the log means its first listed wall
        crags.setdefault(c["name"], c)
    crag = resolve_wall(cfg, entry, crags)
    if crag is None:
        return None
    d = date.fromisoformat(entry["date"])
    zone = {crag["zone"]: cfg["zones"][crag["zone"]]}
    start = (d - timedelta(days=PAST_DAYS)).isoformat()
    models = fetch_models(zone, start, d.isoformat())
    if not any(models[crag["zone"]].values()):
        return None
    marine = fetch_marine(zone, start, d.isoformat())
    day_start = datetime(d.year, d.month, d.day, tzinfo=TZ)
    hours = score_crag(cfg["zones"], crag, models, marine, day_start)
    win = [h for h in hours if entry["from"] <= int(h["t"][11:13]) < entry["to"]]
    if not win:
        return None
    per, bper = {}, {}
    for h in win:
        for lab, sc in h["models"]:
            per.setdefault(lab, []).append(sc)
        for lab, sc in h["base_models"]:
            if sc is not None:
                bper.setdefault(lab, []).append(sc)
    res = {"index": sum(h["index"] for h in win) / len(win), "wet": sum(h["wet"] for h in win) / len(win),
           "models": {lab: sum(v) / len(v) for lab, v in per.items()},
           "base": sum(h["base"] for h in win) / len(win),
           "base_models": {lab: sum(v) / len(v) for lab, v in bper.items()},
           "era": None, "era_base": None}
    era = fetch_reanalysis(zone, start, d.isoformat())
    if era:
        eh = score_crag(cfg["zones"], crag, {crag["zone"]: {MODELS[0][0]: era}}, marine, day_start)
        res["era"] = window_mean(eh, entry, "index")
        res["era_base"] = window_mean(eh, entry, "base")
    return res


def band_miss(x, feel):
    """How far a Grip index falls outside the felt band: 0 inside, negative below, positive above."""
    lo, hi = FEEL_RANGE[feel]
    if x < lo:
        return x - lo
    if x >= hi:
        return x - (hi - 1)
    return 0.0


def write_calibration_csv(cache):
    """Flat table of every scored day, for importing into a spreadsheet."""
    import csv
    labs = [lab for _m, lab, _d, _w in MODELS]
    rows = sorted((v for v in cache.values() if v.get("grip") is not None), key=lambda v: (v["date"], v["crag"]))
    with open(CAL_CSV, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["date", "crag", "from", "to", "felt", "felt_low", "felt_high", "grip", "grip_miss"]
                    + [f"grip_{lab.lower().replace(' ', '_')}" for lab in labs]
                    + ["grip_actual_weather", "grip_actual_weather_miss"]
                    + ["baseline", "baseline_miss"] + [f"baseline_{lab.lower().replace(' ', '_')}" for lab in labs]
                    + ["baseline_actual_weather", "wet_risk", "problems"])
        for v in rows:
            lo, hi = FEEL_RANGE[v["feel"]]
            r2 = lambda x: "" if x is None else f"{x:.1f}"  # noqa: E731
            wr.writerow([v["date"], v["crag"], f'{v["from"]:02d}:00', f'{v["to"]:02d}:00', FEEL_NAME[v["feel"]], lo, min(hi - 1, 10),
                         r2(v["grip"]), r2(band_miss(v["grip"], v["feel"]))]
                        + [r2(v.get("models", {}).get(lab)) for lab in labs]
                        + [r2(v.get("era")), r2(band_miss(v["era"], v["feel"]) if v.get("era") is not None else None)]
                        + [r2(v.get("base")), r2(band_miss(v["base"], v["feel"]) if v.get("base") is not None else None)]
                        + [r2(v.get("base_models", {}).get(lab)) for lab in labs]
                        + [r2(v.get("era_base")), r2(v.get("wet")), v.get("problems", "")])


def merge_days(rows):
    """Several logs of the same crag on the same day become one data point: scores averaged, felt band by majority."""
    groups = {}
    for v in rows:
        groups.setdefault((v["crag"], v["date"]), []).append(v)
    out = []
    for (crag, d), vs in groups.items():
        if len(vs) == 1:
            out.append({**vs[0], "n_logs": 1})
            continue
        feels = [v["feel"] for v in vs]
        feel = max(sorted(set(feels), key=lambda f: FEEL[f]), key=feels.count)

        def avg(get):
            xs = [get(v) for v in vs if get(v) is not None]
            return sum(xs) / len(xs) if xs else None

        labs = {lab for v in vs for lab in v.get("models", {})}
        out.append({**vs[0], "feel": feel, "n_logs": len(vs),
                    "from": min(v["from"] for v in vs), "to": max(v["to"] for v in vs),
                    "grip": avg(lambda v: v.get("grip")), "wet": avg(lambda v: v.get("wet")),
                    "models": {lab: avg(lambda v, lab=lab: v.get("models", {}).get(lab)) for lab in labs},
                    "base": avg(lambda v: v.get("base")), "era": avg(lambda v: v.get("era")), "era_base": avg(lambda v: v.get("era_base")),
                    "base_models": {lab: avg(lambda v, lab=lab: v.get("base_models", {}).get(lab)) for lab in labs}})
    return out


def calibrate(cfg, limit=5):
    """Score every logged day once, cache the result, and summarise how Grip compares with how it felt."""
    if os.environ.get("GRIP_FAKE"):
        return None
    try:
        with open(CAL_FILE) as f:
            cache = json.load(f)
    except Exception:  # noqa: BLE001
        cache = {}
    entries = fetch_log()
    done = 0
    for e in entries:
        key = f'{MODEL_VERSION}|{e["crag"]}|{e["date"]}|{e["from"]}|{e["to"]}|{e["feel"]}'
        age = (datetime.now(TZ).date() - date.fromisoformat(e["date"])).days
        c = cache.get(key)
        if c and (c.get("era") is not None or (c.get("grip") is None and c.get("tries", 1) >= 3)):
            continue  # fully scored, or three tries without success; a day whose reanalysis was not out yet is tried again
        if done >= limit:
            continue
        if age < 1:
            continue  # score it once the day is over
        done += 1
        try:
            res = backscore(cfg, e)
        except Exception as ex:  # noqa: BLE001
            log(f"Back-scoring failed for {key}: {ex}")
            res = None
        cache[key] = {**e, "grip": res["index"] if res else None, "wet": res["wet"] if res else None,
                      "models": res["models"] if res else {}, "base": res["base"] if res else None,
                      "base_models": res["base_models"] if res else {},
                      "era": res["era"] if res else None, "era_base": res["era_base"] if res else None,
                      "tries": 1 if res else (c.get("tries", 1) + 1 if c else 1)}
    cache = {k: v for k, v in cache.items() if k.startswith(MODEL_VERSION + "|")}
    if done:
        with open(CAL_FILE, "w") as f:
            json.dump(cache, f, indent=1, sort_keys=True)
            f.write("\n")
    write_calibration_csv(cache)
    scored = merge_days([v for v in cache.values() if v.get("grip") is not None])
    pending = [e for e in entries if f'{MODEL_VERSION}|{e["crag"]}|{e["date"]}|{e["from"]}|{e["to"]}|{e["feel"]}' not in cache]
    if not scored:
        return {"n": 0, "pending": len(pending), "rows": []}
    errs = [band_miss(v["grip"], v["feel"]) for v in scored]  # unrounded: typical miss and average error
    shown = [band_miss(rnd(v["grip"]), v["feel"]) for v in scored]  # as displayed: in band and within a point
    bands_right = sum(1 for e in shown if e == 0)
    within = sum(1 for e in shown if abs(e) <= 1)
    by_model = {}
    for lab, getter in [(lab, (lambda v, lab=lab: v.get("models", {}).get(lab))) for _m, lab, _d, _w in MODELS] + [("Actual weather", lambda v: v.get("era"))]:
        ms = [band_miss(getter(v), v["feel"]) for v in scored if getter(v) is not None]
        if ms:
            by_model[lab] = {"n": len(ms), "right": sum(1 for v in scored if getter(v) is not None and band_miss(rnd(getter(v)), v["feel"]) == 0), "bias": sum(ms) / len(ms), "mae": sum(abs(x) for x in ms) / len(ms)}
    rows = sorted(scored, key=lambda v: v["date"], reverse=True)
    return {"n": len(scored), "pending": len(pending), "bias": sum(errs) / len(errs),
            "mae": sum(abs(e) for e in errs) / len(errs), "bands_right": bands_right, "within": within,
            "by_model": by_model, "rows": rows}


# ---------------------------------------------------------------- page
# The design tokens are grip-tokens.css from the Claude Design redesign (Appendix B), light and dark, with its comments left out.
# The five band colours are data: nothing but score blocks, key chips and the log form's feel tiles may use them.
# The brand pink and teal are defined for completeness but belong to the logo image only; nothing here uses them.
TOKENS_CSS = """
:root{color-scheme:light dark;
--paper:#eef1f2;--card:#f8fafa;--sunk:#e4e9eb;--ink:#1d2b34;--muted:#5b6b75;--rule:#c9d1d5;--past:#dbe1e4;--past-ink:#4f5e67;
--inv-bg:var(--ink);--inv-fg:var(--paper);--scrim:rgb(20 29 35 / .5);
--shadow-overlay:0 2px 4px rgb(29 43 52 / .08),0 12px 32px rgb(29 43 52 / .16);
--soaked:#b3261e;--on-soaked:#ffffff;--greasy:#ee8a3a;--on-greasy:#1d2b34;--climbable:#f2cd4f;--on-climbable:#1d2b34;
--grippy:#8fc66b;--on-grippy:#1d2b34;--prime:#2e8b3e;--on-prime:#ffffff;
--stripe-on-dark-text:repeating-linear-gradient(135deg,rgb(255 255 255 / .45) 0 4px,transparent 4px 10px);
--stripe-on-light-text:repeating-linear-gradient(135deg,rgb(0 0 0 / .22) 0 4px,transparent 4px 10px);
--brand-thrift:#c2457e;--brand-sea:#2a9d8f;
--font-body:"Barlow",system-ui,sans-serif;--font-display:"Barlow Condensed","Barlow",sans-serif;
--t-micro:0.75rem;--t-small:0.8125rem;--t-meta:0.875rem;--t-body:1rem;--t-lead:1.0625rem;--t-h3:1.25rem;--t-h2:1.5rem;--t-wall:1.75rem;--t-h1:2.25rem;
--lh-tight:1.1;--lh-body:1.45;--overline-tracking:0.06em;
--score-xl:56px;--score-xl-num:2.125rem;--score-l:44px;--score-l-num:1.3125rem;--score-m:36px;--score-m-num:1.1875rem;
--score-s:28px;--score-s-num:1rem;--score-xs:24px;--score-xs-num:0.875rem;
--s-2:2px;--s-3:3px;--s-4:4px;--s-6:6px;--s-8:8px;--s-12:12px;--s-16:16px;--s-20:20px;--s-24:24px;--s-32:32px;--s-48:48px;
--page-pad:16px;--page-max:1200px;
--r-xs:4px;--r-s:6px;--r-m:8px;--r-l:10px;--r-xl:16px;--r-pill:999px;
--bw:1px;--bw-strong:2px;
--focus-ring:0 0 0 2px var(--paper),0 0 0 4px var(--ink);
--now-ring:0 0 0 2px var(--card),0 0 0 4px var(--ink);
--tap:44px}
@media (prefers-color-scheme:dark){:root{
--paper:#141d23;--card:#1b262d;--sunk:#10181d;--ink:#e3e8ea;--muted:#93a3ad;--rule:#2c3a43;--past:#26333c;--past-ink:#9aa9b2;
--scrim:rgb(0 0 0 / .6);--shadow-overlay:0 12px 40px rgb(0 0 0 / .55);--brand-thrift:#ec8bb6;--brand-sea:#7dd3c4}}
"""

CSS = TOKENS_CSS + """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:400 var(--t-body)/var(--lh-body) var(--font-body)}
main{max-width:var(--page-max);margin:0 auto;padding:var(--s-24) var(--page-pad) var(--s-48)}
h1{font:600 var(--t-h1)/var(--lh-tight) var(--font-display);margin:0 0 var(--s-8)}
h2{font:600 var(--t-h2)/var(--lh-tight) var(--font-display);margin:var(--s-32) 0 var(--s-8)}
h3{font:600 var(--t-h3)/var(--lh-tight) var(--font-display);margin:var(--s-24) 0 var(--s-8)}
b,strong{font-weight:600}
.updated{color:var(--muted);font-size:var(--t-meta);margin:0 0 var(--s-24);max-width:72ch}
.hint{color:var(--muted);font-size:var(--t-meta);margin:calc(-1 * var(--s-4)) 0 var(--s-12);max-width:72ch}
.sub{color:var(--muted);font-size:var(--t-meta)}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
a{color:inherit;text-decoration-thickness:1px;text-underline-offset:3px}
:focus-visible{outline:2px solid transparent;outline-offset:2px;box-shadow:var(--focus-ring)}
a:focus-visible{border-radius:2px}
@media (hover:hover){a:hover{text-decoration-thickness:2px}}
.b1{background-color:var(--soaked);color:var(--on-soaked)}.b2{background-color:var(--greasy);color:var(--on-greasy)}
.b3{background-color:var(--climbable);color:var(--on-climbable)}.b4{background-color:var(--grippy);color:var(--on-grippy)}
.b5{background-color:var(--prime);color:var(--on-prime)}
.unsure.b2,.unsure.b3,.unsure.b4{background-image:var(--stripe-on-dark-text)}
.unsure.b1,.unsure.b5{background-image:var(--stripe-on-light-text)}
.risk{position:relative}
.risk::after{content:"";position:absolute;top:4px;right:4px;width:6px;height:6px;border-radius:50%;background:currentColor}
.num,.chip{display:inline-flex;align-items:center;justify-content:center;vertical-align:middle;flex:none;font-family:var(--font-display);font-weight:600;line-height:1;font-variant-numeric:tabular-nums;white-space:nowrap}
.sz-xl{width:var(--score-xl);height:var(--score-xl);font-size:var(--score-xl-num);border-radius:var(--r-m)}
.sz-xl.risk::after{top:5px;right:5px;width:8px;height:8px}
.sz-l{width:var(--score-l);height:var(--score-l);font-size:var(--score-l-num);border-radius:var(--r-s)}
.sz-m{width:var(--score-m);height:var(--score-m);font-size:var(--score-m-num);border-radius:var(--r-s)}
.sz-s,.chip{width:var(--score-s);height:var(--score-s);font-size:var(--score-s-num);border-radius:var(--r-xs)}
.sz-xs{width:var(--score-xs);height:var(--score-xs);font-size:var(--score-xs-num);border-radius:var(--r-xs)}
.kc{display:inline-flex;align-items:center;justify-content:center;flex:none;min-width:34px;height:22px;padding:0 var(--s-4);border-radius:var(--r-xs);font:600 var(--t-small)/1 var(--font-display);font-style:normal;white-space:nowrap}
.wrap{position:relative;overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--rule);border-radius:var(--r-l);background:var(--card)}
.method .wrap:has(>.cal),.wrap:has(>.diff){width:fit-content;max-width:100%}
table{border-collapse:collapse;width:100%}
.scale{display:flex;flex-wrap:wrap;gap:var(--s-6) 14px;margin:14px 0 var(--s-24);font-size:var(--t-small);line-height:1.2;color:var(--ink);max-width:52rem}
.scale div{display:inline-flex;align-items:center;gap:var(--s-6)}
.gridbox{position:relative}
.gridbox::after{content:"";position:absolute;top:1px;right:1px;bottom:1px;width:28px;border-radius:0 var(--r-l) var(--r-l) 0;background:linear-gradient(to right,transparent,var(--card));pointer-events:none;transition:opacity .12s}
.gridbox.end::after{opacity:0}
.grid{font-variant-numeric:tabular-nums;border-collapse:separate;border-spacing:0;min-width:460px}
.grid th,.grid td{padding:0;text-align:center;white-space:nowrap}
.grid td{padding:var(--s-2) 1px}
.grid tbody tr:not(.zone)>*{border-top:1px solid var(--rule)}
.grid thead th{padding:var(--s-8) 1px;min-width:46px;font:600 var(--t-meta)/1.1 var(--font-display);color:var(--muted);border-bottom:1px solid var(--rule)}
.grid thead th span{display:block}.grid thead th span+span{font-weight:500}
.grid thead th.today{color:var(--ink)}
.grid th.crag{position:sticky;left:0;z-index:2;background:var(--card);text-align:left;padding:3px 10px;width:260px;min-width:260px;max-width:260px;white-space:normal;line-height:1.2;box-shadow:1px 0 0 var(--rule)}
.grid thead th.crag{padding:var(--s-8) 10px;font:600 var(--t-small)/1 var(--font-display);letter-spacing:var(--overline-tracking);text-transform:uppercase;color:var(--muted)}
.grid th.crag a{display:block;font-size:15px;font-weight:600;line-height:1.15;text-decoration:none}
@media (hover:hover){.grid th.crag a:hover{text-decoration:underline}}
.grid th.crag a:focus-visible{text-decoration:underline}
.grid th.crag small{display:block;font-weight:400;font-size:var(--t-micro);color:var(--muted)}
@media (max-width:599px){.grid th.crag{width:132px;min-width:132px;max-width:132px}}
.grid tr.zone th{text-align:left;padding:14px 0 var(--s-6);background:var(--card)}
.grid tr.zone th span{position:sticky;left:10px;display:inline-block;margin-left:10px;font:600 15px/1.2 var(--font-display);text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.grid tbody tr:last-child td{padding-bottom:var(--s-6)}
.grid td button,.grid td div{display:flex;align-items:center;justify-content:center;width:var(--score-l);height:var(--score-l);margin:0 auto;border-radius:var(--r-s);position:relative;font:600 var(--score-l-num)/1 var(--font-display)}
.grid td button{border:0;padding:0;cursor:pointer;-webkit-tap-highlight-color:transparent}
.grid td div.none{color:var(--muted);font-weight:500}
.grid td .risk::after{width:7px;height:7px}
.grid td button:focus-visible,.grid td button.sel{z-index:1}
.grid td button.sel{box-shadow:var(--now-ring)}
@media (hover:hover){.grid td button:hover{z-index:1;box-shadow:0 0 0 2px var(--card),0 0 0 4px color-mix(in srgb,var(--ink) 50%,transparent)}
.grid td button.sel:hover{box-shadow:var(--now-ring)}.grid td button:focus-visible{box-shadow:var(--focus-ring)}}
.key{display:flex;flex-wrap:wrap;gap:var(--s-6) 14px;margin:var(--s-12) 0 0;font-size:var(--t-small);color:var(--muted)}
.key span{display:inline-flex;align-items:center;gap:var(--s-6)}
.smp{display:inline-block;position:relative;flex:none;width:22px;height:22px;border-radius:var(--r-xs);background-color:var(--sunk);box-shadow:inset 0 0 0 1px var(--rule);color:var(--ink)}
.smp.unsure{background-image:repeating-linear-gradient(135deg,var(--muted) 0 2px,transparent 2px 6px)}
.smp.risk::after{top:3px;right:3px}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:var(--tap);padding:var(--s-8) var(--s-16);border:0;border-radius:var(--r-m);background:var(--inv-bg);color:var(--inv-fg);font:600 var(--t-body)/1.2 var(--font-body);text-decoration:none;text-align:center;cursor:pointer;margin-right:10px}
.btn.alt{background:var(--card);color:var(--ink);font-weight:500;box-shadow:inset 0 0 0 1px var(--rule)}
.btn.alt:focus-visible{box-shadow:inset 0 0 0 1px var(--rule),var(--focus-ring)}
.btn:active{transform:translateY(1px)}
@media (hover:hover){.btn:hover{opacity:.9}.btn.alt:hover{opacity:1;background:var(--sunk)}}
.cal{width:auto;font-size:var(--t-meta);font-variant-numeric:tabular-nums}
.cal td,.cal th{padding:var(--s-6) var(--s-12);border-bottom:1px solid var(--rule);text-align:left;vertical-align:middle}
.cal th{font:600 var(--t-meta)/1.2 var(--font-body)}
.cal tr:first-child th{font:600 var(--t-micro)/1.1 var(--font-display);letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
.method{color:var(--muted);font-size:var(--t-meta)}
.method>*{max-width:72ch}
.method>table.factors{max-width:none;width:100%}
.method p{margin:0 0 var(--s-12)}
.method table{width:auto;font-size:var(--t-small);margin:var(--s-8) 0 var(--s-16)}
.method td,.method th{border:1px solid var(--rule);padding:var(--s-6) var(--s-8);text-align:left;vertical-align:top}
.method th{color:var(--ink)}
.method .wrap table{margin:0}
.method h3{font:600 var(--t-h3) var(--font-display);margin:var(--s-24) 0 var(--s-8);color:var(--ink)}
.method li{margin:0 0 var(--s-4)}
dialog{border:1px solid var(--rule);border-radius:12px;background:var(--card);color:var(--ink);width:min(480px,calc(100vw - 32px));max-width:none;max-height:85vh;overflow:auto;padding:var(--s-20) var(--s-20) var(--s-16);box-shadow:var(--shadow-overlay)}
dialog[open]{animation:grip-fade .12s ease-out}
dialog::backdrop{background:var(--scrim)}
@keyframes grip-fade{from{opacity:0}to{opacity:1}}
@media (prefers-reduced-motion:reduce){dialog[open]{animation:none}}
@media (max-width:599px){dialog{width:100%;margin:auto 0 0;border-radius:var(--r-xl) var(--r-xl) 0 0;border-bottom:0;padding:var(--s-8) var(--s-16) calc(var(--s-16) + env(safe-area-inset-bottom))}
dialog form::before{content:"";display:block;width:40px;height:4px;border-radius:2px;background:var(--rule);margin:0 auto var(--s-6)}}
dialog h3{font:600 1.625rem/1.05 var(--font-display);margin:0 0 var(--s-4)}
@media (min-width:600px){dialog h3{font-size:var(--t-wall)}}
dialog p{margin:0 0 var(--s-12);color:var(--muted);font-size:var(--t-meta)}
dialog .dh{display:flex;align-items:flex-start;justify-content:space-between;gap:var(--s-12)}
dialog .dh h3{margin:var(--s-8) 0 0}
dialog .dh button{flex:none}
dialog .ds{display:flex;align-items:center;gap:var(--s-12);margin:var(--s-12) 0 0}
dialog .ds p{margin:0}
dialog .ovl{margin:0 0 var(--s-4);font:600 var(--t-small)/1.2 var(--font-display);letter-spacing:var(--overline-tracking);text-transform:uppercase;color:var(--muted)}
dialog .dm{margin:var(--s-12) 0 0;padding:10px var(--s-12);border-radius:var(--r-m);background:var(--sunk)}
#d-models{display:flex;flex-wrap:wrap;gap:var(--s-8)}
#d-models>div{flex:1 1 0;min-width:6.5rem;display:flex;align-items:center;gap:var(--s-8);font-size:var(--t-meta);color:var(--ink)}
#d-wallbox{margin:14px 0 0}
#d-walls{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--s-6) var(--s-12)}
@media (min-width:600px){#d-walls{grid-template-columns:repeat(3,minmax(0,1fr))}}
#d-walls>div{display:flex;align-items:flex-start;gap:var(--s-8);min-height:30px;font-size:var(--t-meta);line-height:1.25;color:var(--ink)}
#d-walls small{display:block;margin-top:var(--s-2);font-size:var(--t-micro);color:var(--muted)}
dialog p.blend{margin:14px 0 var(--s-12)}
dialog p.acts{display:flex;flex-wrap:wrap;gap:var(--s-8);margin:0 0 var(--s-8);font-size:0}
dialog p.acts a{flex:1 1 auto;display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:0 18px;border-radius:var(--r-m);font:500 var(--t-body)/1.2 var(--font-body);color:var(--ink);text-decoration:none;box-shadow:inset 0 0 0 1px var(--rule)}
dialog p.acts a#d-detail{background:var(--inv-bg);color:var(--inv-fg);font-weight:600;box-shadow:none}
dialog p.acts a:focus-visible{box-shadow:inset 0 0 0 1px var(--rule),var(--focus-ring)}
dialog p.acts a#d-detail:focus-visible{box-shadow:var(--focus-ring)}
@media (min-width:600px){dialog p.acts a{flex:0 1 auto;min-height:var(--tap)}}
@media (hover:hover){dialog p.acts a:hover{background:var(--sunk)}dialog p.acts a#d-detail:hover{background:var(--inv-bg);opacity:.9}}
dialog button{display:inline-flex;align-items:center;justify-content:center;min-height:var(--tap);min-width:var(--tap);font:500 var(--t-body)/1.2 var(--font-body);padding:0 var(--s-16);border:0;border-radius:var(--r-m);background:transparent;color:var(--ink);box-shadow:inset 0 0 0 1px var(--rule);cursor:pointer}
dialog button:focus-visible{box-shadow:inset 0 0 0 1px var(--rule),var(--focus-ring)}
@media (hover:hover){dialog button:hover{background:var(--sunk)}}
.bar{background:var(--paper);border-bottom:1px solid var(--rule)}
.bar>div{padding:var(--s-6) max(12px,calc((100% - var(--page-max)) / 2 + var(--page-pad)));min-height:56px;display:flex;align-items:center;justify-content:space-between;gap:var(--s-12)}
.bar img{display:block;height:36px;width:auto}
.bar a{display:inline-flex;align-items:center;min-height:var(--tap)}
.bar nav{display:flex;gap:var(--s-2);font:500 var(--t-lead)/1 var(--font-display)}
.bar nav a{padding:0 7px;white-space:nowrap;text-decoration:none}
.bar nav a[aria-current=page]{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:6px}
@media (hover:hover){.bar nav a:hover{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:6px}}
@media (max-width:400px){.bar>div{gap:var(--s-4)}.bar nav a{padding:0 5px}}
.sitefoot{display:none;max-width:var(--page-max);margin:0 auto;padding:0 var(--page-pad) var(--s-24)}
.sitefoot a{display:inline-flex;align-items:center;min-height:var(--tap);font-weight:500}
@media (max-width:339px){.bar nav a.nm{display:none}.sitefoot{display:block}}
"""

# The logo pack (Claude Design G2): logo files go to site/assets/, favicons to the site root.
# The header bar's background must stay exactly var(--paper): the logo's nails are drawn in that colour.
ASSETS_DIR = os.path.join(HERE, "assets")
LOGO_FILES = ["grip-logo-paper.svg", "grip-logo-dark.svg"]
ICON_FILES = ["favicon.svg", "favicon-32.png", "apple-touch-icon-180.png"]
# Self-hosted Barlow and Barlow Condensed, latin subset, from the @fontsource npm packages 5.3.0 (SIL Open Font Licence;
# the licence files sit beside them). The build copies assets/fonts/ to site/assets/fonts/.
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
FONT_FACES = [("Barlow", 400, "barlow-latin-400-normal.woff2"), ("Barlow", 500, "barlow-latin-500-normal.woff2"),
              ("Barlow", 600, "barlow-latin-600-normal.woff2"), ("Barlow Condensed", 500, "barlow-condensed-latin-500-normal.woff2"),
              ("Barlow Condensed", 600, "barlow-condensed-latin-600-normal.woff2")]
FONT_PRELOAD = ["barlow-latin-400-normal.woff2", "barlow-condensed-latin-600-normal.woff2"]  # the body text and the scores


def fonts(root=""):
    """The font links for a page's head: a preload for the two faces every page shows first, and the @font-face rules.
    root is the path back to the site root ("../" from detail/)."""
    pre = "".join(f'<link rel="preload" href="{root}assets/fonts/{f}" as="font" type="font/woff2" crossorigin>' for f in FONT_PRELOAD)
    faces = "".join(f'@font-face{{font-family:"{fam}";font-style:normal;font-weight:{wt};font-display:swap;'
                    f'src:url({root}assets/fonts/{f}) format("woff2")}}' for fam, wt, f in FONT_FACES)
    return f"{pre}<style>{faces}</style>"


def icon_links(root=""):
    """The favicon links for a page's head; root is the path back to the site root ("../" from detail/)."""
    return (f'<link rel="icon" href="{root}favicon.svg" type="image/svg+xml">'
            f'<link rel="icon" href="{root}favicon-32.png" sizes="32x32">'
            f'<link rel="apple-touch-icon" href="{root}apple-touch-icon-180.png">')


def logo(root, height, alt):
    """The logo, paper colours in light mode and dark colours in dark mode; the browser fetches only the one it shows."""
    width = round(height * 85.8 / 34.8)
    return (f'<picture><source srcset="{root}assets/grip-logo-dark.svg" media="(prefers-color-scheme: dark)">'
            f'<img src="{root}assets/grip-logo-paper.svg" width="{width}" height="{height}" alt="{alt}"></picture>')


NAV = [("forecast", "Forecast", ""), ("contribute", "Contribute", "log.html"), ("birds", "Birds", "birds.html"),
       ("method", "Method", "method.html")]  # the header nav: key, link text, page ("" is the home page)


def header_bar(root="", current=None):
    """The slim bar at the top of every page: the logo linking home, and the nav. current is the NAV key of the page
    shown, marked aria-current; crag pages pass None. root is the path back to the site root ("../" from detail/)."""
    links = []
    for key, text, page in NAV:
        attrs = ' aria-current="page"' if key == current else ""
        attrs += ' class="nm"' if key == "method" else ""
        links.append(f'<a href="{root + page or "./"}"{attrs}>{text}</a>')
    links = "".join(links)
    return (f'<header class="bar"><div><a class="logo" href="{root or "./"}" aria-label="Grip, forecast home">{logo(root, 36, "Grip")}</a>'
            f'<nav aria-label="Main">{links}</nav></div></header>')


def site_foot(root=""):
    """The foot of every page: below 340 px the nav drops Method, and this carries it instead."""
    return f'<footer class="sitefoot"><a href="{root}method.html">Method</a></footer>'

COAST_CSS = """
.coast{max-width:52rem}
.coast h2{margin:var(--s-8) 0 var(--s-4)}
.srow{display:grid;grid-template-columns:170px minmax(0,1fr);gap:var(--s-2) var(--s-12);align-items:center;margin:0 0 var(--s-6)}
.srow .zn{font-size:15px;font-weight:500;line-height:1.2}
.strip{display:flex;gap:var(--s-3)}
.strip span{display:flex;align-items:center;justify-content:center;flex:1 1 0;min-width:0;height:var(--score-m);border-radius:5px;font:600 var(--score-m-num)/1 var(--font-display);font-variant-numeric:tabular-nums;position:relative}
.coast .strip span{height:30px;border-radius:var(--r-xs);font-size:15px}
.strip.hrs span{height:auto;font:500 var(--t-micro)/1.3 var(--font-display);color:var(--muted)}
.coast .strip.hrs span{height:auto;font-size:var(--t-micro)}
.strip span:empty{border:1px dashed var(--rule)}
.strip span.past{background:var(--past);color:var(--past-ink)}
.strip span.now{box-shadow:var(--now-ring);z-index:1}
.coast .strip span.now{box-shadow:0 0 0 2px var(--paper),0 0 0 4px var(--ink)}
.today .strip.hrs{margin:0 0 var(--s-4)}
.today .strip{margin:var(--s-6) 0 var(--s-2)}
@media (max-width:599px){.srow{grid-template-columns:minmax(0,1fr);row-gap:var(--s-6);margin:0 0 var(--s-8)}.srow.head{margin:0 0 var(--s-2)}}
.find{margin:var(--s-16) 0 var(--s-24);max-width:40rem}
.find label{display:block;font-size:15px;font-weight:600;margin:0 0 var(--s-4)}
.find input{display:block;width:100%;height:48px;font:inherit;font-size:16px;padding:0 14px;border:1px solid var(--rule);border-radius:var(--r-m);background:var(--card);color:var(--ink)}
.find input:focus{outline:2px solid transparent;border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink),var(--focus-ring)}
.grid tr[hidden]{display:none}
.popw{max-width:40rem}
.pop,.pop thead,.pop tbody{display:block}
.pop tr{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--s-6) var(--s-12);padding:10px var(--s-12);border-bottom:1px solid var(--rule)}
.pop tbody tr:last-child{border-bottom:0}
.pop th,.pop td{display:block;padding:0;text-align:left;min-width:0}
.pop thead tr{padding:var(--s-8) var(--s-12)}
.pop thead th{font:600 var(--t-small)/1.2 var(--font-display);text-transform:uppercase;letter-spacing:var(--overline-tracking);color:var(--muted)}
.pop thead th small{font:inherit}
.pop thead th:first-child{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.pop tbody th{grid-column:1 / -1}
.pop tbody th a{font-weight:600;line-height:1.2;text-decoration:none}
@media (hover:hover){.pop tbody th a:hover{text-decoration:underline}}
.pop tbody th a:focus-visible{text-decoration:underline}
.pop td.pc{display:flex;align-items:center;gap:var(--s-8)}
.pc .num{width:var(--score-l);height:var(--score-l);font-size:var(--score-l-num);border-radius:var(--r-s)}
.pc .pw{display:block;min-width:0;font-size:var(--t-small);line-height:1.3;font-variant-numeric:tabular-nums}
.pc .w{display:block;font-weight:600}
.pc .h{display:block;color:var(--muted)}
.pc .dot{display:none}
.pc small{display:block;color:var(--muted);font-size:var(--t-small)}
"""

HOME_CSS = """
main.home{padding-top:0}
.fresh{margin:14px 0 0;font-size:var(--t-meta);color:var(--muted)}
.stale{margin:14px 0 0;padding:var(--s-12);background:var(--sunk);border:1px solid var(--ink);border-radius:var(--r-m);max-width:52rem}
.stale+.fresh{margin-top:var(--s-8)}
.ovl{margin:0;font:600 var(--t-small)/1.2 var(--font-display);letter-spacing:var(--overline-tracking);text-transform:uppercase;color:var(--muted)}
.cards{display:flex;flex-wrap:wrap;gap:var(--s-12);margin:10px 0 0}
.card{flex:1 1 300px;display:flex;align-items:center;gap:14px;min-width:0;padding:14px var(--s-16);background:var(--card);border:1px solid var(--rule);border-radius:var(--r-l)}
.card>div{min-width:0}
.card .ln{margin:2px 0 0;font:600 21px/1.2 var(--font-display)}
.card .cm{margin:2px 0 0;font-size:var(--t-meta);color:var(--muted)}
.num.past{background:var(--past);color:var(--past-ink)}
.num.none{background:var(--sunk);color:var(--muted);box-shadow:inset 0 0 0 1px var(--rule)}
.top{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--s-24) var(--s-32);margin:var(--s-24) 0 0;align-items:start}
.top h2{margin-top:0}
@media (min-width:900px){.top{grid-template-columns:minmax(0,3fr) minmax(0,2fr)}.top .popw{max-width:none}
#pop-h{display:flex;align-items:center;min-height:48px;margin-bottom:var(--s-4)}}
.top .scale{margin-bottom:0}
.popw .all{display:flex;align-items:center;min-height:var(--tap);padding:0 var(--s-12);border-top:1px solid var(--rule);font-weight:500}
a.all:focus-visible{border-radius:0 0 var(--r-l) var(--r-l)}
.ch{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:var(--s-8) var(--s-12)}
.coast .ch h2{margin:0}
.coast .hint{margin:var(--s-6) 0 10px}
.seg{display:inline-flex;padding:2px;border:1px solid var(--rule);border-radius:var(--r-m);background:var(--card)}
.seg[hidden]{display:none}
.seg button{min-height:40px;padding:0 14px;border:0;border-radius:var(--r-s);background:transparent;color:var(--ink);font:500 var(--t-body)/1 var(--font-display);cursor:pointer}
.seg button[aria-checked=true]{background:var(--inv-bg);color:var(--inv-fg);font-weight:600}
@media (hover:hover){.seg button[aria-checked=false]:hover{background:var(--sunk)}}
.cp+.cp{margin-top:var(--s-16)}
.cp .pday{margin:0 0 var(--s-6)}
.coast.js .pday{display:none}
.coast.js .cp+.cp{margin-top:0}
.help{margin:var(--s-24) 0 0;padding-top:var(--s-16);border-top:1px solid var(--rule)}
.help h2{margin:0 0 var(--s-4)}
.help .hint{margin:0 0 var(--s-12)}
.hcs{display:flex;flex-wrap:wrap;gap:var(--s-8)}
.hc{flex:1 1 240px;display:flex;flex-direction:column;gap:var(--s-4);min-height:var(--tap);padding:14px var(--s-16);background:var(--card);border:1px solid var(--rule);border-radius:var(--r-l);color:var(--ink);text-decoration:none}
a.hc:focus-visible{border-radius:var(--r-l)}
@media (hover:hover){.hc:hover{background:var(--sunk)}}
.hc .ht{font:600 var(--t-h3)/1.1 var(--font-display)}
.hc .hd{font-size:var(--t-meta);color:var(--muted)}
.hc .ha{margin-top:var(--s-6);font:600 15px/1.2 var(--font-body);text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}
@media (hover:hover){.hc:hover .ha{text-decoration-thickness:2px}}
.find{display:flex;flex-wrap:wrap;align-items:flex-end;gap:var(--s-8) var(--s-16);margin:var(--s-12) 0 var(--s-12);max-width:none}
.find[hidden]{display:none}
.find label{flex:1 1 280px;max-width:420px;margin:0;display:flex;flex-direction:column;gap:var(--s-4)}
.find input{font-weight:400}
.find .sub{margin:0 0 var(--s-12)}
.gridbox.nothing>.wrap,.gridbox.nothing::after{display:none}
.none-box{padding:var(--s-16);background:var(--card);border:1px solid var(--rule);border-radius:var(--r-l)}
.none-box p{margin:0 0 var(--s-4)}
.none-box button{min-height:var(--tap);padding:0;border:0;background:none;color:var(--ink);font:600 var(--t-body)/1.2 var(--font-body);text-decoration:underline;text-underline-offset:3px;cursor:pointer}
.sure{display:flex;flex-wrap:wrap;gap:var(--s-16) var(--s-32);margin:28px 0 0;padding-top:18px;border-top:1px solid var(--rule)}
.sure>div{flex:1 1 300px;min-width:0}
.sure h2{margin:0}
.sure p{margin:var(--s-6) 0 0;max-width:56ch}
.sure .links{display:flex;flex-wrap:wrap;gap:0 var(--s-16);margin-top:var(--s-4)}
.sure .links a{display:inline-flex;align-items:center;min-height:var(--tap);font-weight:500}
.rec{padding-top:var(--s-4)}
.sq{display:flex;flex-wrap:wrap;gap:var(--s-4)}
.sq i,.sql i{display:block;flex:none;width:22px;height:22px;border-radius:var(--r-xs)}
.sq i.in,.sql i.in{background:var(--ink)}
.sq i.near,.sql i.near{box-shadow:inset 0 0 0 2px var(--ink)}
.sq i.out,.sql i.out{border:1px dashed var(--muted)}
.sql{display:flex;flex-wrap:wrap;gap:var(--s-4) 14px;margin:var(--s-8) 0 0;font-size:var(--t-small);color:var(--muted)}
.sql span{display:inline-flex;align-items:center;gap:var(--s-6)}
.sql i{width:12px;height:12px;border-radius:2px}
dialog p.mh{margin:0;font:600 15px/1.3 var(--font-body);color:var(--ink)}
dialog p#d-ms{margin:var(--s-2) 0 var(--s-8)}
"""

METHOD_CSS = """
.foot{color:var(--muted);font-size:var(--t-small);margin-top:var(--s-32);padding-top:var(--s-12);border-top:1px solid var(--rule);max-width:72ch}
.foot p{margin:0 0 var(--s-8)}
"""

MATCH_JS = r"""
var GripMatch=(function(){  // crag name matching shared by the front page search and the log form
  function norm(s){
    return String(s||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase()
      .replace(/['`\u2018\u2019\u02bc\u00b4]/g,'').replace(/[^a-z0-9]+/g,' ').trim();
  }
  function key(s){return ' '+norm(s);}
  function matcher(q){  // a test for keys made by key(): true when every typed word starts one of the name's words, in any order
    var words=norm(q).split(' ').filter(Boolean);
    return function(k){return words.every(function(x){return k.indexOf(' '+x)>=0;});};
  }
  return {norm:norm,key:key,matcher:matcher};
})();
"""

FIND_JS = r"""
(function(){  // Find a crag: filters the seven-day grid's rows as you type; headings with no matching rows are hidden
  var wrap=document.getElementById('findbox'), box=document.getElementById('find'), count=document.getElementById('find-count'),
      grid=document.querySelector('.gridbox'), empty=document.getElementById('find-empty'), none=document.getElementById('find-none'),
      rows=[].slice.call(document.querySelectorAll('table.grid tbody tr')), all=count.textContent;
  var keys=rows.map(function(tr){return tr.dataset.find===undefined?null:GripMatch.key(tr.dataset.find);});
  function draw(){
    var q=GripMatch.norm(box.value), test=GripMatch.matcher(box.value), n=0, head=null, seen=0, said=box.value.trim();
    rows.forEach(function(tr,i){
      if(keys[i]===null){if(head){head.hidden=!!q&&!seen;}head=tr;seen=0;return;}
      var on=!q||test(keys[i]);
      tr.hidden=!on;
      if(on){n++;seen++;}
    });
    if(head){head.hidden=!!q&&!seen;}
    var nothing=!!q&&!n;
    var miss='No crag matches “'+said+'”. Try part of a name, such as Souter or Cove.';
    count.textContent=!q?all:nothing?miss:n+(n===1?' crag matches “':' crags match “')+said+'”';
    count.classList.toggle('vh',nothing);  // said once on screen, in the grid box with Clear; the status still announces it
    none.textContent=nothing?miss:'';
    empty.hidden=!nothing;grid.classList.toggle('nothing',nothing);
  }
  document.getElementById('find-clear').addEventListener('click',function(){box.value='';draw();box.focus();});
  box.addEventListener('input',draw);
  wrap.hidden=false;
  draw();  // a value restored on going back to the page
})();
"""

FADE_JS = r"""
(function(){  // the seven-day grid's right-hand fade shows the box scrolls; it goes once the box is scrolled to the end
  var box=document.querySelector('.gridbox'), sc=box&&box.querySelector('.wrap');
  if(!sc){return;}
  function draw(){box.classList.toggle('end',sc.scrollLeft+sc.clientWidth>=sc.scrollWidth-2);}
  sc.addEventListener('scroll',draw,{passive:true});
  window.addEventListener('resize',draw);
  draw();
})();
"""


def label(c):
    return c["name"] + (f" ({c['wall']})" if c.get("wall") else "")


def fmt(idx):
    return f"{rnd(idx):d}"


def pct(x):
    return f"{round(100 * x):d}%"


def groups_of(results):
    """Results grouped by crag name, in order: [(name, [wall results])]."""
    out, idx = [], {}
    for r in results:
        n = r["crag"]["name"]
        if n not in idx:
            idx[n] = len(out)
            out.append((n, []))
        out[idx[n]][1].append(r)
    return out


def birds_in(walls, days):
    """The bird note for a crag if any of the given dates falls in its nesting months, else None."""
    for r in walls:
        b = r["crag"].get("birds")
        if b and any(date.fromisoformat(d).month in set(b.get("months", [])) for d in days):
            return b
    return None


def best_wall(walls, day_iso):
    """(wall result, its daily entry) with the highest score that day, or (None, None)."""
    best = (None, None)
    for r in walls:
        d = r["daily"].get(day_iso)
        if d and (best[1] is None or d["index"] > best[1]["index"]):
            best = (r, d)
    return best


def log_link(c, day_iso, root=""):
    """The page log form, filled with this wall and date. root is the path back to the site root ("../" from detail/)."""
    return f"{root}log.html?" + urllib.parse.urlencode({"wall": label(c), "date": day_iso}, quote_via=urllib.parse.quote)


def note_link(c):
    q = f"{NOTES_URL}?usp=pp_url&{NOTES_CRAG}={urllib.parse.quote(c['name'])}"
    return q + (f"&{NOTES_WALL}={urllib.parse.quote(c['wall'])}" if c.get("wall") else "")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


WHY_WORDS = {  # factor key: (phrase when it helps, phrase when it holds the rock back)
    "air": ("dry air", "humid air"),
    "fog": ("clear air", "haar"),
    "dew": ("the rock well above the dew point", "rock close to the dew point"),
    "wdir": ("an offshore wind", "onshore air"),
    "wind": ("a drying breeze", "still air or an onshore gale"),
    "sun": ("sun on the face", "no sun"),
    "sea": ("a calm sea", "a big sea"),
    "wet": ("dry rock", "water on the rock"),
    "dry": ("dry rock on a grey day", "damp rock"),
    "seep": ("no seepage", "seepage after heavy rain"),
}
WHY_MIN = 2  # a factor is mentioned only when it is worth this many points or more, either way


def factor_means(hs):
    """Mean points per factor over some scored hours, from each hour's breakdown (the first model's figures)."""
    out = {}
    for k in WHY_WORDS:
        vals = [h["d"]["f"].get(k) for h in hs if h["d"]["f"].get(k) is not None]
        if vals:
            out[k] = sum(vals) / len(vals)
    return out


def worth_saying(means, sign=0, n=2):
    """Up to n factor keys worth WHY_MIN points or more, biggest first; sign 1 or -1 keeps only that side."""
    keys = [k for k, v in means.items() if abs(v) >= WHY_MIN and (sign == 0 or v * sign > 0)]
    return sorted(keys, key=lambda k: -abs(means[k]))[:n]


def why_figures(hs):
    """The first model's figures behind the factor points over some hours, as the hour-by-hour table shows them: mean humidity, rock
    over the dew point, wind speed and direction, sea at the wall (feet, as f_sea scores it), water on the rock, whether it rained,
    and the run of hours with the sun on the face. A figure the hours do not carry is left out, and its phrase is the plain one."""
    def mean(key):
        vals = [h["d"].get(key) for h in hs if h["d"].get(key) is not None]
        return sum(vals) / len(vals) if vals else None
    out = {k: mean(k) for k in ("rh", "margin", "ws", "ft", "film")}
    dirs = [h["d"]["wd"] for h in hs if h["d"].get("wd") is not None]
    if dirs:
        x = sum(math.cos(math.radians(v)) for v in dirs)
        y = sum(math.sin(math.radians(v)) for v in dirs)
        out["wd"] = math.degrees(math.atan2(y, x)) % 360
    notes = [h for h in hs if h["d"].get("sun") is not None]
    face = [h for h in notes if "on the face" in h["d"]["sun"]]
    out["face"] = (face[0]["t"][11:16], end_of(face[-1])) if face else None
    out["sunny"] = bool(notes) and any(h["d"]["sun"] != "cloud" and h["d"]["sun"] != "night" for h in notes)
    out["rain"] = any(h["d"].get("note") == "raining" for h in hs)
    return out


def why_phrase(k, v, fig):
    """One factor in words, with its figure where the hours carry it. v: the factor's mean points (its sign says which side)."""
    helps = v > 0
    plain = WHY_WORDS[k][0 if helps else 1]
    if k == "air" and fig.get("rh") is not None:
        return f"{'dry' if helps else 'humid'} air ({fig['rh']:.0f}% humidity)"
    if k == "dew" and fig.get("margin") is not None:
        m = rnd(fig["margin"])
        if helps:
            return f"the rock {m}°C above the dew point"
        return "rock at or below the dew point" if m <= 0 else f"rock only {m}°C above the dew point"
    if k == "wdir" and fig.get("wd") is not None:
        return f"{'an offshore wind' if helps else 'onshore air'} from the {compass(fig['wd'])}"
    if k == "wind" and fig.get("ws") is not None:
        if helps:
            return f"a drying breeze ({fig['ws']:.0f} km/h)"
        return f"still air ({fig['ws']:.0f} km/h)" if fig["ws"] < 5 else f"a strong onshore wind ({fig['ws']:.0f} km/h)"
    if k == "sun" and helps:
        if fig.get("face"):
            return f"sun on the face ({fig['face'][0]} to {fig['face'][1]})"
        if fig.get("sunny"):
            return "sunshine"
    if k == "sea" and fig.get("ft") is not None:
        return f"{'a calm' if helps else 'a big'} sea ({fig['ft'] / 3.281:.1f} m at the wall)"
    if k == "wet" and not helps:
        if fig.get("rain"):
            return "rain"
        if fig.get("film") is not None and fig["film"] > 0.02:
            return {"a trace": "a trace of water on the rock", "damp": "damp rock", "wet": "wet rock"}[water_words(fig["film"])]
    return plain


def phrase(means, keys, hs=None):
    fig = why_figures(hs) if hs else {}
    return " and ".join(why_phrase(k, means[k], fig) for k in keys)


def why_text(hs, now_hour=None, tomorrow=False):
    """One or two plain sentences on what holds a wall back before its best window and what drives the window.
    hs: the day's scored hours, earlier ones included; the window is the one plain_line names."""
    rest = hs if tomorrow else [x for x in hs if hour_of(x) >= now_hour]
    bw = best_window(rest)
    if not bw:
        return "No daylight hours left to explain."
    win = bw[1]
    start = win[0]["t"]
    out = []
    early = [h for h in hs if h["t"] < start]
    em = factor_means(early)
    held = worth_saying(em, -1)
    if held:
        when = "this morning" if hour_of(win[0]) <= 12 else f"until {start[11:16]}"
        if tomorrow:
            when = "tomorrow morning" if hour_of(win[0]) <= 12 else f"tomorrow until {start[11:16]}"
        out.append(f"Held back {when} by {phrase(em, held, early)}.")
    wm = factor_means(win)
    keys = worth_saying(wm)
    pos = [k for k in keys if wm[k] > 0]
    neg = [k for k in keys if wm[k] < 0]
    if pos and neg:
        out.append(f"The best window comes from {phrase(wm, pos, win)}, though {phrase(wm, neg, win)} still holds it back.")
    elif pos:
        out.append(f"The best window comes from {phrase(wm, pos, win)}.")
    elif neg:
        out.append(f"Even the best window is held back by {phrase(wm, neg, win)}.")
    elif held:
        out.append("The best window comes as that eases, with no single factor worth 2 points or more.")
    else:
        out.append("No single factor is worth 2 points or more either way; the score comes from several small ones.")
    return " ".join(out)


def face_hours(lat, lon, aspect, day):
    """The hours of a day when the sun is on the face, by the scoring's own test (f_sun with a clear sky),
    as [(first hour, hour after the last)] runs. [] when it never is, None when the aspect is unknown."""
    asp = COMPASS.get(aspect or "")
    if asp is None:
        return None
    on = []
    for h in range(24):
        dt = datetime(day.year, day.month, day.day, h, tzinfo=TZ)
        az, el = sun_position(dt.astimezone(timezone.utc), lat, lon)
        if f_sun(None, 0, az, el, asp)[0] >= 2:
            on.append(h)
    runs = []
    for h in on:
        if runs and runs[-1][1] == h:
            runs[-1][1] = h + 1
        else:
            runs.append([h, h + 1])
    return [tuple(r) for r in runs]


def face_text(hours, when="today"):
    if hours is None:
        return "Aspect unknown, so Grip never counts the sun as on the face."
    if not hours:
        return f"The sun does not reach this face at any hour {when}."
    return f"Sun on the face {when}, when it shines: " + " and ".join(f"{a:02d}:00 to {b:02d}:00" for a, b in hours) + "."


def swell_side(wave_dir, aspect):
    """Where the waves come from relative to the face, on the scoring's own split: 'onto' (counted in full, within
    90 degrees of the aspect), 'along' (90 to 135) or 'behind' (beyond 135). None if either direction is unknown."""
    asp = COMPASS.get(aspect or "") if isinstance(aspect, str) else aspect
    if wave_dir is None or asp is None:
        return None
    d = ang_diff(wave_dir, asp)
    return "onto" if d <= 90 else "along" if d <= 135 else "behind"


def sea_text(height, wave_dir, period, aspect, inlet=False, sea_sheltered=False, tidal=False):
    """The sea at the wall in plain words: direction against the face, period, and what the scoring makes of it."""
    if height is None:
        return "No sea forecast for this hour."
    side = swell_side(wave_dir, aspect)
    long_ = period is not None and period >= 9
    parts = []
    where = {"onto": "onto the face", "along": "along the face", "behind": "from behind the face"}.get(side)
    per = f", period {period:.1f} s ({'long swell' if long_ else 'short wind sea'})" if period is not None else ""
    if where:
        parts.append(f"Coming from the {compass(wave_dir)}, {where}{per}.")
    elif wave_dir is not None:
        parts.append(f"Coming from the {compass(wave_dir)}{per}; the face's aspect is unknown, so Grip counts it in full.")
    if inlet:
        parts.append("In the inlet the swell funnels and reflects, so Grip counts it at 1.5 times its height from any direction.")
    elif side in ("along", "behind"):
        parts.append(f"Grip counts it at {'70' if long_ else '40'}% of its height{', as long swell wraps round headlands' if long_ else ''}.")
    elif sea_sheltered:
        parts.append("Offshore rock breaks it, so Grip counts it at half height.")
    else:
        parts.append("Grip counts it in full.")
    pts, ft, eff = f_sea(height, wave_dir, period, COMPASS.get(aspect or ""), inlet, sea_sheltered)
    spray_at = 2.0 if tidal else 2.5
    parts.append(f"That is {eff:.1f} m at the wall, {pts:+d} point{'s' if abs(pts) != 1 else ''} for the sea"
                 + (f", and spray is adding water to the rock (over {spray_at:g} m)." if eff >= spray_at
                    else f"; spray starts adding water to the rock over {spray_at:g} m at the wall."))
    return " ".join(parts)


def water_words(film):
    """The water the model has on the rock, in words, on the scoring's own thresholds."""
    return "dry" if film <= 0.02 else "a trace" if film <= 0.1 else "damp" if film <= 0.5 else "wet"


def rain_totals(h, now):
    """Rain in the 24 and 72 hours before the current hour from one model's hourly data, summed as the seepage factor
    sums it; None where the data does not reach back that far."""
    times = h.get("time") or []
    key = now.strftime("%Y-%m-%dT%H:00")
    if key not in times:
        return None, None
    i = times.index(key)
    pr = series(h, "precipitation")
    return tuple(sum(v for v in pr[i - n:i] if v is not None) if i >= n else None for n in (24, 72))


def zone_now(cfg, models, marine, now):
    """Per weather point, the rain behind the current hour (first model with data) and the sea now and today."""
    out = {}
    key = now.strftime("%Y-%m-%dT%H:00")
    for zk in cfg["zones"]:
        z = {"rain": None, "sea": None}
        for mid, lab, _d, _w in MODELS:
            h = models.get(zk, {}).get(mid)
            if h and any(v is not None for v in series(h, "precipitation")):
                r24, r72 = rain_totals(h, now)
                if r24 is not None:
                    z["rain"] = (lab, r24, r72)
                    break
        m = marine.get(zk, {})
        times = m.get("time") or []
        if key in times:
            i = times.index(key)
            hs = series(m, "wave_height")
            today = [v for t, v in zip(times, hs) if t[:10] == key[:10] and v is not None]
            z["sea"] = {"h": hs[i], "dir": series(m, "wave_direction")[i], "period": series(m, "wave_period")[i],
                        "max": max(today) if today else None}
        out[zk] = z
    return out


def logged_days(cfg):
    """Every scored logged day, merged as on the front page, with the wall it was matched to: [(row, wall)]."""
    try:
        with open(CAL_FILE) as f:
            cache = json.load(f)
    except Exception:  # noqa: BLE001
        return []
    crags = {label(c): c for c in cfg["crags"]}
    for c in cfg["crags"]:
        crags.setdefault(c["name"], c)
    rows = merge_days([v for k, v in cache.items() if k.startswith(MODEL_VERSION + "|") and v.get("grip") is not None])
    return [(v, resolve_wall(cfg, v, crags)) for v in sorted(rows, key=lambda v: v["date"], reverse=True)]


TIDAL_MEANS = "Grip pulls the rock temperature harder towards the sea's, and counts spray from a 2 m sea rather than 2.5 m."
# Source tags in the data's notes, such as "(SMC)", "(UKC)", "(SMC database)", "(UKC and SMC)" or "(developers' notes, 2020)".
# The crag pages leave them out (one sources line at the foot says where the facts come from); the data files keep them.
SOURCE_TAG = re.compile(r"\s*\((?:SMC|UKC|UKClimbing|developers['’]? notes)\b[^()]*\)")
STOCK_BIRD_NOTES = ("Nesting birds noted in the SMC database", "Free of nesting birds")  # say no more than the status itself


def strip_sources(text):
    """A note without its source tags; nothing else in it changes."""
    return SOURCE_TAG.sub("", text or "").strip()


def bird_status(b):
    """A wall's nesting-bird status: "nesting", "clear" (bird free) or "unknown" (no information). Unknown is never clear."""
    if not b:
        return "unknown"
    if b.get("level") == "clear":
        return "clear"
    return "nesting" if b.get("level") in ("affected", "restricted", "possible") else "unknown"


def birds_line(b):
    """The birds line on a wall card, mapped exactly from the status: "None reported" for bird free, "Reported nesting" with the months
    (and "months not confirmed" while they are a placeholder) for nesting, "No information" when Grip has nothing."""
    st = bird_status(b)
    if st == "unknown":
        return "No information. Grip does not know whether birds nest here."
    note = strip_sources(b.get("note"))
    note = re.sub(r";?\s*months not confirmed\.?$", "", note).strip().rstrip(".")
    if note.startswith(STOCK_BIRD_NOTES):
        note = ""
    if st == "clear":
        return "None reported." + (f" {note}." if note else "")
    months = sorted(b.get("months") or [])
    if months:
        line = f"Reported nesting, {MONTHS[months[0]]} to {MONTHS[months[-1]]}" + ("" if b.get("confirmed") else ", months not confirmed") + "."
    else:
        line = "Reported nesting, months not known."
    if b.get("level") == "restricted":
        line += " Climbing is restricted while they nest."
    return line + (f" {note}." if note else "")


def birds_in_season(b, days):
    """True when a wall's birds are reported nesting in the month of any of the given dates."""
    return bird_status(b) == "nesting" and any(d.month in set(b.get("months") or []) for d in days)


def tide_tag(c):
    note = (c.get("tidal_note") or "").lower()
    if c.get("tidal"):
        return "Part tidal" if ("partial" in note or "partly" in note) else "Mainly tidal" if "mainly" in note else "Tidal"
    return "Not tidal" if "non" in note else "Tide not known"


def wall_sub(c):
    """The line under a wall's name in the walls list and its summary: aspect, then tide and seepage where they apply."""
    parts = [f"Faces {c['aspect']}" if c.get("aspect") else "Aspect not known"]
    if c.get("tidal"):
        parts.append(tide_tag(c).lower())
    if c.get("seeps") or c.get("seep_note") or c.get("seep_until_month"):
        parts.append("seeps")
    return " · ".join(parts)


def wall_tags(c, days):
    """The pills under a wall's name: aspect, shelter, tide, and birds when they are nesting on the days shown."""
    tags = [f"Faces {c['aspect']}" if c.get("aspect") else "Aspect not known"]
    if c.get("inlet"):
        tags.append("Inlet")
    elif c.get("sheltered"):
        tags.append("Sheltered bay")
    elif not c.get("sea_sheltered"):
        tags.append("Open")
    if c.get("sea_sheltered"):
        tags.append("Sea-sheltered")
    tags.append(tide_tag(c))
    if birds_in_season(c.get("birds"), days):
        tags.append("Birds nesting now")
    return tags


def open_wall(walls, day_iso):
    """The wall a multi-wall crag page opens by default: the best score on the day shown (today, or tomorrow after dark), as shown,
    ties to the most climbable hours, then the first in the list. Returns its index."""
    def key(i):
        d = walls[i]["daily"].get(day_iso)
        return (rnd(d["index"]), d["usable"], -i) if d else (-1, -1, -i)
    return max(range(len(walls)), key=key)


def wall_name(c):
    return c.get("wall") or "Main face"


def wall_ids(walls):
    """An id per wall card from its name, for links and the URL hash, unique on the page."""
    out, seen = [], {"walls-h", "sure-h", "across-h", "hour-by-hour", "logged-h"}
    for r in walls:
        base = slug(wall_name(r["crag"])) or "wall"
        i, x = 1, base
        while x in seen:
            i += 1
            x = f"{base}-{i}"
        seen.add(x)
        out.append(x)
    return out


def rock_word(r):
    """The water on a wall's rock now, in words, with the film behind it; None when the build has no figure."""
    if not r.get("film_now"):
        return None
    return water_words(r["film_now"][1])


def rain_words(rain):
    """The rain behind the current hour at the weather point, in words: "0.6 mm of rain in 24 hours, 1.4 mm in 72." """
    if not rain:
        return "Recent rain not available."
    _lab, r24, r72 = rain
    return f"{r24:.1f} mm of rain in 24 hours" + (f", {r72:.1f} mm in 72." if r72 is not None else ".")


def across_facts(walls, zone, zn, tides, days, labels):
    """What Across the crag states once, and what each wall card adds because it differs.
    Across: rock now (the word most walls share, with the rain), low water, the sea, the weather point.
    Returns (across: [(heading, text)], per_wall: [[(heading, text)]]): a wall carries Rock now only when its own word differs."""
    words = [rock_word(r) for r in walls]
    known = [x for x in words if x]
    common = max(known, key=lambda x: (known.count(x), -known.index(x))) if known else None
    if common is None:
        rock = "Not available."
    elif known.count(common) == len(walls) or len(walls) == 1:
        rock = common[0].upper() + common[1:] + "."
    else:
        rock = f"{common[0].upper() + common[1:]} on {known.count(common)} of {len(walls)} walls."
    rock += " " + rain_words(zn.get("rain"))
    lw = []
    for i, (d, word) in enumerate(zip(days, labels)):
        t = tides.get(walls[0]["crag"]["zone"], {}).get(d.isoformat(), [])
        lw.append(f"{word} {', '.join(t)}." if t else f"{word} not available.")
    lw = " ".join(lw)
    sea = zn.get("sea")
    if sea and sea["h"] is not None:
        sea_s = f"{sea['h']:.1f} m" + (f" from the {compass(sea['dir'])}" if sea.get("dir") is not None else "")
        if sea.get("period") is not None:
            sea_s += f", {sea['period']:.0f} s {'swell' if sea['period'] >= 9 else 'wind sea'}"
        sea_s += "." + (f" Up to {sea['max']:.1f} m today." if sea.get("max") is not None else "")
    else:
        sea_s = "No sea forecast available."
    faces = zone.get("coast_faces", 112.5)
    facing = next((k for k, v in COMPASS.items() if v == faces), f"{faces:g} degrees")
    weather = f"{zone['name']} point, shared along this stretch. Coast counted as facing {facing}."
    across = [("Rock now", rock), ("Low water", lw), ("Sea", sea_s), ("Weather", weather)]
    per_wall = []
    for r, x in zip(walls, words):
        items = []
        if x and x != common:
            items.append(("Rock now", f"{x[0].upper() + x[1:]} ({r['film_now'][1]:.2f} mm on the rock)."))
        per_wall.append(items)
    return across, per_wall


def wall_sea_text(sea, c):
    """The sea against one wall, in the wording table's form: where it comes from against the face, how much of it Grip counts,
    and the height at the wall. "Onto the face, counted in full: 1.1 m at the wall." """
    if not sea or sea["h"] is None:
        return "No sea forecast available."
    asp = COMPASS.get(c.get("aspect") or "")
    inlet, sheltered = bool(c.get("inlet")), bool(c.get("sea_sheltered"))
    side = swell_side(sea["dir"], c.get("aspect"))
    long_ = sea.get("period") is not None and sea["period"] >= 9
    where = {"onto": "Onto the face", "along": "Runs along the face", "behind": "Comes from behind the face"}.get(side, "Aspect not known")
    if inlet:
        how = "funnels in the inlet, counted at 1.5 times"
    elif side in ("along", "behind"):
        how = f"counted at {'70%, as long swell wraps round' if long_ else '40%'}"
    elif sheltered:
        how = "broken by offshore rock, counted at half"
    else:
        how = "counted in full"
    _pts, _ft, eff = f_sea(sea["h"], sea["dir"], sea.get("period"), asp, inlet, sheltered)
    return f"{where}, {how}: {eff:.1f} m at the wall."


def sun_text(hours, when="today"):
    """Sun on the face in the wording table's form: "On the face 09:00 to 14:00, when it shines." """
    if hours is None:
        return "Aspect not known, so Grip never counts the sun as on the face."
    if not hours:
        return f"Does not reach the face {when}."
    return "On the face " + " and ".join(f"{a:02d}:00 to {b:02d}:00" for a, b in hours) + ", when it shines."


def shapes_items(c, zone, day, when, sea):
    """What shapes this wall, as (heading, text): only what is particular to the wall. The sun and the sea depend on its aspect;
    shelter and tide appear when they change the scoring; seepage and birds always."""
    items = []
    asp = c.get("aspect")
    sun = sun_text(face_hours(zone["lat"], zone["lon"], asp, day), when)
    if asp and c.get("aspect_note"):
        sun = f"Faces {c['aspect_note']} in places, scored as {asp}. " + sun
    items.append(("Sun", sun))
    shelter = []
    if c.get("sheltered") and c.get("inlet"):
        shelter.append("Narrow inlet. Wind counted at half from every direction.")
    elif c.get("sheltered"):
        shelter.append("Back of a bay. Wind counted at half unless it blows onto the face.")
    if c.get("sea_sheltered"):
        shelter.append("Offshore rock breaks the swell.")
    if c.get("sheltered"):
        shelter.append("Shelter does not slow drying.")
    if shelter:
        items.append(("Shelter", " ".join(shelter)))
    items.append(("Sea", wall_sea_text(sea, c)))
    if c.get("tidal"):
        items.append(("Tide", TIDAL_MEANS))
    elif "non" not in (c.get("tidal_note") or "").lower():
        items.append(("Tide", "Tidal status not known; scored as not tidal."))
    seep = []
    if c.get("seeps"):
        seep.append("Known to seep after rain.")
    if c.get("seep_note"):
        seep.append(strip_sources(c["seep_note"]).rstrip(".") + ".")
    if c.get("seep_until_month"):
        seep.append(f"Usually wet until {MONTHS[c['seep_until_month']]}.")
    items.append(("Seepage", " ".join(seep) or "None noted."))
    items.append(("Birds", birds_line(c.get("birds"))))
    return items


def score_block(d, size="sz-m", when=""):
    """A day's score block with its number, stripes when the models disagree and a dot for wet-rock risk; a dash when not scored."""
    if not d:
        return f'<span class="num {size} none" role="img" aria-label="{when + ": " if when else ""}not scored">-</span>'
    name, _note, css = band(d["index"])
    unsure, risk = d["spread"] > 2 or d["n"] < 2, d["wet"] >= 0.3
    said = f"{when + ': ' if when else ''}{fmt(d['index'])} {name}" + (", wet-rock risk" if risk else "") + (", models disagree" if unsure else "")
    cls = css + (" unsure" if unsure else "") + (" risk" if risk else "")
    return f'<span class="num {size} {cls}" role="img" aria-label="{said}">{fmt(d["index"])}</span>'


def week_html(r, today):
    """One cell per day for the next seven days: score, best window as hours ("11–14") and climbable hours."""
    days = [d for d in sorted(r["daily"]) if date.fromisoformat(d) >= today][:7]
    if not days:
        return '<p class="sub">No days scored.</p>'
    cells = []
    for d in days:
        v = r["daily"][d]
        name, _note, css = band(v["index"])
        dd = date.fromisoformat(d)
        cells.append(f'<div role="listitem" aria-label="{dd.strftime("%A %-d %B")}: {fmt(v["index"])}, {name}, best {v["start"]} to {v["end"]}, '
                     f'{v["usable"]} of {v["hours"]} daylight hours climbable"><span class="dn">{dd.strftime("%a")}</span><b class="num {css}">{fmt(v["index"])}</b>'
                     f'<span>{v["start"][:2]}–{v["end"][:2]}</span><span>{v["usable"]} h</span></div>')
    return '<div class="week" role="list">' + "".join(cells) + "</div>"


def sure_items(walls, days, today):
    """How sure on a crag page: the home pop-up's models sentence for every wall and day shown where the models do not agree.
    Returns [(wall result, day, sentence)]; empty when they agree everywhere."""
    out = []
    for r in walls:
        for d in days:
            di = d.isoformat()
            v = r["daily"].get(di)
            if not v:
                continue
            kind, said = models_sentence(r, di, v, d == today)
            if kind != "a":
                out.append((r, d, said))
    return out


FACTOR_LABEL = [("air", "air"), ("fog", "haar"), ("dew", "dew"), ("wdir", "wind dir"), ("wind", "wind"), ("sun", "sun"),
                ("sea", "sea"), ("wet", "wet"), ("dry", "dry rock"), ("seep", "seep")]  # the points column, in this order


def wet_words(hr):
    """Wet-rock risk for an hour: how many of the models scoring it have the rock wet, foggy or raining."""
    n = hr.get("n") or len(hr.get("models") or []) or 1
    k = round(hr["wet"] * n)
    return "None" if k == 0 else f"{k} in {n}"


def points_text(x):
    """The points column: each factor worth something as shown, zero factors left out, then the water note."""
    f = x["f"]
    parts = [f"{lab} {fpt(f.get(k))}" for k, lab in FACTOR_LABEL if f.get(k) is not None and fpt(f.get(k)) not in ("+0", "-0")]
    out = " · ".join(parts) or "all factors 0"
    return out + (f" ({x['note']})" if x.get("note") else "")


def hour_cells(hr):
    """One row of the hour-by-hour table as shown: {time, grip, models [(name, score shown or None)], wet, humidity, margin, wind, sun,
    sea, points}. The figures after the scores are the first model's that has the hour, as the factor points are."""
    x = hr["d"]
    m = dict(hr["models"])
    return {
        "time": hr["t"][11:16], "grip": fmt(hr["index"]),
        "models": [(lab, fmt(m[lab]) if lab in m else None) for _id, lab, _d, _w in MODELS],  # rounded as Grip's own score
        "wet": wet_words(hr),
        "humidity": f'{x["rh"]:.0f}%' if x.get("rh") is not None else "?",
        "margin": f'{x["margin"]:+.1f}°C' if x.get("margin") is not None else "-",
        "wind": f'{compass(x["wd"])} {x["ws"]:.0f} km/h' if x.get("ws") is not None else "?",
        "sun": x.get("sun") or "",
        "sea": f'{x["ft"] / 3.281:.1f} m' if x.get("ft") is not None else "-",  # f_sea scores in feet; shown in metres
        "points": points_text(x),
    }


def hours_table(hs, caption):
    """The hour-by-hour table for one wall and one day."""
    out = [f'<table class="hours"><caption>{escape(caption)}</caption><thead><tr><th scope="col">Time</th><th scope="col">Grip</th>'
           '<th scope="col">Models</th><th scope="col">Wet risk</th><th scope="col">Humidity</th><th scope="col">Rock over dew point</th>'
           '<th scope="col">Wind</th><th scope="col">Sun</th><th scope="col">Sea at wall</th><th scope="col">Points</th></tr></thead><tbody>']
    for hr in hs:
        x = hour_cells(hr)
        name = band(hr["index"])[0]
        unsure = hr.get("n", 2) >= 2 and hr.get("spread", 0) > 2
        grip = (f'<span class="num sz-hb {band(hr["index"])[2]}{" unsure" if unsure else ""}" role="img" '
                f'aria-label="{x["grip"]} {name}{", models differ by more than 2" if unsure else ""}">{x["grip"]}</span>')
        mods = "".join(f'<span class="num sz-xs {band(float(s))[2]}" role="img" aria-label="{lab} {s}">{s}</span>' if s is not None
                       else f'<span class="num sz-xs none" role="img" aria-label="{lab}: no forecast">-</span>' for lab, s in x["models"])
        wr = ' class="wr"' if x["wet"] != "None" else ""  # wet risk in 600 weight only when there is one
        out.append(f'<tr><th scope="row">{x["time"]}</th><td>{grip}</td><td class="mods">{mods}</td><td{wr}>{x["wet"]}</td>'
                   f'<td>{x["humidity"]}</td><td>{x["margin"]}</td><td>{x["wind"]}</td><td>{escape(x["sun"])}</td><td>{x["sea"]}</td>'
                   f'<td class="pts">{escape(x["points"])}</td></tr>')
    out.append("</tbody></table>")
    return "".join(out)


DETAIL_CSS = """
.crumb{margin:0 0 var(--s-6);font-size:var(--t-meta);color:var(--muted)}
.crumb a{color:var(--ink)}
main.crag h1{margin:0}
@media (min-width:900px){main.crag h1{font-size:2.5rem;line-height:1}}
.tb{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:var(--s-12) var(--s-24);margin:0 0 var(--s-20)}
.meta{margin:var(--s-6) 0 0;font-size:var(--t-meta);color:var(--muted)}
.acts{display:flex;flex-wrap:wrap;gap:var(--s-8);margin:0}
.acts .btn{margin:0}
.cols{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--s-16) var(--s-32);align-items:start}
@media (min-width:900px){.cols{grid-template-columns:minmax(0,320px) minmax(0,1fr)}}
.side>*+*,.body>*+*{margin-top:var(--s-16)}
.box{background:var(--card);border:1px solid var(--rule);border-radius:var(--r-l);padding:14px var(--s-16)}
.box h2{margin:0 0 var(--s-8);font-size:var(--t-h3)}
.ovl{margin:0;font:600 var(--t-small)/1.2 var(--font-display);letter-spacing:var(--overline-tracking);text-transform:uppercase;color:var(--muted)}
.wlist{padding:0;overflow:hidden}
.wlist ul{margin:0;padding:0;list-style:none}
.wlist .wh,.wlist a{display:grid;grid-template-columns:minmax(0,1fr) 52px 52px;align-items:center;gap:var(--s-8);padding:0 var(--s-12)}
.wlist .wh{align-items:end;padding-top:10px;padding-bottom:var(--s-6)}
.wlist .wh h2{margin:0;line-height:1}
.wlist .wh span{text-align:center;font-size:var(--t-micro);line-height:1}
.wlist a{min-height:var(--tap);padding-top:5px;padding-bottom:5px;border-top:1px solid var(--rule);text-decoration:none;color:var(--ink)}
.wlist a>.num{justify-self:center}
.wlist a[aria-current]{background:var(--sunk);box-shadow:inset 3px 0 0 var(--ink)}
.wlist a:focus-visible{border-radius:0;position:relative;z-index:1}
.wlist a[aria-current]:focus-visible{box-shadow:inset 3px 0 0 var(--ink),var(--focus-ring)}
.wlist .wn{font-size:15px;font-weight:600;line-height:1.2}
.wlist .wn small{display:block;font-weight:400;font-size:var(--t-micro);color:var(--muted)}
@media (hover:hover){.wlist a:hover .wn{text-decoration:underline}}
.sure{border:2px solid var(--ink)}
.sure p{margin:0 0 var(--s-8);font-size:15px}
.sure p:last-child{margin-bottom:0}
.sure h3{margin:var(--s-12) 0 var(--s-2);font:600 15px/1.2 var(--font-body)}
.across dl,.wall dl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:var(--s-6) 14px;margin:0;font-size:var(--t-meta)}
.wall dl{gap:var(--s-4) 14px}
.across dt,.wall dt{font-weight:600}
.across dd,.wall dd{margin:0;max-width:72ch}
.fn{margin:var(--s-8) 0 0;font-size:var(--t-small);color:var(--muted)}
.wall{background:var(--card);border:1px solid var(--rule);border-radius:var(--r-l)}
.wall>summary{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:var(--s-8);min-height:48px;padding:var(--s-8) var(--s-16);cursor:pointer;list-style:none;border-radius:var(--r-l)}
.wall>summary::-webkit-details-marker{display:none}
.wall>summary h2{margin:0;font-size:var(--t-h2);overflow-wrap:anywhere}
@media (min-width:600px){.wall[open]>summary h2{font-size:var(--t-wall)}}
.wall>summary h2 small{display:block;font:400 var(--t-meta)/1.3 var(--font-body);color:var(--muted)}
.wall:not([open])>summary{padding-top:var(--s-6);padding-bottom:var(--s-6)}
.wall:not([open])>summary h2{font-size:17px;line-height:1.2}
.wall:not([open])>summary h2 small{display:inline;margin-left:var(--s-4);font-size:var(--t-small)}
.wall:not([open])>summary .mk{color:var(--muted);font-size:1.25rem}
.wl-hint{margin:0 0 calc(-1 * var(--s-8))}
.wall>summary .sb{display:flex;align-items:center;gap:var(--s-8)}
.wall>summary .mk{display:inline-flex;align-items:center;justify-content:center;width:var(--tap);height:var(--tap);font:500 1.75rem/1 var(--font-display)}
.wall>summary .mk::before{content:"+"}
.wall[open]>summary .mk::before{content:"\\2212"}
.wall[open]>summary{border-bottom:1px solid var(--rule);border-radius:var(--r-l) var(--r-l) 0 0}
@media (hover:hover){.wall>summary:hover h2{text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:4px}}
.wb{padding:var(--s-4) var(--s-16) var(--s-20)}
article.wall .wb{padding-top:var(--s-12)}
article.wall h2{margin:0;font-size:var(--t-wall)}
.wb .tr{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:var(--s-2) var(--s-12);margin:var(--s-4) 0 0}
.wb .lg{display:inline-flex;align-items:center;min-height:var(--tap);font-size:15px}
.tags{display:flex;flex-wrap:wrap;gap:var(--s-6);margin:0;padding:0;list-style:none}
.tags li{display:inline-flex;align-items:center;min-height:26px;padding:var(--s-2) 10px;border:1px solid var(--rule);border-radius:var(--r-pill);font-size:var(--t-small);line-height:1.2}
.tags li.in{border-color:var(--ink);font-weight:600}
.wb h3{margin:var(--s-20) 0 var(--s-6);font:600 var(--t-small)/1.2 var(--font-display);letter-spacing:var(--overline-tracking);text-transform:uppercase;color:var(--muted)}
.wb p{margin:0 0 var(--s-6);max-width:72ch}
.wb .why{margin-top:14px;padding-top:var(--s-12);border-top:1px solid var(--rule)}
.wb .why h3{margin-top:0}
.today .dayline{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--s-2) 10px;margin:var(--s-16) 0 0}
.today .dayline h3{margin:0}
.today .line{margin:0;font-size:var(--t-lead);font-weight:600;line-height:1.25}
.week{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:var(--s-3);max-width:36rem}
.week div{text-align:center;font-size:var(--t-micro);line-height:1.3;min-width:0;color:var(--muted);font-variant-numeric:tabular-nums}
.week span{display:block}
.week .dn{font:600 var(--t-small)/1.3 var(--font-display);color:var(--ink)}
.week span:nth-of-type(2){color:var(--ink)}
.week b{display:flex;width:100%;max-width:48px;height:38px;margin:var(--s-3) auto;border-radius:5px;font-size:1.25rem}
.num.none{background:var(--sunk);color:var(--muted);box-shadow:inset 0 0 0 1px var(--rule)}
.hbc{display:flex;flex-wrap:wrap;align-items:flex-end;gap:var(--s-8) var(--s-16);margin:0 0 var(--s-12)}
.hbc[hidden]{display:none}
.hbc label{display:flex;flex-direction:column;gap:var(--s-4);font-size:15px;font-weight:600}
.hbc select{min-height:var(--tap);min-width:12rem;max-width:100%;padding:0 var(--s-8);font:400 16px var(--font-body);color:var(--ink);background:var(--card);border:1px solid var(--rule);border-radius:var(--r-m)}
.hbc select:focus-visible{border-color:var(--ink)}
.tabs{display:inline-flex;flex-wrap:wrap;padding:2px;border:1px solid var(--rule);border-radius:var(--r-m);background:var(--card)}
.tabs button{min-height:40px;padding:0 14px;border:0;border-radius:var(--r-s);background:transparent;color:var(--ink);font:500 var(--t-body)/1 var(--font-display);cursor:pointer}
.tabs button[aria-selected=true]{background:var(--inv-bg);color:var(--inv-fg);font-weight:600}
@media (hover:hover){.tabs button[aria-selected=false]:hover{background:var(--sunk)}}
details.hb{margin:0 0 var(--s-12)}
details.hb>summary{min-height:var(--tap);display:flex;align-items:center;font-weight:600;cursor:pointer}
.hbs.js details.hb>summary{display:none}
details.hb[hidden]{display:none}
.hours{min-width:820px;font-size:var(--t-meta);font-variant-numeric:tabular-nums}
.hours caption{padding:var(--s-8) var(--s-12);text-align:left;font-size:var(--t-small);color:var(--muted);border-bottom:1px solid var(--rule);caption-side:top}
.hours th,.hours td{height:40px;padding:var(--s-4) var(--s-6);text-align:left;border-top:1px solid var(--rule);white-space:nowrap}
.hours tbody th{position:sticky;left:0;z-index:1;padding:var(--s-4) 10px;background:var(--card);box-shadow:1px 0 0 var(--rule);font:600 15px/1 var(--font-display)}
.hours thead th{font:600 var(--t-micro)/1.1 var(--font-display);text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.hours thead th:first-child{position:sticky;left:0;z-index:1;background:var(--card);box-shadow:1px 0 0 var(--rule)}
.hours .sz-hb{width:34px;height:34px;font-size:var(--score-m-num);border-radius:var(--r-s)}
.hours td.mods{display:table-cell}
.hours td.mods .num{margin-right:var(--s-3)}
.hours td.wr{font-weight:600}
.hours td.pts{color:var(--muted)}
.cal td small{color:var(--muted)}
.body .cal{width:100%;min-width:420px}
.foot{color:var(--muted);font-size:var(--t-small);margin-top:var(--s-32);padding-top:var(--s-12);border-top:1px solid var(--rule)}
"""

CRAG_JS = r"""
(function(){  // walls: open the best wall (or the one in the URL hash) and close the rest; the walls list marks the open wall
  var walls=[].slice.call(document.querySelectorAll('details.wall')), links=[].slice.call(document.querySelectorAll('.wlist a'));
  if(!walls.length){return;}
  var main=document.querySelector('main.crag');
  function mark(id){links.forEach(function(a){if(a.getAttribute('href')==='#'+id){a.setAttribute('aria-current','true');}else{a.removeAttribute('aria-current');}});}
  function pick(id){
    var t=id&&document.getElementById(id);
    if(!t||walls.indexOf(t)<0){return false;}
    t.open=true;mark(id);return true;
  }
  var h='';try{h=decodeURIComponent(location.hash.slice(1));}catch(e){}
  walls.forEach(function(d){d.open=false;});
  if(!pick(h)){pick(main.getAttribute('data-open'));}
  walls.forEach(function(d){d.addEventListener('toggle',function(){if(d.open){mark(d.id);}});});
  links.forEach(function(a){a.addEventListener('click',function(){pick(a.getAttribute('href').slice(1));});});
  window.addEventListener('hashchange',function(){try{pick(decodeURIComponent(location.hash.slice(1)));}catch(e){}});
})();
(function(){  // hour by hour: one table at a time, chosen by the wall picker and the day tabs; without script every table shows
  var box=document.getElementById('hbs');
  if(!box){return;}
  var panels=[].slice.call(box.querySelectorAll('details.hb')), sel=document.getElementById('hb-wall'),
      tabs=[].slice.call(box.querySelectorAll('[role=tab]')), w=+box.getAttribute('data-w'), d=0;
  function draw(){
    panels.forEach(function(p){var on=+p.getAttribute('data-w')===w&&+p.getAttribute('data-d')===d;p.hidden=!on;if(on){p.open=true;}});
    tabs.forEach(function(t,i){t.setAttribute('aria-selected',i===d?'true':'false');t.tabIndex=i===d?0:-1;t.setAttribute('aria-controls','hb-'+w+'-'+i);});
  }
  panels.forEach(function(p){p.setAttribute('role','tabpanel');p.setAttribute('aria-labelledby','hb-t'+p.getAttribute('data-d'));});
  if(sel){sel.value=String(w);sel.addEventListener('change',function(){w=+sel.value;draw();});}
  tabs.forEach(function(t,i){
    t.addEventListener('click',function(){d=i;draw();});
    t.addEventListener('keydown',function(e){
      var k=e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0;
      if(!k){return;}
      e.preventDefault();d=(d+k+tabs.length)%tabs.length;draw();tabs[d].focus();
    });
  });
  document.querySelectorAll('details.wall').forEach(function(x,i){x.addEventListener('toggle',function(){if(x.open&&sel){w=i;sel.value=String(i);draw();}});});
  box.classList.add('js');document.getElementById('hb-ctl').hidden=false;draw();
})();
"""


def render_detail(gname, walls, tides, now, today, cfg, view, here, logged, nxt=None):
    """The conditions page for one crag. Title block; then, beside each other from 900 px (stacked on phones, in this order): the walls
    list, How sure and Across the crag; the wall cards (one <details> each on multi-wall crags, the best wall open), hour by hour,
    the days logged here and the sources line.
    view: coast_view() for the first strip; nxt: next_view() for the second; here: zone_now(); logged: logged_days()."""
    day, tomorrow, now_hour, _rows, cols = view
    di = day.isoformat()
    nday, ncols = nxt if nxt else (day + timedelta(days=1), [])
    days = [day, nday]
    labels = ["Tomorrow", "Day after"] if tomorrow else ["Today", "Tomorrow"]
    multi = len(walls) > 1
    zones = cfg["zones"]
    c0 = walls[0]["crag"]
    zone = zones[c0["zone"]]
    zn = here.get(c0["zone"], {})
    ids = wall_ids(walls)
    best = open_wall(walls, di)
    out = []
    w = out.append
    w('<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    w(f"<title>{escape(gname)}: Grip conditions</title>")
    w(fonts("../"))
    w(icon_links("../"))
    w(f'<style>{CSS}{COAST_CSS}{DETAIL_CSS}</style></head><body>{header_bar("../")}<main class="crag" data-open="{ids[best]}">')
    w(f'<nav class="crumb" aria-label="Breadcrumb"><a href="../">Forecast</a> / {escape(zone["name"])}</nav>')
    w(f'<div class="tb"><div><h1>{escape(gname)}</h1>')
    w(f'<p class="meta">{len(walls)} wall{"s" if multi else ""} &middot; Weather from the {escape(zone["name"])} point &middot; '
      f'Updated {now.strftime("%a %-d %b, %H:%M")}</p></div>')
    log_c = c0 if not multi else {"name": gname}
    w(f'<p class="acts"><a class="btn" href="{escape(log_link(log_c, today.isoformat(), "../"))}">Log a day here</a>'
      f'<a class="btn alt" href="{escape(note_link(log_c))}" target="_blank" rel="noopener">Send a crag note</a></p></div>')
    w('<div class="cols"><div class="side">')

    if multi:
        w('<section class="box wlist" aria-labelledby="walls-h"><div class="wh"><h2 id="walls-h">Walls</h2>'
          f'<span class="ovl" aria-hidden="true">{"Tmrw" if tomorrow else "Today"}</span><span class="ovl" aria-hidden="true">{"Day after" if tomorrow else "Tmrw"}</span></div><ul>')
        for i, r in enumerate(walls):
            c = r["crag"]
            cur = ' aria-current="true"' if i == best else ""
            w(f'<li><a href="#{ids[i]}"{cur}><span class="wn">{escape(wall_name(c))}<small>{escape(wall_sub(c))}</small></span>'
              + "".join(score_block(r["daily"].get(d.isoformat()), "sz-m", lab) for d, lab in zip(days, labels)) + "</a></li>")
        w("</ul></section>")

    sure = sure_items(walls, days, today)
    w('<section class="box sure" aria-labelledby="sure-h"><h2 id="sure-h">How sure</h2>')
    if not sure:
        w(f'<p>{labels[0]} and {labels[1].lower()} the three models agree{" on every wall" if multi else ""}, within 2 points.</p>')
    else:
        last = None
        for r, d, said in sure:
            if multi and r is not last:
                w(f'<h3>{escape(wall_name(r["crag"]))}</h3>')
                last = r
            w(f'<p><b>{labels[days.index(d)]}:</b> {escape(said)}</p>')
    w("</section>")

    across, per_wall = across_facts(walls, zone, zn, tides, days, labels)
    w('<section class="box across" aria-labelledby="across-h"><h2 id="across-h">Across the crag</h2><dl>')
    for head, text in across:
        w(f"<dt>{escape(head)}</dt><dd>{escape(text)}</dd>")
    rain = zn.get("rain")
    src = f"{escape(rain[0])} figures, to {now.strftime('%H')}:00." if rain else ""
    w(f'</dl><p class="fn">{src}</p></section>' if src else "</dl></section>")
    w('</div><div class="body">')
    if multi:
        w(f'<p class="hint wl-hint">Open a wall for its strips, reasons and week. Scores are {labels[0].lower()}, then {"the day after" if tomorrow else "tomorrow"}.</p>')

    for i, r in enumerate(walls):
        c = r["crag"]
        tags = "".join(('<li class="in">' if t == "Birds nesting now" else "<li>") + escape(t) + "</li>" for t in wall_tags(c, days))
        blocks = "".join(score_block(r["daily"].get(d.isoformat()), "sz-m", lab) for d, lab in zip(days, labels))
        sub = escape(wall_sub(c))
        if multi:
            w(f'<details class="wall" id="{ids[i]}" open><summary><h2>{escape(wall_name(c))}<small>{sub}</small></h2>'
              f'<span class="sb">{blocks}</span><span class="mk" aria-hidden="true"></span></summary><div class="wb">')
        else:
            w(f'<article class="wall" id="{ids[i]}" aria-labelledby="{ids[i]}-h"><div class="wb"><h2 id="{ids[i]}-h">{escape(wall_name(c) if c.get("wall") else gname)}</h2>')
        lg = f'<a class="lg" href="{escape(log_link(c, today.isoformat(), "../"))}">Log a day on this wall</a>' if multi else ""
        w(f'<div class="tr"><ul class="tags" aria-label="About this wall">{tags}</ul>{lg}</div>')
        hs = day_hours(r, di)
        vals = {hour_of(hr): hr["index"] for hr in hs}
        w(f'<div class="today"><div class="dayline"><h3>{labels[0]}, {day.strftime("%a %-d")}</h3>'
          f'<p class="line">{escape(plain_line(hs, now_hour, tomorrow))}</p></div>'
          + (strip_html(cols, vals, now_hour) + hours_head(cols) if cols else "") + "</div>")
        nhs = day_hours(r, nday.isoformat())
        nvals = {hour_of(hr): hr["index"] for hr in nhs}
        w(f'<div class="today next"><div class="dayline"><h3>{labels[1]}, {nday.strftime("%a %-d")}</h3>'
          f'<p class="line">{escape(plain_line(nhs, None, True))}</p></div>'
          + (strip_html(ncols, nvals, -1) + hours_head(ncols) if ncols else "") + "</div>")
        w(f'<div class="why"><h3>Why</h3><p>{escape(why_text(hs, now_hour, tomorrow))}</p></div>')
        w(f'<h3>What shapes this {"wall" if multi else "crag"}</h3><dl>')
        for head, text in per_wall[i] + shapes_items(c, zones[c["zone"]], day, labels[0].lower(), zn.get("sea")):
            w(f"<dt>{escape(head)}</dt><dd>{escape(text)}</dd>")
        w("</dl>")
        w(f'<h3>Next 7 days</h3>{week_html(r, today)}')
        w("</div></details>" if multi else "</div></article>")

    # hour by hour: the next three days, as before; one table per wall and day
    hb_days = sorted({hr["t"][:10] for r in walls for hr in r["hours"] if date.fromisoformat(hr["t"][:10]) <= today + timedelta(days=2)})
    w(f'<section class="hbs" id="hbs" data-w="{best}" aria-labelledby="hour-by-hour"><h2 id="hour-by-hour">Hour by hour</h2>'
      '<p class="hint">Grip is the blend of the three models. The points column shows the Met Office figures (the next model\'s where it '
      "does not reach), factors at zero left out. Wet risk is how many models have the rock wet, foggy or raining.</p>")
    w('<div class="hbc" id="hb-ctl" hidden>')
    if multi:
        w('<label for="hb-wall">Wall<select id="hb-wall">' + "".join(f'<option value="{i}">{escape(wall_name(r["crag"]))}</option>' for i, r in enumerate(walls))
          + "</select></label>")
    w('<div class="tabs" role="tablist" aria-label="Day">' + "".join(
        f'<button type="button" role="tab" id="hb-t{j}" aria-selected="false">{date.fromisoformat(d).strftime("%a %-d")}</button>'
        for j, d in enumerate(hb_days)) + "</div></div>")
    for i, r in enumerate(walls):
        for j, d in enumerate(hb_days):
            hs = [hr for hr in r["hours"] if hr["t"][:10] == d]
            lt = tides.get(r["crag"]["zone"], {}).get(d, [])
            dd = date.fromisoformat(d)
            cap = dd.strftime("%A %-d %B") + (f" · low water {', '.join(lt)}" if lt else "")
            name = (wall_name(r["crag"]) + ", " if multi else "") + dd.strftime("%a %-d %b")
            w(f'<details class="hb" id="hb-{i}-{j}" data-w="{i}" data-d="{j}" open><summary>{escape(name)}</summary>')
            if hs:
                w(f'<div class="wrap" tabindex="0" role="region" aria-label="{escape(name)}, hour by hour">{hours_table(hs, cap)}</div>')
            else:
                w('<p class="sub">No hours scored.</p>')
            w("</details>")
    w('<p class="sub fn">Models: Met Office, ECMWF, ICON, in that order.</p></section>')

    w('<section aria-labelledby="logged-h"><h2 id="logged-h">Logged days here</h2>')
    mine = [(v, c) for v, c in logged if c is not None and c["name"] == gname]
    if not mine:
        w(f'<p>No days logged here yet. Climbed here? <a href="{escape(log_link(log_c, today.isoformat(), "../"))}">Log a day</a>.</p>')
    else:
        def chip(x):
            if x is None:
                return "-"
            return f'<span class="num sz-s {band(x)[2]}">{fmt(x)}</span>'
        w('<div class="wrap" tabindex="0" role="region" aria-label="Logged days here"><table class="cal"><tr><th>Date</th><th>Wall</th><th>Felt</th><th>Grip said</th><th>Actual weather</th></tr>')
        for v, c in mine:
            n = f' <small>({v["n_logs"]} logs)</small>' if v.get("n_logs", 1) > 1 else ""
            w(f'<tr><td>{date.fromisoformat(v["date"]).strftime("%-d %b %Y")}</td><td>{escape(wall_name(c))}{n}</td>'
              f'<td>{escape(FEEL_NAME[v["feel"]])}</td><td>{chip(v["grip"])} {band(v["grip"])[0]}</td><td>{chip(v.get("era"))}</td></tr>')
        w("</table></div>")
    w("</section>")
    w(f'<p class="foot">Crag facts from the <a href="https://routes.smc.org.uk/crag/{int(c0["smc_crag_id"])}">SMC routes database</a>, '
      "climbers' reports and local developers' notes, reworded by Grip.</p>")
    w(f"</div></div><script>{CRAG_JS}</script></main>{site_foot('../')}</body></html>")
    return "".join(out)


BIRDS_CSS = """
.updated{color:var(--ink);font-size:var(--t-body);max-width:64ch}
.legend{display:flex;flex-wrap:wrap;gap:var(--s-6) 18px;margin:0 0 var(--s-16);font-size:var(--t-small);color:var(--muted);max-width:60rem}
.legend>span{display:inline-flex;align-items:center;gap:var(--s-6)}
.birds{font-size:var(--t-meta)}
.birds td,.birds th{padding:var(--s-8) var(--s-12);border-bottom:1px solid var(--rule);text-align:left;vertical-align:middle}
.birds tr:first-child th{font:500 var(--t-small)/1.2 var(--font-display);text-transform:uppercase;letter-spacing:var(--overline-tracking);color:var(--muted)}
.birds tr.zone th{padding:var(--s-20) var(--s-12) var(--s-6);font:600 15px/1.2 var(--font-display);text-transform:uppercase;letter-spacing:var(--overline-tracking);color:var(--muted)}
.birds td:first-child{font-size:var(--t-body);font-weight:600;line-height:1.2;min-width:10rem}
.birds td:first-child small{display:block;font-weight:400;color:var(--muted);font-size:var(--t-small)}
.birds td.note{min-width:16rem;max-width:28rem}
.birds tr.unk td{background:var(--sunk)}
.tag{display:inline-flex;align-items:center;gap:var(--s-4);min-height:26px;padding:var(--s-2) 9px;border-radius:5px;font-size:var(--t-small);font-weight:600;line-height:1.2;white-space:nowrap;color:var(--ink)}
.tag i{font-style:normal}
.t-res{background:var(--inv-bg);color:var(--inv-fg)}
.t-nest{box-shadow:inset 0 0 0 1.5px var(--ink)}
.t-pos{border:1.5px dotted var(--ink)}
.t-free{background:var(--sunk);box-shadow:inset 0 0 0 1px var(--rule);font-weight:500}
.t-unk{border:1px dashed var(--muted);background:var(--card)}
.mcell{display:inline-block;vertical-align:middle}
.mbar,.mini{display:grid;grid-template-columns:repeat(12,14px);gap:2px}
.mbar i{display:block;position:relative;height:14px;border-radius:2px;box-shadow:inset 0 0 0 1px var(--rule)}
.mbar i.n{background:var(--ink);box-shadow:none}
.mbar i.p{background:repeating-linear-gradient(135deg,var(--ink) 0 1.5px,transparent 1.5px 4.5px);box-shadow:inset 0 0 0 1.5px var(--ink)}
.mbar i.now{box-shadow:inset 0 -3px 0 var(--ink),inset 0 0 0 1px var(--rule)}
.mbar i.p.now{box-shadow:inset 0 -3px 0 var(--ink),inset 0 0 0 1.5px var(--ink)}
.mbar i.n.now{box-shadow:inset 0 -3px 0 var(--paper)}
.mini{margin:var(--s-2) 0 0;font:500 10px/1 var(--font-display);color:var(--muted);text-align:center}
.mt{display:block;margin:var(--s-4) 0 0;font-size:var(--t-small);color:var(--muted)}
.legend .mbar{display:inline-grid;grid-template-columns:14px}
.conf{display:inline-flex;align-items:center;gap:var(--s-6);font-size:15px;font-weight:600}
.conf i{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;font:700 11px/1 var(--font-body);font-style:normal}
.conf i.yes{background:var(--ink)}
.conf i.yes::before{content:"";width:4px;height:9px;margin-top:-2px;border:solid var(--paper);border-width:0 2px 2px 0;transform:rotate(45deg)}
.conf i.no{box-shadow:inset 0 0 0 1.5px var(--ink)}
"""


MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


BIRD_TAG = {"restricted": "t-res", "affected": "t-nest", "clear": "t-free", "possible": "t-pos"}  # status tags, ink only, each a different shape


def month_bar(months, confirmed, this_month):
    """Twelve squares, January to December: nesting months solid ink once confirmed, hatched while they are a placeholder,
    the rest outlined; this month underlined. Then the initials and the months as text."""
    kind = "n" if confirmed else "p"

    def cell(m):
        cls = " ".join(x for x in (kind if m in months else "", "now" if m == this_month else "") if x)
        return f'<i class="{cls}"></i>' if cls else "<i></i>"
    cells = "".join(cell(m) for m in range(1, 13))
    said = f"Nesting {MONTHS[min(months)]} to {MONTHS[max(months)]}" + ("" if confirmed else ", months not confirmed")
    return (f'<span class="mcell"><span class="mbar" role="img" aria-label="{said}">{cells}</span>'
            '<span class="mini" aria-hidden="true">' + "".join(f"<span>{MONTHS[m][0]}</span>" for m in range(1, 13)) + "</span>"
            f'<span class="mt">{MONTHS[min(months)][:3]} to {MONTHS[max(months)][:3]}</span></span>')


def render_birds(cfg, now):
    """A register of nesting-bird status for every crag, with months, source and whether anyone has confirmed it."""
    out = []
    w = out.append
    w('<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    w("<title>Grip: nesting birds by crag</title>")
    w(fonts())
    w(icon_links())
    w(f"<style>{CSS}{BIRDS_CSS}</style></head><body>{header_bar(current='birds')}<main>")
    w("<h1>Nesting birds by crag</h1>")
    w(f'<p class="updated">Status, months and source for every crag Grip covers. In season the forecast marks the crag but does not mark it down. '
      f'Most entries come from keyword matching on the SMC routes database and UKC, with the months a placeholder until someone confirms them. '
      f'If you know better, <a href="{NOTES_URL}" target="_blank" rel="noopener">send a crag note</a>. Updated {now.strftime("%a %-d %b, %H:%M")}.</p>')
    groups = []
    for c in cfg["crags"]:
        key = (c.get("section") or "", c["name"])
        if not groups or groups[-1][0] != key:
            groups.append((key, []))
        groups[-1][1].append(c)
    cur_sec = None
    unknown = '<span class="tag t-unk"><i aria-hidden="true">?</i>No information</span>'
    w('<div class="legend" role="note" aria-label="Key"><span><span class="mbar" aria-hidden="true"><i class="n"></i></span>Nesting month, confirmed</span>'
      '<span><span class="mbar" aria-hidden="true"><i class="p"></i></span>Nesting month, a placeholder until someone confirms it</span>'
      '<span><span class="mbar" aria-hidden="true"><i></i></span>Other months</span>'
      '<span><span class="mbar" aria-hidden="true"><i class="now"></i></span>This month</span>'
      f'<span>{unknown} Unknown. Not the same as bird free.</span></div>')
    w('<div class="wrap"><table class="birds"><tr><th>Crag</th><th>Status</th><th>Months</th><th>Note</th><th>Confirmed</th></tr>')
    for (sec, name), walls in groups:
        if sec != cur_sec:
            w(f'<tr class="zone"><th colspan="5">{escape(sec)}</th></tr>')
            cur_sec = sec
        seen = set()
        rows = []
        for c in walls:
            b = c.get("birds")
            key = json.dumps(b, sort_keys=True) if b else None
            if key in seen:
                continue
            seen.add(key)
            rows.append((c, b))
        for c, b in rows:
            wall = f' <small>{escape(c["wall"])}</small>' if c.get("wall") and len(rows) > 1 else ""
            if not b:
                w(f'<tr class="unk"><td>{escape(c["name"])}{wall}</td><td>{unknown}</td><td>-</td><td class="note"></td><td>-</td></tr>')
                continue
            months = b.get("months") or []
            span = month_bar(set(months), b.get("confirmed"), now.month) if months else "-"
            level = {"restricted": "Restricted", "affected": "Nesting birds", "clear": "Bird free", "possible": "Possible"}.get(b.get("level"), b.get("level", ""))
            tag = f'<span class="tag {BIRD_TAG.get(b.get("level"), "t-nest")}">{escape(level)}</span>'
            conf = ('<span class="conf"><i class="yes" aria-hidden="true"></i>Yes</span>' if b.get("confirmed")
                    else '<span class="conf"><i class="no" aria-hidden="true">?</i>No</span>')
            w(f'<tr><td>{escape(c["name"])}{wall}</td><td>{tag}</td><td>{span}</td><td class="note">{escape(b.get("note", ""))}</td><td>{conf}</td></tr>')
    w(f"</table></div></main>{site_foot()}</body></html>")
    return "".join(out)


LOG_CSS = """
.logform{max-width:680px}
.field{margin:0 0 var(--s-24);padding:0;border:0;min-width:0}
.field>label,.field legend{display:block;font-weight:600;margin:0 0 var(--s-4);padding:0}
.desc{color:var(--muted);font-size:var(--t-meta);margin:0 0 var(--s-8)}
.req{color:var(--ink)}
.logform input[type=text],.logform input[type=date],.logform input[type=time],.logform textarea{display:block;width:100%;min-height:48px;font:inherit;font-size:16px;padding:var(--s-8) var(--s-12);border:1px solid var(--rule);border-radius:var(--r-m);background:var(--card);color:var(--ink)}
.updated{color:var(--ink);font-size:var(--t-body);max-width:56ch}
.logform textarea{min-height:96px;resize:vertical}
.logform input:focus,.logform input:focus-within,.logform textarea:focus{outline:2px solid transparent;border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink),var(--focus-ring)}
.pair{display:flex;flex-wrap:wrap;gap:0 var(--s-12)}
.pair .field{flex:1 1 90px}
.pair #f-date{flex-basis:150px}
.combo{position:relative}
.combo ul{position:absolute;left:0;right:0;top:100%;z-index:5;margin:var(--s-4) 0 0;padding:0;list-style:none;max-height:min(20rem,45vh);overflow-y:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;background:var(--card);border:1px solid var(--rule);border-radius:var(--r-m);box-shadow:var(--shadow-overlay)}
.combo li{display:flex;align-items:center;min-height:var(--tap);padding:var(--s-8) var(--s-12);cursor:pointer;border-bottom:1px solid var(--rule)}
.combo li:last-child{border-bottom:0}
@media (hover:hover){.combo li:hover{background:var(--sunk)}}
.combo li[aria-selected=true]{background:var(--inv-bg);color:var(--inv-fg)}
.combo li.none{cursor:default;color:var(--muted)}
.field>label.tile{display:block;position:relative;margin:0 0 var(--s-6);font-weight:400;cursor:pointer}
.tile input,.pchip input{position:absolute;top:0;left:0;width:1px;height:1px;margin:0;opacity:0}
.tile .tb{display:flex;align-items:center;gap:var(--s-12);min-height:52px;padding:var(--s-4) var(--s-12) var(--s-4) var(--s-4);background:var(--card);border-radius:var(--r-m);box-shadow:inset 0 0 0 1px var(--rule)}
.tile .tb::after{content:"";flex:none;margin-left:auto;width:22px;height:22px;border-radius:50%;box-shadow:inset 0 0 0 2px var(--ink)}
.tile .kc{min-width:var(--score-l);height:var(--score-l);font-size:15px;border-radius:var(--r-s)}
.tile .fn{display:block;font-size:var(--t-lead);font-weight:600;line-height:1.2}
.tile .fd{display:block;color:var(--muted);font-size:var(--t-meta);line-height:1.3}
.tile input:checked+.tb{box-shadow:inset 0 0 0 2px var(--ink)}
.tile input:checked+.tb::after{box-shadow:inset 0 0 0 2px var(--ink);background:radial-gradient(circle,var(--ink) 0 5px,transparent 5.5px)}
.tile input:focus-visible+.tb{box-shadow:inset 0 0 0 1px var(--rule),var(--focus-ring)}
.tile input:checked:focus-visible+.tb{box-shadow:inset 0 0 0 2px var(--ink),var(--focus-ring)}
@media (hover:hover){.tile:hover .tb{background:var(--sunk)}}
.chips{display:flex;flex-wrap:wrap;gap:var(--s-8)}
.pchip{position:relative;display:inline-block;cursor:pointer}
.pchip span{position:relative;display:inline-flex;align-items:center;gap:var(--s-8);min-height:var(--tap);padding:var(--s-6) 14px var(--s-6) 10px;border-radius:var(--r-pill);background:var(--card);box-shadow:inset 0 0 0 1px var(--rule);font-size:15px;line-height:1.2}
.pchip span::before{content:"";flex:none;width:18px;height:18px;border:2px solid currentColor;border-radius:var(--r-xs)}
.pchip input:checked+span{background:var(--inv-bg);color:var(--inv-fg);box-shadow:inset 0 0 0 1px var(--ink)}
.pchip input:checked+span::after{content:"";position:absolute;left:17px;top:50%;width:5px;height:10px;margin-top:-7px;border:solid currentColor;border-width:0 2px 2px 0;transform:rotate(45deg)}
.pchip input:focus-visible+span{box-shadow:inset 0 0 0 1px var(--rule),var(--focus-ring)}
.pchip input:checked:focus-visible+span{box-shadow:inset 0 0 0 1px var(--ink),var(--focus-ring)}
@media (hover:hover){.pchip:hover input:not(:checked)+span{background:var(--sunk)}}
.err{color:var(--ink);font-size:var(--t-meta);font-weight:600;margin:var(--s-6) 0 0}
.err:empty{display:none}
.bad input[type=text],.bad input[type=date],.bad input[type=time]{border-color:var(--ink);box-shadow:inset 0 0 0 1px var(--ink)}
.bad .tb{box-shadow:inset 0 0 0 1px var(--ink)}
button.btn{min-height:52px;width:100%;max-width:320px;margin:0;font-size:18px}
button.btn:disabled{background:var(--past);color:var(--past-ink);cursor:default;opacity:1}
#done h2{margin-top:var(--s-24)}
.foot{color:var(--muted);font-size:var(--t-meta);margin-top:var(--s-32)}
"""

LOG_JS = r"""
var GripLog=(function(){
  var WALLS=__WALLS__;  // [label shown, crag sent to the form, wall sent to the form], coast order, "Somewhere else" last
  var E=__ENTRIES__;
  var POST=__POST__;
  var norm=GripMatch.norm;
  var KEYS=WALLS.map(function(w){return GripMatch.key(w[0]);});
  function filter(q){  // indices of the walls whose label has every typed word at the start of one of its words; "Somewhere else" always last
    var test=GripMatch.matcher(q), out=[], last=WALLS.length-1;
    for(var i=0;i<last;i++){
      if(test(KEYS[i])){out.push(i);}
    }
    out.push(last);
    return out;
  }
  function find(v){  // index of the wall whose label is v, exactly or apart from case and punctuation; -1 if none
    if(!v){return -1;}
    for(var i=0;i<WALLS.length;i++){if(WALLS[i][0]===v){return i;}}
    var n=norm(v), hit=-1;
    for(var j=0;j<WALLS.length;j++){if(KEYS[j]===' '+n){if(hit>=0){return -1;} hit=j;}}
    return hit;
  }
  function today(){var d=new Date();return d.getFullYear()+'-'+('0'+(d.getMonth()+1)).slice(-2)+'-'+('0'+d.getDate()).slice(-2);}
  function validate(f, now){  // f: {wall: index or -1, date, from, until, feel, ...}; returns [[field, message], ...]
    var bad=[];
    if(!(f.wall>=0&&f.wall<WALLS.length)){bad.push(['wall','Pick a crag and wall from the list.']);}
    if(!/^\d{4}-\d{2}-\d{2}$/.test(f.date||'')){bad.push(['date','Enter the date.']);}
    else if(f.date>(now||today())){bad.push(['date','The date cannot be in the future.']);}
    var t=/^\d{2}:\d{2}/;
    if(!t.test(f.from||'')){bad.push(['from','Enter when you got on the rock.']);}
    if(!t.test(f.until||'')){bad.push(['until','Enter when you came off the rock.']);}
    else if(t.test(f.from||'')&&f.until.slice(0,5)<=f.from.slice(0,5)){bad.push(['until','This must be later than the start time.']);}
    if(!f.feel){bad.push(['feel','Choose how the rock felt.']);}
    return bad;
  }
  function payload(f){  // the form-urlencoded body for the Google Form
    var p=new URLSearchParams(), w=WALLS[f.wall], d=f.date.split('-'), a=f.from.split(':'), b=f.until.split(':');
    p.append(E.crag,w[1]);
    p.append(E.wall,w[2]);
    p.append(E.date+'_year',d[0]);p.append(E.date+'_month',d[1]);p.append(E.date+'_day',d[2]);
    p.append(E.from+'_hour',a[0]);p.append(E.from+'_minute',a[1]);
    p.append(E.until+'_hour',b[0]);p.append(E.until+'_minute',b[1]);
    p.append(E.feel,f.feel);
    (f.problems||[]).forEach(function(x){p.append(E.problems,x);});
    p.append(E.initials,(f.initials||'').trim());
    p.append(E.other,(f.other||'').trim());
    p.append(E.contact,(f.contact||'').trim());
    p.append('fvv','1');
    p.append('pageHistory','0');
    return p;
  }
  return {WALLS:WALLS,POST:POST,norm:norm,filter:filter,find:find,today:today,validate:validate,payload:payload};
})();
if(typeof document!=='undefined'){(function(){
  var G=GripLog, W=G.WALLS;
  function $(id){return document.getElementById(id);}
  var form=$('logform'), input=$('wall'), list=$('wall-list'), combo=input.parentNode, chosen=-1, shown=[], active=-1;
  function isOpen(){return !list.hidden;}
  function draw(){
    shown=G.filter(input.value);
    var html=[];
    if(shown.length===1&&input.value.trim()){html.push('<li class="none" aria-disabled="true">No wall matches. Try fewer letters, or:</li>');}
    shown.forEach(function(wi,k){
      var li='<li role="option" id="opt-'+k+'" data-k="'+k+'"'+(k===active?' aria-selected="true"':'')+'></li>';
      html.push(li);
    });
    list.innerHTML=html.join('');
    list.querySelectorAll('li[role=option]').forEach(function(li){li.textContent=W[shown[+li.dataset.k]][0];});
    if(active>=0){input.setAttribute('aria-activedescendant','opt-'+active);var el=$('opt-'+active);if(el&&el.scrollIntoView){el.scrollIntoView({block:'nearest'});}}
    else{input.removeAttribute('aria-activedescendant');}
  }
  function open(){draw();list.hidden=false;input.setAttribute('aria-expanded','true');}
  function close(){list.hidden=true;active=-1;input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');}
  function choose(wi){chosen=wi;input.value=W[wi][0];close();mark('wall','');}
  function mark(field,msg){
    var box=$('f-'+field), err=$(field+'-err');
    if(err){err.textContent=msg;}
    if(box){box.classList.toggle('bad',!!msg);}
  }
  input.addEventListener('input',function(){chosen=G.find(input.value);active=-1;open();});
  input.addEventListener('focus',function(){open();});
  input.addEventListener('click',function(){if(!isOpen()){open();}});
  input.addEventListener('change',function(){var i=G.find(input.value);if(i>=0){chosen=i;input.value=W[i][0];}});
  input.addEventListener('keydown',function(e){
    var k=e.key;
    if(k==='ArrowDown'||k==='Down'){e.preventDefault();if(!isOpen()){open();}active=Math.min(active+1,shown.length-1);draw();}
    else if(k==='ArrowUp'||k==='Up'){e.preventDefault();if(isOpen()){active=Math.max(active-1,0);draw();}}
    else if(k==='Enter'){e.preventDefault();if(isOpen()&&active>=0){choose(shown[active]);}else if(isOpen()&&shown.length===2&&input.value.trim()){choose(shown[0]);}}
    else if(k==='Escape'||k==='Esc'){if(isOpen()){e.preventDefault();close();}}
    else if(k==='Tab'){close();}
  });
  list.addEventListener('mousedown',function(e){e.preventDefault();});  // keep focus in the box while picking
  list.addEventListener('click',function(e){
    var li=e.target.closest?e.target.closest('li[role=option]'):null;
    if(li){choose(shown[+li.dataset.k]);}
  });
  document.addEventListener('pointerdown',function(e){if(isOpen()&&!combo.contains(e.target)){close();}});

  var dt=$('date');
  dt.max=G.today();
  var q=new URLSearchParams(location.search);
  if(q.get('wall')){var i=G.find(q.get('wall'));if(i>=0){chosen=i;input.value=W[i][0];}else{input.value=q.get('wall');}}
  if(/^\d{4}-\d{2}-\d{2}$/.test(q.get('date')||'')){dt.value=q.get('date');}

  function values(){
    var feel=form.querySelector('input[name=feel]:checked');
    return {wall:chosen>=0&&input.value===W[chosen][0]?chosen:G.find(input.value), date:dt.value, from:$('from').value, until:$('until').value,
      feel:feel?feel.value:'', problems:[].map.call(form.querySelectorAll('input[name=problems]:checked'),function(x){return x.value;}),
      initials:$('initials').value, other:$('other').value, contact:$('contact').value};
  }
  form.addEventListener('submit',function(e){
    e.preventDefault();
    var f=values(), bad=G.validate(f), send=$('send');
    ['wall','date','from','until','feel'].forEach(function(x){mark(x,'');});
    $('form-err').textContent='';
    bad.forEach(function(b){mark(b[0],b[1]);});
    if(bad.length){
      $('form-err').textContent='Please check the '+(bad.length===1?'field':bad.length+' fields')+' marked above.';
      var first=bad[0][0]==='feel'?form.querySelector('input[name=feel]'):$(bad[0][0]);
      if(first){first.focus();}
      return;
    }
    input.value=W[f.wall][0];
    send.disabled=true;send.textContent='Sending...';
    fetch(G.POST,{method:'POST',mode:'no-cors',body:G.payload(f)}).then(function(){
      form.hidden=true;$('done').hidden=false;$('foot').hidden=true;window.scrollTo(0,0);
    }).catch(function(){
      send.disabled=false;send.textContent='Send';
      $('form-err').textContent='It did not send. Check your connection and try again.';
    });
  });
})();}
"""


def form_walls(cfg):
    """Every wall as the page log form offers it, in coast order: [label, crag sent to the Google Form, wall sent].
    A crag missing from the form's options goes in as "Somewhere else on the coast" with the full label as the wall."""
    try:
        with open(FORM_CRAGS_FILE) as f:
            known = set(json.load(f))
    except Exception as e:  # noqa: BLE001
        log(f"Warning: cannot read data/form_crags.json ({e}); every log will go in as '{FORM_ELSEWHERE}'")
        known = set()
    out, missing = [], []
    for c in cfg["crags"]:
        if c["name"] in known:
            out.append([label(c), c["name"], c.get("wall") or ""])
        else:
            out.append([label(c), FORM_ELSEWHERE, label(c)])
            if c["name"] not in missing:
                missing.append(c["name"])
    if missing:
        log(f"Warning: {len(missing)} crag(s) not in data/form_crags.json, logged as '{FORM_ELSEWHERE}' with the label as the wall: {', '.join(missing)}")
    if known and FORM_ELSEWHERE not in known:
        log(f"Warning: '{FORM_ELSEWHERE}' is not in data/form_crags.json")
    out.append([FORM_ELSEWHERE, FORM_ELSEWHERE, ""])
    return out


def js(x):
    """A value as a JavaScript literal, safe inside a script element."""
    return json.dumps(x, ensure_ascii=False).replace("</", "<\\/")


def render_log(cfg):
    """The log form: a searchable crag and wall box that submits into the Google Form, so the responses sheet is unchanged."""
    script = MATCH_JS + (LOG_JS.replace("__WALLS__", js(form_walls(cfg))).replace("__ENTRIES__", js(FORM_ENTRIES))
                         .replace("__POST__", js(FORM_POST)))
    req = '<span class="req" aria-hidden="true"> *</span>'
    out = []
    w = out.append
    w('<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    w("<title>Grip: log a day on the rock</title>")
    w(fonts())
    w(icon_links())
    w(f"<style>{CSS}{LOG_CSS}</style></head><body>{header_bar(current='contribute')}<main>")
    w("<h1>Log a day on the rock</h1>")
    w('<p class="updated">How did the rock actually feel? Your answers calibrate the Grip forecast. Anonymous, no account needed. One entry per crag per visit.</p>')
    w('<p class="updated">Score the crag as a whole: how most of the rock felt across your time on it. Not your best route or your worst. '
      'If one route or patch stood out, say so under &quot;Anything else about the day?&quot;</p>')
    w(f'<noscript><p>This form needs JavaScript. <a href="{FORM_URL}">Use the Google form</a> instead.</p></noscript>')
    w('<form id="logform" class="logform" novalidate>')
    w(f'<div class="field" id="f-wall"><label for="wall" id="wall-label">Crag and wall{req}</label>'
      '<p class="desc" id="wall-desc">Type the start of any word in the name, then pick from the list.</p>'
      '<div class="combo"><input id="wall" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="wall-list" '
      'aria-describedby="wall-desc wall-err" aria-required="true" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false">'
      '<ul id="wall-list" role="listbox" aria-labelledby="wall-label" hidden></ul></div><p class="err" id="wall-err"></p></div>')
    w(f'<div class="pair"><div class="field" id="f-date"><label for="date">Date{req}</label><input id="date" type="date" required aria-describedby="date-err"><p class="err" id="date-err"></p></div>'
      f'<div class="field" id="f-from"><label for="from">On the rock from{req}</label><input id="from" type="time" step="60" required aria-describedby="from-err"><p class="err" id="from-err"></p></div>'
      f'<div class="field" id="f-until"><label for="until">On the rock until{req}</label><input id="until" type="time" step="60" required aria-describedby="until-err"><p class="err" id="until-err"></p></div></div>')
    w(f'<fieldset class="field" id="f-feel" aria-describedby="feel-desc feel-err"><legend>How did the rock feel overall?{req}</legend>'
      '<p class="desc" id="feel-desc">The crag as a whole, across your session. Not the best or worst route.</p>')
    ranges = {name: (css, rng) for _lo, name, _note, css, rng in BANDS}
    for i, v in enumerate(LOG_FEELS):  # one tile per band: its chip, then the option's own words, name and description
        name, desc = v.split(": ", 1)
        css, rng = ranges[name]
        w(f'<label class="tile"><input type="radio" name="feel" id="feel-{i}" value="{escape(v)}"><span class="tb">'
          f'<span class="kc {css}" aria-hidden="true">{rng}</span><span><span class="fn">{escape(name)}<span class="vh">:</span></span> '
          f'<span class="fd">{escape(desc)}</span></span></span></label>')
    w('<p class="err" id="feel-err"></p></fieldset>')
    w('<fieldset class="field"><legend>If it was poor, what was the problem? Tick any that apply.</legend><div class="chips">')
    for i, v in enumerate(LOG_PROBLEMS):
        w(f'<label class="pchip"><input type="checkbox" name="problems" id="prob-{i}" value="{escape(v)}"><span>{escape(v)}</span></label>')
    w("</div></fieldset>")
    w('<div class="field"><label for="initials">Initials</label><input id="initials" type="text" autocomplete="off"></div>')
    w('<div class="field"><label for="other">Anything else about the day?</label>'
      '<p class="desc" id="other-desc">For example: a route or patch much worse or better than the rest, wet to look at or just slick, worse near the sea, '
      'how the wind felt on the wall, whether it changed through the session</p><textarea id="other" aria-describedby="other-desc"></textarea></div>')
    w('<div class="field"><label for="contact">Happy to answer a follow-up question about this day?</label>'
      '<p class="desc" id="contact-desc">Leave a name and a way to reach you, WhatsApp number or email. Kept private, never published.</p>'
      '<input id="contact" type="text" aria-describedby="contact-desc"></div>')
    w('<p class="err" id="form-err" role="alert"></p><p><button type="submit" class="btn" id="send">Send</button></p></form>')
    w('<div id="done" hidden><h2>Logged, thank you</h2><p><a href="./">Back to the forecast</a></p></div>')
    w(f'<div id="foot"><p class="foot">Prefer the Google form? <a href="{FORM_URL}">Use it here.</a></p><p class="foot"><a href="./">Back to the forecast</a></p></div>')
    w(f"<script>{script}</script></main>{site_foot()}</body></html>")
    return "".join(out)


def strip_html(cols, vals, now_hour):
    """A row of hour blocks: the score as a whole number, coloured by band, earlier hours greyed, the current hour outlined.
    cols: the hours shown; vals: {hour: score}; now_hour: the current hour, or -1 when showing tomorrow."""
    out = []
    for h in cols:
        v = vals.get(h)
        if v is None:
            out.append("<span></span>")
            continue
        name, _note, css = band(v)
        when = "" if now_hour < 0 else "past" if h < now_hour else "now" if h == now_hour else ""
        out.append(f'<span role="img" class="{css}{" " + when if when else ""}" aria-label="{h:02d}:00, {when + ", " if when else ""}{name.lower()}, {rnd(v)}">{rnd(v)}</span>')
    return '<div class="strip">' + "".join(out) + "</div>"


def hours_head(cols):
    return '<div class="strip hrs" aria-hidden="true">' + "".join(f"<span>{h:02d}</span>" for h in cols) + "</div>"


def coast_view(results, now, cfg):
    """What the Coast panel, the popular crags table and the crag pages' Today strips share: (day, tomorrow, now_hour, rows, cols)."""
    day, tomorrow = coast_day(results, now)
    now_hour = -1 if tomorrow else now.hour
    rows = coast_rows(results, cfg["zones"], day.isoformat())
    cols = sorted({h for _z, _n, vals in rows for h in vals})
    return day, tomorrow, now_hour, rows, cols


def next_view(results, view):
    """The day after the one the Coast panel shows, for the second strip on the crag pages: (day, the hours scored that day)."""
    day = view[0] + timedelta(days=1)
    return day, sorted({hour_of(hr) for r in results for hr in day_hours(r, day.isoformat())})


def load_popular(cfg):
    """The popular crags from data/popular.json, in the file's order, keeping only names that match a crag in crags.json."""
    try:
        with open(POPULAR_FILE) as f:
            names = json.load(f)
    except Exception as e:  # noqa: BLE001
        log(f"Warning: cannot read data/popular.json ({e}); the popular crags table will be empty")
        return []
    known = {c["name"] for c in cfg["crags"]}
    missing = [n for n in names if n not in known]
    if missing:
        log(f"Warning: {len(missing)} name(s) in data/popular.json match no crag in crags.json: {', '.join(missing)}")
    return [n for n in names if n in known]


def popular_rows(groups, names, days):
    """One row per popular crag, (name, walls, [(best wall result, its daily entry) for each day]), sorted by the first day's
    score as shown, then its climbable hours, then the list order. A crag with no hours left that day sorts last."""
    by_name = dict(groups)
    rows = []
    for i, n in enumerate(names):
        if n in by_name:
            walls = by_name[n]
            rows.append((i, n, walls, [best_wall(walls, d.isoformat()) for d in days]))

    def key(row):
        d = row[3][0][1]
        return (-rnd(d["index"]) if d else 1, -d["usable"] if d else 1, row[0])
    return [(n, walls, cells) for _i, n, walls, cells in sorted(rows, key=key)]


def popular_cell(r, d, day_iso, tides):
    """One day of the popular crags table: the best wall's score in its band colour, best window and climbable hours,
    and low water when that wall is tidal."""
    if not d:
        return '<td class="pc" role="cell"><span class="sub">No daylight hours left</span></td>'
    name, _note, css = band(d["index"])
    lw = tides.get(r["crag"]["zone"], {}).get(day_iso, []) if r["crag"].get("tidal") else []
    return (f'<td class="pc" role="cell"><span class="num {css}">{fmt(d["index"])}</span><span class="vh"> {name},</span>'
            f'<span class="pw"><span class="w"><span class="vh">best </span>{d["start"]} to {d["end"]}</span>'
            f'<span class="h"><span class="dot"> &middot; </span>{d["usable"]} h<span class="vh"> climbable</span></span>'
            + (f'<small>Low water {", ".join(lw)}</small>' if lw else "") + "</span></td>")


def render_popular(results, tides, now, cfg):
    """The popular crags table: today and tomorrow side by side (tomorrow and the day after once today's daylight is over)."""
    day, tomorrow, _now_hour, _rows, _cols = coast_view(results, now, cfg)
    days = (day, day + timedelta(days=1))
    titles = ("Tomorrow", "Day after") if tomorrow else ("Today", "Tomorrow")
    rows = popular_rows(groups_of(results), load_popular(cfg), days)
    out = []
    w = out.append
    w('<section aria-labelledby="pop-h"><h2 id="pop-h">Popular crags</h2>'
      f'<p class="hint">The crags people climb most. Each day shows the crag\'s best wall: score, best window and climbable hours. '
      f'Sorted by {titles[0].lower()}\'s score. Tap a crag for its conditions page.</p>')
    if not rows:
        w('<p class="sub">No popular crags listed.</p></section>')
        return "".join(out)
    w('<div class="wrap popw"><table class="pop" role="table"><thead role="rowgroup"><tr role="row"><th scope="col" role="columnheader">Crag</th>'
      + "".join(f'<th scope="col" role="columnheader">{t} <small>{d.strftime("%a %-d %b")}</small></th>' for t, d in zip(titles, days))
      + '</tr></thead><tbody role="rowgroup">')  # the rows are laid out as a grid, so the table roles are stated outright
    for n, _walls, cells in rows:
        w(f'<tr role="row"><th scope="row" role="rowheader"><a href="detail/{slug(n)}.html">{escape(n)}</a></th>'
          + "".join(popular_cell(r, d, dd.isoformat(), tides) for (r, d), dd in zip(cells, days)) + "</tr>")
    w(f'</tbody></table><a class="all" href="#week-h">All {len(groups_of(results))} crags, next 7 days</a></div></section>')
    return "".join(out)


def render_coast(results, now, cfg):
    """The Along the coast panel: each weather point's walls, hour by hour, with a Today | Tomorrow switch.
    Both days are in the page; the switch shows one. After dark it starts on Tomorrow, and Today shows every hour as past.
    Without JavaScript the switch stays hidden and both days show, each under its own label."""
    _day, tomorrow, _now_hour, _rows, _cols = coast_view(results, now, cfg)
    today = now.date()
    panels = []
    for i, (title, day) in enumerate((("Today", today), ("Tomorrow", today + timedelta(days=1)))):
        rows = coast_rows(results, cfg["zones"], day.isoformat())
        cols = sorted({h for _z, _n, vals in rows for h in vals})
        now_hour = (99 if tomorrow else now.hour) if i == 0 else -1  # after dark every hour today is past
        panels.append((title, day, rows, cols, now_hour, (i == 1) == tomorrow))
    out = []
    w = out.append
    w('<section class="coast" id="coast" aria-labelledby="coast-h"><div class="ch"><h2 id="coast-h">Along the coast</h2>'
      '<div class="seg" role="radiogroup" aria-label="Day" hidden>')
    for i, (title, _day, _rows, _cols, _nh, on) in enumerate(panels):
        w(f'<button type="button" role="radio" aria-checked="{"true" if on else "false"}" tabindex="{0 if on else -1}" aria-controls="cp{i}">{title}</button>')
    w('</div></div><p class="hint">Typical score across the walls on each stretch, hour by hour. Earlier hours are greyed.</p>')
    for i, (title, day, rows, cols, now_hour, on) in enumerate(panels):
        w(f'<div class="cp" id="cp{i}" role="group" aria-label="{title}, {day.strftime("%a %-d %b")}">'
          f'<p class="ovl pday" aria-hidden="true">{title}, {day.strftime("%a %-d %b")}</p>')
        if not cols:
            w('<p class="sub">No hours scored.</p>')
        else:
            w(f'<div class="srow head"><span></span>{hours_head(cols)}</div>')
            for z, name, vals in rows:
                w(f'<div class="srow" role="group" aria-label="{escape(name)}"><span class="zn" aria-hidden="true">{escape(name)}</span>{strip_html(cols, vals, now_hour)}</div>')
        w("</div>")
    w("</section>")
    return "".join(out)


SWITCH_JS = r"""
(function(){  // the coast panel's Today | Tomorrow switch: a radio group, arrow keys move between the two
  var sec=document.getElementById('coast'), seg=sec&&sec.querySelector('.seg');
  if(!seg){return;}
  var btns=[].slice.call(seg.querySelectorAll('button'));
  function pick(b,focus){
    btns.forEach(function(x){var on=x===b;x.setAttribute('aria-checked',on?'true':'false');x.tabIndex=on?0:-1;
      document.getElementById(x.getAttribute('aria-controls')).hidden=!on;});
    if(focus){b.focus();}
  }
  btns.forEach(function(b,i){
    b.addEventListener('click',function(){pick(b);});
    b.addEventListener('keydown',function(e){
      var k=e.key, d=k==='ArrowRight'||k==='ArrowDown'||k==='Right'||k==='Down'?1:k==='ArrowLeft'||k==='ArrowUp'||k==='Left'||k==='Up'?-1:0;
      if(d){e.preventDefault();pick(btns[(i+d+btns.length)%btns.length],true);}
    });
  });
  sec.classList.add('js');seg.hidden=false;
  pick(btns.filter(function(b){return b.getAttribute('aria-checked')==='true';})[0]||btns[0]);
})();
"""

STALE_HOURS = 9  # the page warns when the newest run is more than this many hours old
SMALL_SAMPLE = 30  # under this many scored days, How sure leads with "Not very, yet." (the handbook's small-sample threshold)


def stale_age(run, now):
    """The age of a run in whole hours if it is more than STALE_HOURS old, else None. The page's script applies the same rule
    in the browser, comparing the time embedded in the page with the reader's clock."""
    secs = (now - run).total_seconds()
    return int(secs // 3600) if secs > STALE_HOURS * 3600 else None


STALE_JS = r"""
(function(){  // the stale notice: shown above the freshness line when the newest run is more than __HOURS__ hours old
  var p=document.getElementById('fresh'), t=p?Date.parse(p.getAttribute('data-run')):NaN, age=Date.now()-t;
  if(isNaN(t)||!(age>__HOURS__*3600000)){return;}
  var n=document.createElement('p');
  n.className='stale';n.setAttribute('role','note');
  n.textContent='This forecast is '+Math.floor(age/3600000)+' hours old. The next run is late, so treat it with care.';
  p.parentNode.insertBefore(n,p);
})();
""".replace("__HOURS__", str(STALE_HOURS))


def fresh_line(now):
    """When the page was made, and when the next run is due. Runs are hourly but often late, so no clock time is promised."""
    return (f'<p class="fresh" id="fresh" data-run="{now.isoformat(timespec="seconds")}">'
            f'Updated {now.strftime("%a %-d %b, %H:%M")} &middot; Next update within the hour</p>')


def band_floor(index):
    """The lowest score in the band of a score as shown: 8 for Prime, 6 for Grippy and so on."""
    s = rnd(index)
    return next(lo for lo, *_rest in BANDS if s >= lo)


def band_run(hs, d):
    """The hours a wall holds its day's band: the longest run of consecutive hours scoring, as shown, at least the floor of the
    band of the day's score, among the runs that share an hour with the best window (the earlier run on a tie).
    hs: the wall's hours that day, in order; d: its daily entry. Returns the run's hours."""
    floor = band_floor(d["index"])
    runs, cur = [], []
    for hr in hs:
        if rnd(hr["index"]) >= floor and (not cur or hour_of(hr) == hour_of(cur[-1]) + 1):
            cur.append(hr)
            continue
        if cur:
            runs.append(cur)
        cur = [hr] if rnd(hr["index"]) >= floor else []
    if cur:
        runs.append(cur)
    in_win = [run for run in runs if any(d["start"] <= hr["t"][11:16] < d["end"] for hr in run)]
    return max(in_win, key=len) if in_win else [hr for hr in hs if d["start"] <= hr["t"][11:16] < d["end"]]


def when_words(run, day_hrs):
    """Where a run of hours sits in the day, in words. All day; most of the day (two thirds or more); late on (to the day's last
    hour, starting in its second half); early on (from its first hour, ending in its first half); otherwise by the clock:
    in the morning, around midday (centred 12:00 to 14:00) or in the afternoon.
    day_hrs: every scored hour of that day, earlier ones included, so the words do not drift as the day goes on."""
    first, last = hour_of(day_hrs[0]), hour_of(day_hrs[-1]) + 1
    a, b = hour_of(run[0]), hour_of(run[-1]) + 1
    half = (first + last) / 2
    if a <= first and b >= last:
        return "all day"
    if (b - a) * 3 >= (last - first) * 2:
        return "most of the day"
    if b >= last and a >= half:
        return "late on"
    if a <= first and b <= half:
        return "early on"
    mid = (a + b) / 2
    return "in the morning" if mid < 12 else "around midday" if mid <= 14 else "in the afternoon"


def day_summary(results, cfg, day_iso):
    """The best of a day along the whole coast, for its summary card. The best stretch is the coast panel's stretch (weather point)
    holding the best wall:
    the highest day score as shown, ties to the longest run of hours in that band, then coast order.
    Returns a dict: best (None if nothing is scored), grippy (crags whose day score as shown is 6 or more) and crags (all crags)."""
    zones = cfg["zones"]
    best = None
    for i, r in enumerate(results):
        d = r["daily"].get(day_iso)
        if not d:
            continue
        hs = [hr for hr in r["hours"] if hr["t"][:10] == day_iso]
        run = band_run(hs, d)
        key = (rnd(d["index"]), len(run), -i)
        if best is None or key > best["key"]:
            best = {"key": key, "r": r, "d": d, "run": run}
    groups = groups_of(results)
    grippy = 0
    for _n, walls in groups:
        _r, d = best_wall(walls, day_iso)
        if d and rnd(d["index"]) >= 6:
            grippy += 1
    if best:
        c = best["r"]["crag"]
        best["stretch"] = zones[c["zone"]]["name"]
        best["when"] = when_words(best["run"], day_hours(best["r"], day_iso))
    return {"best": best, "grippy": grippy, "crags": len(groups)}


def day_over(results, day_iso):
    """The best score anywhere on a day that is already over: the highest best-window mean over its hours. None if none."""
    wins = [best_window(day_hours(r, day_iso)) for r in results]
    wins = [x[0] for x in wins if x]
    return max(wins) if wins else None


def summary_card(title, day, s=None, over=None):
    """One summary card. s: day_summary() for a day still to come; over: the best score of a day whose daylight is over."""
    head = f'<p class="ovl">{title}, {day.strftime("%a %-d %b")}</p>'
    if s is None:
        if over is None:
            block, line = '<span class="num sz-xl none" aria-hidden="true">-</span>', "Today is over"
        else:
            name = band(over)[0]
            block = f'<span class="num sz-xl past" role="img" aria-label="Best today: {fmt(over)}, {name}">{fmt(over)}</span>'
            line = "Today is over"
        return f'<div class="card">{block}<div>{head}<p class="ln">{line}</p></div></div>'
    b = s["best"]
    if not b:
        return f'<div class="card"><span class="num sz-xl none" aria-hidden="true">-</span><div>{head}<p class="ln">No hours scored.</p></div></div>'
    d = b["d"]
    name, _note, css = band(d["index"])
    unsure, risk = d["spread"] > 2 or d["n"] < 2, d["wet"] >= 0.3
    cls = css + (" unsure" if unsure else "") + (" risk" if risk else "")
    said = f"{fmt(d['index'])}, {name}" + (", wet-rock risk" if risk else "") + (", models disagree" if unsure else "")
    block = f'<span class="num sz-xl {cls}" role="img" aria-label="{said}">{fmt(d["index"])}</span>'
    n = s["grippy"]
    count = f'{n} of {s["crags"]} crags {"reaches" if n == 1 else "reach"} Grippy.'
    if rnd(d["index"]) < USABLE:
        line, meta = f'Nowhere climbable. Best is {name}, {fmt(d["index"])}, at {escape(b["r"]["crag"]["name"])}.', count
    else:
        run = b["run"]
        line = f'{name} {b["when"]}, {run[0]["t"][11:16]} to {end_of(run[-1])}'
        meta = f'Best from {escape(b["stretch"])}. {count}'
    return f'<div class="card">{block}<div>{head}<p class="ln">{line}</p><p class="cm">{meta}</p></div></div>'


def render_summary(results, now, cfg):
    """The Today and Tomorrow cards at the top of home. After dark Today reads "Today is over" and Tomorrow comes first."""
    today = now.date()
    tomorrow = today + timedelta(days=1)
    _day, after_dark, *_rest = coast_view(results, now, cfg)
    later = summary_card("Tomorrow", tomorrow, day_summary(results, cfg, tomorrow.isoformat()))
    if after_dark:
        cards = later + summary_card("Today", today, over=day_over(results, today.isoformat()))
    else:
        cards = summary_card("Today", today, day_summary(results, cfg, today.isoformat())) + later
    return f'<section class="cards" aria-label="Best today and tomorrow">{cards}</section>'


def render_help():
    """Help Grip get better: the three forms as equal cards, in a fixed order."""
    cards = [("log.html", "Log a day on the rock", "Say how the rock felt. It is how the forecast gets checked.", "Log a day", False),
             (NOTES_URL, "Send a crag note", "Aspect, tides, seepage, shelter or birds wrong or missing.", "Send a note", True),
             (FEEDBACK_URL, "Give feedback", "What works on the site, what does not, what is missing.", "Give feedback", True)]
    out = ['<section class="help" aria-labelledby="help-h"><h2 id="help-h">Help Grip get better</h2>'
           '<p class="hint">Grip is still being calibrated. Each of these takes a minute and needs no account.</p><div class="hcs">']
    for href, title, desc, act, ext in cards:
        tgt = ' target="_blank" rel="noopener"' if ext else ""
        out.append(f'<a class="hc" href="{href}"{tgt}><span class="ht">{title}</span><span class="hd">{desc}</span><span class="ha">{act}</span></a>')
    out.append("</div></section>")
    return "".join(out)


def grid_sub(walls):
    """A crag's sub-label in the seven-day grid: its aspect, or how many walls it has, and sport where a wall is bolted."""
    if len(walls) > 1:
        sub = f"Best of {len(walls)} walls"
    else:
        asp = walls[0]["crag"].get("aspect")
        sub = f"Faces {asp}" if asp else "Aspect not known"
    return sub + (" · sport" if any(r["crag"].get("type") == "sport" for r in walls) else "")


def odd_one(models):
    """With three models' scores for an hour, the one standing apart: (its name, how far from the nearer of the other two,
    negative when lower), when the other two are within 2 points of each other and it is more than 2 from both. Else None."""
    if len(models) != 3:
        return None
    lo, mid, hi = sorted(models, key=lambda m: m[1])
    if mid[1] - lo[1] > 2 and hi[1] - mid[1] <= 2:
        return lo[0], lo[1] - mid[1]
    if hi[1] - mid[1] > 2 and mid[1] - lo[1] <= 2:
        return hi[0], hi[1] - mid[1]
    return None


def and_list(xs):
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def models_sentence(r, day_iso, d, is_today):
    """The pop-up's plain words on the weather models for one wall's day, from its scored hours.
    An hour counts as a disagreement when the models' scores differ by more than 2, the rule the grid's stripes use.
    Returns (kind, sentence). kind: "a" the models agree, "w" they agree on the best window but not elsewhere,
    "d" they disagree in the best window, "o" only one model covers the best window."""
    hs = [hr for hr in r["hours"] if hr["t"][:10] == day_iso]
    if not hs:
        return "a", ""
    names = [lab for _m, lab, _d, _w in MODELS]
    seen = {lab for hr in hs for lab, _s in hr["models"]}
    before = {lab for hr in r["hours"] if hr["t"][:10] < day_iso for lab, _s in hr["models"]}
    parts = []
    gone = [lab for lab in names if lab not in seen and lab in before]  # the data shows these stop before this day
    stop = [(lab, end_of(max((hr for hr in hs if lab in dict(hr["models"])), key=lambda hr: hr["t"])))
            for lab in names if lab in seen and lab not in dict(hs[-1]["models"])]
    if len(seen) == 1:
        lab = next(iter(seen))
        lead = f"Only {lab} reaches this far ahead." if gone else f"Only {lab} has a forecast for this day."
        return "o", lead + " Treat it as a rough guide."
    if gone:
        parts.append(f"{and_list(gone)} {'does' if len(gone) == 1 else 'do'} not reach this far ahead.")
    parts += [f"{lab} only reaches to {end}." for lab, end in stop]
    win = [hr for hr in hs if d["start"] <= hr["t"][11:16] < d["end"]]
    split = [hr for hr in hs if len(hr["models"]) >= 2 and hr["spread"] > 2]
    if not split:
        sets = {tuple(sorted(dict(hr["models"]))) for hr in hs}
        who = ("All three models are" if len(seen) == 3 else "Both models are") if len(sets) == 1 else "The models are"
        parts.append(f"{who} within 2 points {'for the rest of the day' if is_today else 'all day'}.")
        kind = "a"
    else:
        hrs = [hour_of(hr) for hr in split]
        if len(hrs) == 1:
            when = f"at {split[0]['t'][11:16]}"
        elif hrs == list(range(hrs[0], hrs[0] + len(hrs))):
            when = f"from {split[0]['t'][11:16]} to {end_of(split[-1])}"
        else:
            when = f"at times between {split[0]['t'][11:16]} and {end_of(split[-1])}"

        def by(x):
            n = rnd(abs(x))
            return f"up to {n} points" if n > 2 else "just over 2 points"
        odd = [odd_one(hr["models"]) for hr in split]
        pairs = {tuple(sorted(dict(hr["models"]))) for hr in split}
        if all(odd) and len({o[0] for o in odd}) == 1:
            lab, gaps = odd[0][0], [o[1] for o in odd]
            far = max(gaps, key=abs)
            if all(g < 0 for g in gaps) or all(g > 0 for g in gaps):
                parts.append(f"{lab} is {by(far)} {'lower' if far < 0 else 'higher'} than the other two {when}.")
            else:
                parts.append(f"{lab} differs from the other two by {by(far)} {when}.")
        elif all(len(hr["models"]) == 2 for hr in split) and len(pairs) == 1:
            parts.append(f"{and_list(list(next(iter(pairs))))} differ by {by(max(hr['spread'] for hr in split))} {when}.")
        else:
            parts.append(f"The models differ by {by(max(hr['spread'] for hr in split))} {when}.")
        touches = any(hr in win for hr in split)
        parts.append("This touches the best window." if touches else "The best window is not affected.")
        kind = "d" if touches else "w"
    if win and min(len(hr["models"]) for hr in win) < 2:
        kind = "o"
        parts.append("Only one model covers part of the best window, so treat it as a rough guide.")
    return kind, " ".join(parts)


def cal_mark(v):
    """How one scored day went, on the score as shown: "in" the felt band, "near" (within a point) or "out"."""
    m = band_miss(rnd(v["grip"]), v["feel"])
    return "in" if m == 0 else "near" if abs(m) <= 1 else "out"


def sure_lead(cal):
    """The opening words of How sure is Grip? on home, from the calibration summary."""
    if cal is None:
        return "Logged days are scored against the archived forecasts once the day is over, and the results appear here."
    n, wait = cal["n"], cal.get("pending", 0)
    more = f" {wait} more {'is' if wait == 1 else 'are'} waiting to be scored." if wait else ""
    if n == 0:
        return "Not very, yet. No logged days have been scored so far." + more
    lead = "Not very, yet. " if n < SMALL_SAMPLE else ""
    if n == 1:
        res = {"in": "landed in the band climbers felt", "near": "was within a point of the band climbers felt",
               "out": "missed the band climbers felt by more than a point"}[cal_mark(cal["rows"][0])]
        return f"{lead}1 day has been logged. Grip's score {res}.{more}"
    return (f"{lead}{n} days have been logged. Grip's score landed in the band climbers felt on {cal['bands_right']} of them, "
            f"and within a point on {cal['within']}.{more}")


def render_sure(cal):
    """How sure is Grip?, under the grid: the lead in words, one square per scored day, and links to the full record on Method."""
    out = ['<section class="sure" aria-labelledby="sure-h"><div><h2 id="sure-h">How sure is Grip?</h2>'
           f'<p>{escape(sure_lead(cal))}</p><p class="links"><a href="method.html#days">Every logged day</a>'
           '<a href="method.html">How Grip works</a></p></div>']
    rows = sorted((cal or {}).get("rows", []), key=lambda v: (v["date"], v["crag"]))
    if rows:
        marks = [cal_mark(v) for v in rows]
        k = {m: marks.count(m) for m in ("in", "near", "out")}
        said = f'{len(marks)} logged day{"s" if len(marks) != 1 else ""}: {k["in"]} in the felt band, {k["near"]} within a point, {k["out"]} further out'
        out.append(f'<div class="rec"><div class="sq" role="img" aria-label="{said}">' + "".join(f'<i class="{m}"></i>' for m in marks)
                   + f'</div><p class="sql" aria-hidden="true"><span><i class="in"></i>In the felt band, {k["in"]}</span>'
                   f'<span><i class="near"></i>Within a point, {k["near"]}</span><span><i class="out"></i>Further out, {k["out"]}</span></p></div>')
    out.append("</section>")
    return "".join(out)


def render(results, tides, now, cfg, models_ok, cal=None):
    zones = cfg["zones"]
    today = now.date()
    all_days = sorted({d for r in results for d in r["daily"]})
    all_days = [d for d in all_days if date.fromisoformat(d) >= today][:7]

    groups = groups_of(results)

    out = []
    w = out.append
    w('<!doctype html><html lang="en-GB"><head><meta charset="utf-8">')
    w('<meta name="viewport" content="width=device-width, initial-scale=1">')
    w('<title>Grip forecast</title>')
    w(fonts())
    w(icon_links())
    w(f"<style>{CSS}{COAST_CSS}{HOME_CSS}</style></head><body>{header_bar(current='forecast')}<main class=\"home\">")
    w(fresh_line(now))
    w('<h1 class="vh">Grip, dry-rock forecast for the north-east sea cliffs</h1>')
    w(render_summary(results, now, cfg))
    w('<div class="top"><div>')
    w(render_coast(results, now, cfg))
    w('<div class="scale" aria-label="Grip scale">')
    for lo, name, note, css, rng in reversed(BANDS):
        w(f'<div><b class="kc {css}">{rng}</b><span>{name}: {note}</span></div>')
    w('<div><i class="smp risk" aria-hidden="true"></i><span>Wet-rock risk</span></div>'
      '<div><i class="smp unsure" aria-hidden="true"></i><span>Models disagree</span></div></div></div>')
    w(render_popular(results, tides, now, cfg))
    w("</div>")
    w(render_help())

    sections = []
    for n, walls in groups:
        sec = walls[0]["crag"].get("section") or zones[walls[0]["crag"]["zone"]]["name"]
        if sec not in sections:
            sections.append(sec)
    w('<h2 id="week-h">Next 7 days</h2>')
    w('<p class="hint">Crags with several walls show their best wall. Tap a crag name for its hour-by-hour page; tap any score for the other walls, what each weather model gives it, climbable hours and wet-rock risk.</p>')
    w('<div class="find" id="findbox" role="search" hidden><label for="find">Find a crag'
      '<input id="find" type="search" placeholder="Start typing a name, such as Logie" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" aria-controls="grid" aria-describedby="find-count"></label>'
      f'<p class="sub" id="find-count" role="status">{len(groups)} crags in {len(sections)} stretches</p></div>')
    w('<div class="gridbox"><div class="wrap"><table class="grid" id="grid" aria-labelledby="week-h"><thead><tr><th class="crag">Crag</th>')
    for d in all_days:
        dd = date.fromisoformat(d)
        today_col = ' class="today"' if dd == today else ""
        w(f"<th{today_col}><span>{dd.strftime('%a')}</span><span>{dd.day}</span></th>")
    w("</tr></thead><tbody>")
    said_at = {}
    for sec in sections:
        zgroups = [(n, walls) for n, walls in groups if (walls[0]["crag"].get("section") or zones[walls[0]["crag"]["zone"]]["name"]) == sec]
        w(f'<tr class="zone"><th colspan="{len(all_days) + 1}"><span>{escape(sec)}</span></th></tr>')
        for gname, walls in zgroups:
            sub = grid_sub(walls)
            gb = birds_in(walls, all_days)
            if gb:
                sub += ". Restricted: nesting birds" if gb["level"] == "restricted" else ". Nesting birds"
            find = " ".join([gname] + [wr["crag"]["wall"] for wr in walls if wr["crag"].get("wall")])  # what Find a crag matches against
            w(f'<tr data-find="{escape(find)}"><th class="crag"><a href="detail/{slug(gname)}.html">{escape(gname)}</a><small>{escape(sub)}</small></th>')
            for d in all_days:
                r, v = best_wall(walls, d)
                if not v:
                    w('<td><div class="none">-</div></td>')
                    continue
                c = r["crag"]
                name, note, css = band(v["index"])
                cls = css + (" unsure" if v["spread"] > 2 or v["n"] < 2 else "") + (" risk" if v["wet"] >= 0.3 else "")
                mods = "|".join(f"{lab}~{sc:.1f}" for lab, sc in v["models"])
                wl = ""
                if len(walls) > 1:
                    parts = []
                    for wr in walls:
                        wd = wr["daily"].get(d)
                        if wd:
                            parts.append(f'{wr["crag"].get("wall") or "Main face"}~{wd["index"]:.1f}~{wd["start"]} to {wd["end"]}~{wd["usable"]} of {wd["hours"]}~{pct(wd["wet"])}')
                    wl = "|".join(parts)
                dd = date.fromisoformat(d).strftime("%a %-d %b")
                said = "".join(models_sentence(r, d, v, date.fromisoformat(d) == today))  # its kind, then the sentence
                said = said_at.setdefault(said, len(said_at))  # each distinct sentence goes in the page once
                w(f'<td><button type="button" class="cell {cls}" data-crag="{escape(gname)}" data-wall="{escape(c.get("wall") or "")}" data-day="{dd}" data-ms="{said}" '
                  f'data-win="{v["start"]} to {v["end"]}" data-score="{v["index"]:.1f}" data-usable="{v["usable"]} of {v["hours"]}" data-drying="{escape(v["drying"])}" '
                  f'data-wet="{pct(v["wet"])}" data-models="{escape(mods)}" data-walls="{escape(wl)}" data-log="{escape(log_link(c, d if date.fromisoformat(d) <= today else today.isoformat()))}" data-note="{escape(note_link(c))}" data-detail="detail/{slug(gname)}.html" '
                  f'data-birds="{escape(gb["note"]) if gb else ""}" '
                  f'aria-label="{escape(label(c))}, {dd}: {fmt(v["index"])}, {name}">{fmt(v["index"])}</button></td>')
            w("</tr>")
    w('</tbody></table></div><div class="none-box" id="find-empty" hidden><p id="find-none"></p>'
      '<button type="button" class="clear" id="find-clear">Clear</button></div></div>')
    w('<div class="key">')
    for lo, name, note, css, rng in BANDS:
        w(f'<span><i class="kc {css}">{rng}</i> {name}: {note}</span>')
    w('<span><i class="smp unsure" aria-hidden="true"></i>Striped: models differ by more than 2, or only one model</span>')
    w('<span><i class="smp risk" aria-hidden="true"></i>Dot: at least one model in three has the rock wet, foggy or raining in the best window</span>')
    w("</div>")


    w(render_sure(cal))
    w('<dialog id="detail" aria-labelledby="d-title"><form method="dialog"><div class="dh"><h3 id="d-title"></h3><button>Close</button></div>'
      '<div class="ds"><span id="d-score"></span><div><p class="ovl">Blended</p><p id="d-sub"></p></div></div>'
      '<div class="dm"><p class="ovl" id="d-mhead" hidden></p><p class="mh" id="d-mh"></p><p id="d-ms"></p><div id="d-models"></div></div>'
      '<div id="d-wallbox" hidden><p class="ovl">Walls</p><div id="d-walls"></div></div>'
      '<p class="blend">The blend weights the Met Office 2.5 (1 beyond two days), ECMWF 1 and ICON 1. The Met Office weight was raised early on, when it led the other models on the first logged days; on the current count its lead is narrow, so the weights will be reviewed as more days are logged.</p>'
      '<p id="d-birds" style="display:none;color:var(--ink)"></p>'
      '<p class="acts"><a id="d-detail" href="#">Hour by hour for this crag</a></p>'
      '<p class="acts"><a id="d-log" href="#">Log how it actually was</a> &middot; <a id="d-note" href="#" target="_blank" rel="noopener">Send a crag note</a></p></form></dialog>')
    w(f"<script>var MODELS_SAID={js(list(said_at))};{STALE_JS}{SWITCH_JS}{MATCH_JS}{FIND_JS}{FADE_JS}</script>")
    w("""<script>
(function(){
  var dlg=document.getElementById('detail'), sel=null,
      MK={a:'The models agree',w:'The models agree on the best window',d:'The models disagree',o:'One model only'};
  function band(s){s=Math.round(s);return s>=8?'b5':s>=6?'b4':s>=4?'b3':s>=2?'b2':'b1';}
  function item(s,name,more){  // a score block and its name, with an optional detail line under the name
    var el=document.createElement('div'), c=document.createElement('span'), t=document.createElement('span');
    c.className='chip '+band(s);c.textContent=Math.round(s);
    t.textContent=name;
    if(more){var m=document.createElement('small');m.textContent=more;t.appendChild(m);}
    el.appendChild(c);el.appendChild(t);return el;
  }
  document.querySelectorAll('button.cell').forEach(function(b){
    b.addEventListener('click',function(){
      document.getElementById('d-title').textContent=b.dataset.crag;
      var who=b.dataset.wall?(' on '+b.dataset.wall):'';
      document.getElementById('d-sub').textContent=b.dataset.day+', best window '+b.dataset.win+who+'. Climbable hours: '+b.dataset.usable+'. Wet-rock risk: '+b.dataset.wet+'.'+(b.dataset.drying?(' '+b.dataset.drying+'.'):'');
      var s=parseFloat(b.dataset.score), sc=document.getElementById('d-score');
      sc.className='num sz-xl '+band(s)+(b.classList.contains('unsure')?' unsure':'')+(b.classList.contains('risk')?' risk':'');
      sc.textContent=Math.round(s);
      var mh=document.getElementById('d-mhead'), ms=document.getElementById('d-models'), wb=document.getElementById('d-wallbox'), ws=document.getElementById('d-walls');
      mh.textContent='Models'+who;mh.hidden=!b.dataset.walls;
      var said=MODELS_SAID[+b.dataset.ms]||'a', mt=document.getElementById('d-ms');  // its kind, then the sentence
      document.getElementById('d-mh').textContent=MK[said.charAt(0)];
      mt.textContent=said.slice(1);mt.hidden=!mt.textContent;
      ms.textContent='';
      b.dataset.models.split('|').forEach(function(m){var p=m.split('~');ms.appendChild(item(parseFloat(p[1]),p[0]));});
      ws.textContent='';wb.hidden=!b.dataset.walls;
      if(b.dataset.walls){
        b.dataset.walls.split('|').forEach(function(m){var p=m.split('~');ws.appendChild(item(parseFloat(p[1]),p[0],p[2]+', '+p[3]+' climbable, wet risk '+p[4]));});
      }
      document.getElementById('d-log').href=b.dataset.log;
      document.getElementById('d-note').href=b.dataset.note;
      document.getElementById('d-detail').href=b.dataset.detail;
      var bp=document.getElementById('d-birds'); if(b.dataset.birds){bp.textContent='Birds: '+b.dataset.birds; bp.style.display='block';} else {bp.style.display='none';}
      if(sel){sel.classList.remove('sel');}
      sel=b;b.classList.add('sel');
      if(dlg.showModal){dlg.showModal();}else{dlg.setAttribute('open','');}
    });
  });
  dlg.addEventListener('click',function(e){if(e.target===dlg){dlg.close();}});
  dlg.addEventListener('close',function(){if(sel){sel.classList.remove('sel');sel=null;}});
})();
</script>""")
    w(f"</main>{site_foot()}</body></html>")
    return "".join(out)


def render_method(cal, now, models_ok):
    """The Method page: how Grip works, the weather models in the latest run, and the full calibration against logged days."""
    out = []
    w = out.append
    w('<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    w("<title>Grip: how Grip works</title>")
    w(fonts())
    w(icon_links())
    w(f"<style>{CSS}{METHOD_CSS}</style></head><body>{header_bar(current='method')}<main>")
    w('<h1>How Grip works</h1><div class="method">')
    w("<p>Grip estimates the state of the rock, hour by hour, for each wall. It models the two things that make sea-cliff rock greasy: "
      "water on the surface, from rain, spray, sea salt drawing moisture out of damp air, or condensation on rock colder than the air's dew point; "
      "and how fast the air, wind and sun can dry it again. Each daylight hour collects points from the factors below, which are turned into a "
      "0 to 10 index. The three weather models are scored separately and blended, with the Met Office 2 km model weighted highest for the first two days. "
      "A day's score is its best three-hour window; the number of climbable hours and the wet-rock risk are shown alongside.</p>")
    w('<table class="factors"><tr><th>Factor</th><th>Points</th><th>Why</th></tr>'
      "<tr><td>Air moisture</td><td>+1 for every 4% below 76% humidity (up to +4 at 60%) and -1 for every 5% above (down to -4), with an extra -1 once humidity passes 75%. The penalties count in full when the rock is within 2&deg;C of the dew point and at half when it is 4&deg;C or more clear</td>"
      "<td>Sea salt on the rock starts drawing water out of the air at about 75% humidity. Humid air greases rock through condensation, so the penalty is tied to how close the rock is to the dew point: logged days showed dry rock in 80% air climbing well. Below 76% the reward was steepened after logged days showed the rock keeps improving as the air dries.</td></tr>"
      "<tr><td>Haar</td><td>Fog on the Met Office 2 km model or visibility under 1 km -4; patchy fog or visibility under 4 km -2</td>"
      "<td>Sea fog soaks the rock directly and stops any drying. It also adds to the water on the rock (0.1 mm an hour in thick haar, half that in patchy), so the rock stays damp after the haar lifts until the air and wind have dried it.</td></tr>"
      "<tr><td>Rock against dew point</td><td>Rock temperature minus dew point: 0 or less -4, up to 1&deg;C -3, up to 2&deg;C -2, up to 3&deg;C -1, over 5&deg;C +1</td>"
      "<td>Rock sweats when it is colder than the dew point. Rock temperature is estimated from the current air temperature (40%) and the last 24 hours' average (60%), "
      "pulled 30% towards the sea temperature (60% at tidal walls, which stand in it), warmed by up to 3&deg;C when the sun is on the face, and cooled by 1.5&deg;C under a clear sky with little wind when the sun is below 15 degrees or gone. "
      "That covers warm damp air after a cold spell, cold-sea sweating in spring, dew at dawn and the damp that arrives as the sun leaves a face.</td></tr>"
      "<tr><td>Wind direction</td><td>-1 straight onshore, +1 straight offshore, 0 along the shore, with the effect shrinking to nothing in a calm (full from 15 km/h)</td>"
      "<td>Onshore air is moist and salty. The Aberdeenshire coast counts as facing east-south-east, the Banff and Moray coast as facing north.</td></tr>"
      "<tr><td>Wind strength</td><td>Under 5 km/h -1, 5-15 +1, 15-35 +2, over 35 +1. At sheltered walls at the back of a bay the speed is halved unless the wind blows onto the face; in a narrow inlet it is halved from every direction. Onshore wind over 25 km/h -1, over 40 km/h -2. Positive points are halved while the rock is wet</td>"
      "<td>Wind clears damp air off the rock and speeds drying, but a gale onshore carries spray.</td></tr>"
      "<tr><td>Sun</td><td>Cloud 0, sun +1, sun on the face +3 (+2 when the sun is under 10 degrees up). Halved while the rock is wet</td>"
      "<td>Direct sun warms the rock above the dew point and dries it. On the face means within 60 degrees of the wall's aspect.</td></tr>"
      "<tr><td>Sea state</td><td>1.5 m+ -2, 0.8 to 1.5 m -1, 0.3 to 0.8 m 0, under 0.3 m +1</td>"
      "<td>Spray wets the rock and lays down fresh salt. Waves from behind or along the face count at 40%, or 70% for long-period swell, which wraps round headlands. In narrow inlets the swell funnels and reflects, so the height counts 1.5 times from any direction; walls protected by offshore rock count it at half.</td></tr>"
      "<tr><td>Water on the rock</td><td>Raining -5. Otherwise, by the water left on the rock: over 0.5 mm -3, 0.1-0.5 mm -2, a trace -1</td>"
      "<td>The film is tracked hour by hour. Rain adds to it, up to 2 mm; a big sea (over 2.5 m, or 2 m at tidal walls) adds a little spray; and at 85%+ humidity the salt draws in a thin brine film of up to 0.15 mm. "
      "It dries at a rate set by the vapour pressure deficit (how much more moisture the air can take), the wind and sun on the face. Shelter is not applied here: logged days show sheltered rock still dries at the full rate in dry air. "
      "Humid, still air barely dries it; warm, breezy, sunny air clears a light shower in two or three hours. This is what makes the morning after a humid night greasy until the air dries.</td></tr>"
      "<tr><td>Seepage</td><td>5 mm+ of rain in the last 24 hours -2, 10 mm+ -3, a further -1 for 25 mm+ in the last three days</td>"
      "<td>Drainage after heavy rain lasts much longer than surface water.</td></tr>"
      "<tr><td>Dry rock</td><td>Up to +2 when there is no water on the rock, no rain, no haar and the rock is 3&deg;C or more above the dew point: the full +2 at 76% humidity and above, fading to nothing at 60%, where the air reward already covers it</td>"
      "<td>Dry rock on a grey day is good rock. Without this, an overcast calm morning with nothing wrong scored Greasy; logged days said Grippy. The calm-air penalty is also waived when the rock is dry and the air is under 80%.</td></tr></table>")
    w("<p>The index is 3 plus half the points, held between 0 and 10. Hours with the sun less than 5 degrees above the horizon are not scored. "
      "Tides are shown for planning but not scored, and so are nesting birds: a crag in its bird season is marked, not marked down. Model disagreement is shown rather than hidden: striped cells and the wet-rock risk tell you when the forecasts differ. "
      "The weightings are a first estimate and are being checked against real days; expect them to change.</p>")
    w("</div>")
    w('<h2 id="models">Weather models</h2><div class="method">'
      f'<p>Models in the latest run, {now.strftime("%a %-d %b, %H:%M")}: {escape(", ".join(models_ok)) or "none available"}.</p></div>')
    w('<h2 id="days">Checking Grip against real days</h2><div class="method">')
    if cal is None:
        w("<p>Logged days are scored against the archived forecasts once the day is over, and the results appear here.</p>")
    elif cal["n"] == 0:
        w(f"<p>No scored days yet. {cal['pending']} logged and waiting to be scored.</p>")
    else:
        w(f"<p>{cal['n']} logged day{'s' if cal['n'] != 1 else ''} scored so far"
          f"{', ' + str(cal['pending']) + ' waiting' if cal['pending'] else ''}. "
          f"Taking the score as shown, Grip landed in the felt band {cal['bands_right']} time{'s' if cal['bands_right'] != 1 else ''}, and within a point of it {cal['within']} time{'s' if cal['within'] != 1 else ''}. "
          f"Misses are measured on the unrounded score from the edge of the band, since the form records a band rather than a number: "
          f"typical miss {cal['mae']:.1f}" + (f", on average {abs(cal['bias']):.1f} {'above' if cal['bias'] > 0 else 'below'} the felt band" if abs(cal['bias']) >= 0.05 else "") + ".</p>")
        if cal.get("by_model"):
            parts = [f'{lab} in the band {m["right"]} of {m["n"]}, typical miss {m["mae"]:.1f}' + (f' ({"above" if m["bias"] > 0 else "below"} by {abs(m["bias"]):.1f})' if abs(m["bias"]) >= 0.05 else "")
                     for lab, m in cal["by_model"].items()]
            w(f"<p>By model: {'; '.join(parts)}. The model that lands in the band most often over enough days is the one to trust most in the blend. "
              "The actual-weather column scores the day from the ERA5 reanalysis, the best record of what the weather really did, so it tests the scoring logic itself rather than the forecasts.</p>")

        def chip(x):
            if x is None:
                return "-"
            name, note, css = band(x)
            return f'<span class="chip {css}">{fmt(x)}</span>'

        w('<div class="wrap"><table class="cal"><tr><th>Date</th><th>Crag</th><th>Felt</th><th>Grip</th>' + "".join(f"<th>{lab}</th>" for _m, lab, _d, _w in MODELS) + "<th>Actual weather</th></tr>")
        for v in cal["rows"]:
            cells = "".join(f'<td>{chip(v.get("models", {}).get(lab))}</td>' for _m, lab, _d, _w in MODELS) + f'<td>{chip(v.get("era"))}</td>'
            lo, hi = FEEL_RANGE[v["feel"]]
            times = f' <small>({v["n_logs"]} logs)</small>' if v.get("n_logs", 1) > 1 else ""
            w(f'<tr><td>{date.fromisoformat(v["date"]).strftime("%-d %b %Y")}</td><td>{escape(v["crag"])}{times}</td><td>{escape(FEEL_NAME[v["feel"]])} ({lo:g} to {min(hi - 1, 10):g})</td>'
              f'<td>{chip(v["grip"])} {band(v["grip"])[0]}</td>{cells}</tr>')
        w("</table></div>")  # in its own scrolling box, like the crag pages' logged days, so the page never scrolls sideways
    w("</div>")
    w('<footer class="foot"><p>Forecast data: <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0), from the Met Office '
      "(UK Met Office data, CC BY-SA 4.0), ECMWF and the Deutscher Wetterdienst (ICON). The actual-weather column is scored from the ERA5 "
      "reanalysis of the Copernicus Climate Change Service, also through Open-Meteo. "
      "Crag details, aspects and tidal status from the <a href=\"https://routes.smc.org.uk/\">SMC routes database</a>, with local corrections; "
      "nesting bird notes from the SMC database and UKC.</p>"
      "<p>Grip is independent and not affiliated with the SMC or UKClimbing.</p></footer>")
    w(f"</main>{site_foot()}</body></html>")
    return "".join(out)


# ---------------------------------------------------------------- ntfy
def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_state(st):
    with open(STATE_FILE, "w") as f:
        json.dump(st, f, indent=2, sort_keys=True)
        f.write("\n")


def daily_message(results, now):
    lines = []
    for day, title in ((now.date(), "Today"), (now.date() + timedelta(days=1), "Tomorrow")):
        items = []
        for name, walls in groups_of(results):
            r, d = best_wall(walls, day.isoformat())
            if d:
                items.append((d["index"], r, d))
        items.sort(key=lambda x: -x[0])
        if not items:
            continue
        lines.append(f"{title}:")
        for s, r, d in items[:4]:
            name = band(s)[0]
            lines.append(f"{fmt(s)} {name}: {label(r['crag'])}, {d['start']}-{d['end']}")
    return "\n".join(lines)


def send_ntfy(topic, text, click):
    headers = {"Title": "Grip forecast", "Tags": "rock"}
    if click:
        headers["Click"] = click
    req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=text.encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


# ---------------------------------------------------------------- main
def main():
    with open(os.path.join(HERE, "crags.json")) as f:
        cfg = json.load(f)
    if os.environ.get("GRIP_FAKE"):
        models, marine = fake_data(cfg["zones"])
    else:
        models = fetch_models(cfg["zones"])
        marine = fetch_marine(cfg["zones"])
    models_ok = [lab for mid, lab, _d, _w in MODELS if any(models[z].get(mid) for z in models)]
    if not models_ok:
        log("No forecast data at all; leaving the previous page in place.")
        sys.exit(1)
    results, tides, now = build(cfg, models, marine)
    try:
        cal = calibrate(cfg)
    except Exception as e:  # noqa: BLE001
        log(f"Calibration skipped: {e}")
        cal = None
    os.makedirs(SITE_DIR, exist_ok=True)
    html = render(results, tides, now, cfg, models_ok, cal)
    with open(os.path.join(SITE_DIR, "index.html"), "w") as f:
        f.write(html)
    with open(os.path.join(SITE_DIR, "method.html"), "w") as f:
        f.write(render_method(cal, now, models_ok))
    with open(os.path.join(SITE_DIR, "birds.html"), "w") as f:
        f.write(render_birds(cfg, now))
    with open(os.path.join(SITE_DIR, "log.html"), "w") as f:
        f.write(render_log(cfg))
    os.makedirs(os.path.join(SITE_DIR, "detail"), exist_ok=True)
    view, here, logged = coast_view(results, now, cfg), zone_now(cfg, models, marine, now), logged_days(cfg)
    nxt = next_view(results, view)
    for gname, walls in groups_of(results):
        with open(os.path.join(SITE_DIR, "detail", slug(gname) + ".html"), "w") as f:
            f.write(render_detail(gname, walls, tides, now, now.date(), cfg, view, here, logged, nxt))
    os.makedirs(os.path.join(SITE_DIR, "assets"), exist_ok=True)
    for n in LOGO_FILES:
        shutil.copyfile(os.path.join(ASSETS_DIR, n), os.path.join(SITE_DIR, "assets", n))
    for n in ICON_FILES:
        shutil.copyfile(os.path.join(ASSETS_DIR, n), os.path.join(SITE_DIR, n))
    os.makedirs(os.path.join(SITE_DIR, "assets", "fonts"), exist_ok=True)
    for n in sorted(os.listdir(FONTS_DIR)):
        shutil.copyfile(os.path.join(FONTS_DIR, n), os.path.join(SITE_DIR, "assets", "fonts", n))
    with open(os.path.join(SITE_DIR, ".nojekyll"), "w") as f:
        f.write("")
    log(f"Wrote page ({len(html) // 1024} KB), models: {', '.join(models_ok)}")

    st = load_state()
    week = now.strftime("%G-W%V")
    if st.get("keepalive") != week:
        st["keepalive"] = week
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if topic and now.hour == 8 and st.get("last_push") != now.date().isoformat():
        try:
            send_ntfy(topic, daily_message(results, now), PAGE_URL)
            st["last_push"] = now.date().isoformat()
            log("Sent daily push")
        except Exception as e:  # noqa: BLE001
            log(f"Push failed: {e}")
    save_state(st)


if __name__ == "__main__":
    main()
