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
    ("ukmo_seamless", "Met Office", 7, 2.0),
    ("ecmwf_ifs025", "ECMWF", 8, 1.5),
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
FORM_CRAG = "entry.769015387"
FORM_WALL = "entry.1131909785"
FORM_DATE = "entry.2085482145"
NOTES_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeFKYLfOJ5V7yZiKIyMd9RxH9yiBWbQ27h_CLWvUP52EbOWPg/viewform"
NOTES_CRAG = "entry.1230562053"
NOTES_WALL = "entry.763167181"
LOG_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTJvP_UEtYosrIGLGEKbwuYLZn64xxAUlsedFZoAk5iESNDN9MBM2bgpkyYODvse42nNa-1JIuqZBDf/pub?output=csv"
CAL_FILE = os.path.join(HERE, "calibration.json")
MODEL_VERSION = "3.4"  # bump when the scoring or crag details change; logged days are then re-scored
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

COMPASS = {"N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5,
           "SE": 135, "SSE": 157.5, "S": 180, "SSW": 202.5, "SW": 225,
           "WSW": 247.5, "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5}
POINTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# Grip index 0-10. (min index, name, note, css class, range label)
BANDS = [
    (8, "Prime", "As dry as this coast gets", "b5", "8 to 10"),
    (6, "Crisp", "Good friction", "b4", "6 to 7"),
    (4, "Usable", "Climbable with care; choose the wall well", "b3", "4 to 5"),
    (2, "Greasy", "Damp and slippery; training at best", "b2", "2 to 3"),
    (0, "Soaked", "Wet rock", "b1", "0 to 1"),
]
USABLE = 4  # index at or above this counts as a usable hour


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
def f_air(rh):
    """Air moisture. Linear, plus a step at 75% where sea salt on the rock goes wet."""
    if rh is None:
        return None
    pts = min(4.0, (76 - rh) / 4) if rh <= 76 else max(-4.0, (76 - rh) / 5)
    if rh >= 75:
        pts -= 1
    return pts


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


def f_wind(kmh, is_onshore, sheltered):
    """Drying by wind at the rock. The speed is halved at sheltered crags. Onshore wind from force 4 up carries salt and spray."""
    if kmh is None:
        return None
    k = kmh * 0.5 if sheltered else kmh
    pts = -1 if k < 5 else 1 if k <= 15 else 2 if k <= 35 else 1
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


def score_crag(zones, crag, models, marine, now):
    """Hourly Grip for one wall: each model scored separately, then blended. Hours before now are skipped."""
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
            film = max(0.0, film - drying_rate(vpd, (WS[i] or 0) * (0.5 if in_shelter(sheltered, WD[i], asp, inlet) else 1.0), sun_pts))
            films.append(film)

        # pass 2: score the daylight hours still to come
        rows = {}
        for i, t in enumerate(times):
            dt = datetime.fromisoformat(t).replace(tzinfo=TZ)
            if dt + timedelta(hours=1) <= now:
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
                "air": f_air(RH[i]),
                "fog": f_fog(FG[i], VIS[i]),
                "dew": f_condensation(margin),
                "wdir": f_wind_dir(WD[i], WS[i], coast),
                "wind": f_wind(WS[i], is_on, in_shelter(sheltered, WD[i], asp, inlet)),
                "sun": sun_pts,
                "sea": seas[i][0],
            }
            f["wet"], wnote = f_wet(PR[i], films[i])
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

    for crag in cfg["crags"]:
        hours = score_crag(zones, crag, models, marine, now)
        days = {}
        for hr in hours:
            days.setdefault(hr["t"][:10], []).append(hr)
        daily = {}
        for d, hs in days.items():
            best = None
            for i in range(len(hs)):
                win = hs[i:i + 3]
                if len(win) < 2:
                    continue
                s = sum(x["index"] for x in win) / len(win)
                if best is None or s > best[0]:
                    best = (s, win)
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
                    "usable": sum(1 for x in hs if x["index"] >= USABLE), "hours": len(hs),
                    "drying": drying_note(hs),
                    "models": [(lab, sum(v) / len(v)) for lab, v in pm.items()],
                }
        results.append({"crag": crag, "hours": hours, "daily": daily})
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
            feel = r[ifeel].split(":")[0].strip()
            if not crag or d is None or t1 is None or t2 is None or feel not in FEEL:
                continue
            if t2 <= t1:
                t2 = t1 + 1
            wall = r[iwall].strip() if iwall is not None and iwall < len(r) else ""
            out.append({"crag": crag, "wall": wall, "date": d.isoformat(), "from": t1, "to": t2, "feel": feel,
                        "problems": r[iprob].strip() if iprob is not None and iprob < len(r) else ""})
        except Exception:  # noqa: BLE001
            continue
    return out


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
            wr.writerow([v["date"], v["crag"], f'{v["from"]:02d}:00', f'{v["to"]:02d}:00', v["feel"], lo, min(hi - 1, 10),
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
        if key in cache and (cache[key].get("era") is not None or cache[key].get("grip") is None):
            continue  # fully scored, or could not be scored; a day whose reanalysis was not out yet is tried again
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
                      "era": res["era"] if res else None, "era_base": res["era_base"] if res else None}
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
    errs = [band_miss(v["grip"], v["feel"]) for v in scored]
    bands_right = sum(1 for e in errs if e == 0)
    within = sum(1 for err in errs if abs(err) <= 1)
    by_model = {}
    for lab, getter in [(lab, (lambda v, lab=lab: v.get("models", {}).get(lab))) for _m, lab, _d, _w in MODELS] + [("Actual weather", lambda v: v.get("era"))]:
        ms = [band_miss(getter(v), v["feel"]) for v in scored if getter(v) is not None]
        if ms:
            by_model[lab] = {"n": len(ms), "right": sum(1 for x in ms if x == 0), "bias": sum(ms) / len(ms), "mae": sum(abs(x) for x in ms) / len(ms)}
    rows = sorted(scored, key=lambda v: v["date"], reverse=True)[:40]
    return {"n": len(scored), "pending": len(pending), "bias": sum(errs) / len(errs),
            "mae": sum(abs(e) for e in errs) / len(errs), "bands_right": bands_right, "within": within,
            "by_model": by_model, "rows": rows}


# ---------------------------------------------------------------- page
CSS = """
:root{--paper:#eef1f2;--ink:#1d2b34;--muted:#5b6b75;--rule:#c9d1d5;--card:#f8fafa;
--b1:#b3261e;--b2:#ee8a3a;--b3:#f2cd4f;--b4:#8fc66b;--b5:#2e8b3e;--b1t:#fff;--b2t:#1d2b34;--b3t:#1d2b34;--b4t:#1d2b34;--b5t:#fff}
@media (prefers-color-scheme:dark){:root{--paper:#141d23;--ink:#e3e8ea;--muted:#93a3ad;--rule:#2c3a43;--card:#1b262d}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 "Barlow",system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px 60px}
h1{font:600 2.1rem/1.1 "Barlow Condensed","Barlow",system-ui,sans-serif;margin:0 0 4px;letter-spacing:.01em}
h2{font:600 1.35rem/1.2 "Barlow Condensed","Barlow",system-ui,sans-serif;margin:36px 0 10px}
.updated{color:var(--muted);margin:0 0 22px}
a{color:inherit}
.scale{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;margin:0 0 26px}
.scale div{padding:8px 10px;border-radius:4px}
.scale b{display:block;font:600 1.3rem/1.1 "Barlow Condensed",system-ui,sans-serif}
.scale span{display:block;font-size:.82rem;line-height:1.3}
@media (max-width:560px){.scale{grid-template-columns:1fr}.scale div{display:grid;grid-template-columns:6.2rem 1fr;align-items:center;gap:10px;padding:6px 10px}.scale b{font-size:1.15rem;white-space:nowrap}}
.bets{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
.day h3{font:600 1.1rem "Barlow Condensed",system-ui,sans-serif;margin:0 0 8px}
.bet{display:grid;grid-template-columns:3.2rem 1fr;gap:12px;align-items:center;padding:8px 0;border-top:1px solid var(--rule)}
.num{font:600 1.7rem/1 "Barlow Condensed",system-ui,sans-serif;text-align:center;padding:8px 0;border-radius:4px}
.bet .who{font-weight:600}
.bet .sub{color:var(--muted);font-size:.9rem}
.b1{background:var(--b1);color:var(--b1t)}.b2{background:var(--b2);color:var(--b2t)}.b3{background:var(--b3);color:var(--b3t)}
.b4{background:var(--b4);color:var(--b4t)}.b5{background:var(--b5);color:var(--b5t)}
.wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;border:1px solid var(--rule);border-radius:4px;background:var(--card)}
table{border-collapse:collapse;width:100%}
.grid th,.grid td{padding:0;text-align:center;font-size:.85rem;white-space:nowrap}
.grid thead th{padding:6px 4px;font-weight:600;color:var(--muted);border-bottom:1px solid var(--rule)}
.grid th.crag{position:sticky;left:0;background:var(--card);text-align:left;padding:6px 10px;font-weight:600;min-width:12rem;border-right:1px solid var(--rule);z-index:1}
.grid th.crag small{display:block;font-weight:400;color:var(--muted)}
@media (max-width:640px){.grid th.crag{min-width:7.5rem;max-width:8.5rem;white-space:normal;font-size:.8rem;padding:4px 6px}.grid td div,.grid td button{min-width:2.1rem;padding:5px 0}}
.grid tr.zone th{text-align:left;padding:10px 10px 4px;font:600 .95rem "Barlow Condensed",system-ui,sans-serif;color:var(--muted);position:sticky;left:0;background:var(--card)}
.grid td div,.grid td button{margin:2px;min-width:2.6rem;padding:6px 0;border-radius:3px;font-weight:600;position:relative}
.grid td button{border:0;font:inherit;font-weight:600;cursor:pointer;width:calc(100% - 4px)}
.grid td .unsure{background-image:repeating-linear-gradient(135deg,transparent 0 5px,rgba(255,255,255,.28) 5px 8px)}
.grid td .risk::after,.key i.risk::after{content:"";position:absolute;top:3px;right:3px;width:6px;height:6px;border-radius:50%;background:#1d2b34;opacity:.7}
.key i.risk::after{top:2px;right:2px;width:5px;height:5px}
.grid td div.none{color:var(--muted);font-weight:400}
.hint{color:var(--muted);font-size:.9rem;margin:-4px 0 10px}
.log{margin:-10px 0 26px;color:var(--muted);font-size:.92rem}
.btn{display:inline-block;padding:7px 14px;border-radius:4px;background:var(--ink);color:var(--paper);text-decoration:none;font-weight:600;margin-right:10px}
.btn:hover{opacity:.9}
.cal{width:auto;font-size:.85rem}
.cal td,.cal th{padding:3px 10px;border-bottom:1px solid var(--rule);text-align:left}
.key{display:flex;flex-wrap:wrap;gap:8px 16px;margin:10px 0 0;font-size:.85rem;color:var(--muted)}
.key span{display:inline-flex;align-items:center;gap:6px}
.key i{display:inline-block;width:14px;height:14px;border-radius:2px;position:relative}
details{border-top:1px solid var(--rule);padding:6px 0}
summary{cursor:pointer;font-weight:600;padding:6px 0}
summary small{font-weight:400;color:var(--muted)}
summary:focus-visible,a:focus-visible,button:focus-visible{outline:2px solid var(--b5);outline-offset:2px}
.hours{font-size:.82rem}
.hours th,.hours td{padding:4px 8px;text-align:right;border-bottom:1px solid var(--rule);white-space:nowrap}
.hours th:first-child,.hours td:first-child{text-align:left}
.hours thead th{color:var(--muted);font-weight:600}
.hours td.s{font-weight:700}
.hours tr.dayrow td{text-align:left;font:600 .95rem "Barlow Condensed",system-ui,sans-serif;padding-top:12px;border-bottom:none}
.method{max-width:70ch;color:var(--muted);font-size:.92rem}
.method table{width:auto;font-size:.85rem;margin:8px 0}
.method td,.method th{border:1px solid var(--rule);padding:3px 8px;text-align:left;vertical-align:top}
.method h3{font:600 1.1rem "Barlow Condensed",system-ui,sans-serif;margin:18px 0 6px}
.method li{margin:0 0 4px}
dialog{border:1px solid var(--rule);border-radius:6px;background:var(--card);color:var(--ink);width:min(24rem,92vw);padding:16px 18px;max-height:85vh;overflow:auto}
dialog::backdrop{background:rgba(0,0,0,.4)}
dialog h3{font:600 1.2rem "Barlow Condensed",system-ui,sans-serif;margin:0 0 2px}
dialog p{margin:0 0 10px;color:var(--muted);font-size:.9rem}
dialog table{width:100%;margin:0 0 12px}
dialog td{padding:5px 0;border-bottom:1px solid var(--rule)}
dialog td:last-child{text-align:right}
dialog .chip{display:inline-block;min-width:2.2rem;text-align:center;padding:2px 6px;border-radius:3px;font-weight:600}
dialog button{font:inherit;padding:6px 14px;border:1px solid var(--rule);border-radius:4px;background:var(--paper);color:var(--ink);cursor:pointer}
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


def log_link(c, day_iso):
    q = f"{FORM_URL}?usp=pp_url&{FORM_CRAG}={urllib.parse.quote(c['name'])}&{FORM_DATE}={day_iso}"
    return q + (f"&{FORM_WALL}={urllib.parse.quote(c['wall'])}" if c.get("wall") else "")


def note_link(c):
    q = f"{NOTES_URL}?usp=pp_url&{NOTES_CRAG}={urllib.parse.quote(c['name'])}"
    return q + (f"&{NOTES_WALL}={urllib.parse.quote(c['wall'])}" if c.get("wall") else "")


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def render_detail(gname, walls, tides, now, today):
    """Hour-by-hour page for one crag (all its walls, three days)."""
    out = []
    w = out.append
    w('<!doctype html><html lang="en-GB"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">')
    w(f"<title>{escape(gname)}: Grip hour by hour</title>")
    w('<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&family=Barlow+Condensed:wght@600&display=swap" rel="stylesheet">')
    w(f"<style>{CSS}</style></head><body><main>")
    r0, t0 = best_wall(walls, today.isoformat())
    summ = f"today {fmt(t0['index'])}, best {t0['start']} to {t0['end']}" + (f" on {r0['crag'].get('wall') or 'the main face'}" if len(walls) > 1 else "") if t0 else "no hours left today"
    w(f"<h1>{escape(gname)}</h1><p class=\"updated\">Hour by hour, next three days. {escape(summ[0].upper() + summ[1:])}. Scores are the blend of the models; the breakdown columns show the Met Office figures. Updated {now.strftime('%a %-d %b, %H:%M')}. <a href=\"../\">Back to the forecast</a></p>")
    for r in walls:
        c = r["crag"]
        if len(walls) > 1:
            w(f'<h3 style="font:600 1.05rem \'Barlow Condensed\',system-ui,sans-serif;margin:12px 0 4px">{escape(c.get("wall") or "Main face")} <small style="font-weight:400;color:var(--muted)">{escape(c.get("aspect") or "aspect unknown")}</small></h3>')
        w('<div class="wrap"><table class="hours"><thead><tr><th>Time</th><th>Grip</th><th>Wet risk</th><th>Humidity</th>'
          '<th>Rock vs dew point</th><th>Wind</th><th>Sun</th><th>Sea</th><th>Breakdown (points)</th><th>Models</th></tr></thead><tbody>')
        last_day = None
        for hr in r["hours"]:
            d = hr["t"][:10]
            if date.fromisoformat(d) > today + timedelta(days=2):
                break
            if d != last_day:
                lt = tides.get(c["zone"], {}).get(d, [])
                tide = f" (low water {', '.join(lt)})" if lt else ""
                w(f'<tr class="dayrow"><td colspan="10">{date.fromisoformat(d).strftime("%A %-d %b")}{tide}</td></tr>')
                last_day = d
            x = hr["d"]
            f = x["f"]
            name, note, css = band(hr["index"])
            wind = f'{compass(x["wd"])} {x["ws"]:.0f} km/h' if x["ws"] is not None else "?"
            sea = f'{x["ft"]:.1f} ft' if x["ft"] is not None else "-"
            rh = f'{x["rh"]:.0f}%' if x["rh"] is not None else "?"
            margin = f'{x["margin"]:+.1f}°C' if x["margin"] is not None else "-"
            brk = (f'air {fpt(f["air"])}, fog {fpt(f["fog"])}, dew {fpt(f["dew"])}, wind {fpt(f["wdir"])}/{fpt(f["wind"])}, '
                   f'sun {fpt(f["sun"])}, sea {fpt(f["sea"])}, wet {fpt(f["wet"])}, seep {fpt(f["seep"])}')
            if x["note"]:
                brk += f' ({x["note"]})'
            mods = ", ".join(f"{lab[:3]} {s:.0f}" for lab, s in hr["models"])
            w(f'<tr><td>{hr["t"][11:16]}</td><td class="s"><span class="num {css}" style="font-size:.85rem;padding:2px 6px">{fmt(hr["index"])}</span></td>'
              f'<td>{pct(hr["wet"])}</td><td>{rh}</td><td>{margin}</td><td>{wind}</td><td>{escape(x["sun"])}</td><td>{sea}</td>'
              f'<td>{escape(brk)}</td><td>{escape(mods)}</td></tr>')
        w("</tbody></table></div>")

    w("</main></body></html>")
    return "".join(out)


def render(results, tides, now, cfg, models_ok, cal=None):
    zones = cfg["zones"]
    today = now.date()
    tomorrow = today + timedelta(days=1)
    all_days = sorted({d for r in results for d in r["daily"]})
    all_days = [d for d in all_days if date.fromisoformat(d) >= today][:7]

    groups = groups_of(results)

    def best_list(day, n=5):
        items = []
        for name, walls in groups:
            r, d = best_wall(walls, day.isoformat())
            if d:
                items.append((d["index"], r, d))
        items.sort(key=lambda x: -x[0])
        return items[:n]

    out = []
    w = out.append
    w('<!doctype html><html lang="en-GB"><head><meta charset="utf-8">')
    w('<meta name="viewport" content="width=device-width, initial-scale=1">')
    w('<title>Grip forecast</title>')
    w('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    w('<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;600&family=Barlow+Condensed:wght@600&display=swap" rel="stylesheet">')
    w(f"<style>{CSS}</style></head><body><main>")
    w("<h1>Grip</h1>")
    w(f'<p class="updated">Dry-rock forecast for the sea cliffs of north-east Scotland. Updated {now.strftime("%a %-d %b, %H:%M")}. '
      f'Models: {escape(", ".join(models_ok)) or "none available"}.</p>')
    w('<div class="scale" aria-label="Grip scale">')
    for lo, name, note, css, rng in reversed(BANDS):
        w(f'<div class="{css}"><b>{rng}</b><span>{name}: {note}</span></div>')
    w("</div>")
    w(f'<p class="log"><a class="btn" href="{FORM_URL}" target="_blank" rel="noopener">Log a day on the rock</a>'
      "Climbed on the coast? Say how the rock felt. It takes a minute, it is anonymous, and it is how Grip gets checked against reality. "
      f'Know a crag better than the list does? <a href="{NOTES_URL}" target="_blank" rel="noopener">Send a crag note</a>: aspect, tides, seepage, shelter, birds.</p>')

    pair = ((today, "Today"), (tomorrow, "Tomorrow"))
    if not best_list(today):
        pair = ((tomorrow, "Tomorrow"), (tomorrow + timedelta(days=1), "Day after"))
    w('<section class="bets">')
    for day, title in pair:
        w(f'<div class="day"><h3>{title}, {day.strftime("%a %-d %b")}</h3>')
        bl = best_list(day)
        if not bl:
            w('<p class="sub">No daylight hours left to score.</p>')
        for s, r, d in bl:
            name, note, css = band(s)
            lt = tides.get(r["crag"]["zone"], {}).get(day.isoformat(), [])
            tide = f" Low water {', '.join(lt)}." if lt else ""
            risk = f" Wet-rock risk {pct(d['wet'])}." if d["wet"] >= 0.3 else ""
            b = birds_in([r], [day.isoformat()])
            birds = (" Restricted for nesting birds." if b["level"] == "restricted" else " Nesting birds at this time of year.") if b else ""
            w(f'<div class="bet"><div class="num {css}">{fmt(s)}</div><div><div class="who">{escape(label(r["crag"]))}</div>'
              f'<div class="sub">{name}, best {d["start"]} to {d["end"]}; {d["usable"]} of {d["hours"]} daylight hours usable.{risk}{birds}{tide}</div></div></div>')
        w("</div>")
    w("</section>")

    w("<h2>Next 7 days</h2>")
    w('<p class="hint">Crags with several walls show their best wall. Tap a crag name for its hour-by-hour page; tap any score for the other walls, what each weather model gives it, usable hours and wet-rock risk.</p>')
    w('<div class="wrap"><table class="grid"><thead><tr><th class="crag">Crag</th>')
    for d in all_days:
        dd = date.fromisoformat(d)
        w(f"<th>{dd.strftime('%a')}<br>{dd.day}</th>")
    w("</tr></thead><tbody>")
    sections = []
    for n, walls in groups:
        sec = walls[0]["crag"].get("section") or zones[walls[0]["crag"]["zone"]]["name"]
        if sec not in sections:
            sections.append(sec)
    for sec in sections:
        zgroups = [(n, walls) for n, walls in groups if (walls[0]["crag"].get("section") or zones[walls[0]["crag"]["zone"]]["name"]) == sec]
        w(f'<tr class="zone"><th colspan="{len(all_days) + 1}">{escape(sec)}</th></tr>')
        for gname, walls in zgroups:
            c0 = walls[0]["crag"]
            if len(walls) == 1:
                sub = ", ".join(x for x in (c0.get("aspect") or "aspect unknown", c0["type"]) if x)
            else:
                sub = f"{len(walls)} walls, best shown"
            gb = birds_in(walls, all_days)
            if gb:
                sub += ". Restricted: nesting birds" if gb["level"] == "restricted" else ". Nesting birds"
            w(f'<tr><th class="crag"><a href="detail/{slug(gname)}.html" style="text-decoration:none">{escape(gname)}</a><small>{escape(sub)}</small></th>')
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
                w(f'<td><button type="button" class="cell {cls}" data-crag="{escape(gname)}" data-wall="{escape(c.get("wall") or "")}" data-day="{dd}" '
                  f'data-win="{v["start"]} to {v["end"]}" data-score="{v["index"]:.1f}" data-usable="{v["usable"]} of {v["hours"]}" data-drying="{escape(v["drying"])}" '
                  f'data-wet="{pct(v["wet"])}" data-models="{escape(mods)}" data-walls="{escape(wl)}" data-log="{escape(log_link(c, d if date.fromisoformat(d) <= today else today.isoformat()))}" data-note="{escape(note_link(c))}" data-detail="detail/{slug(gname)}.html" '
                  f'data-birds="{escape(gb["note"]) if gb else ""}" '
                  f'aria-label="{escape(label(c))}, {dd}: {fmt(v["index"])}, {name}">{fmt(v["index"])}</button></td>')
            w("</tr>")
    w("</tbody></table></div>")
    w('<div class="key">')
    for lo, name, note, css, rng in BANDS:
        w(f'<span><i class="{css}"></i>{rng} {name}: {note}</span>')
    w('<span><i class="b3 unsure" style="background-image:repeating-linear-gradient(135deg,transparent 0 5px,rgba(0,0,0,.25) 5px 8px)"></i>Striped: models differ by more than 2, or only one model</span>')
    w('<span><i class="b4 risk"></i>Dot: at least one model in three has the rock wet, foggy or raining in the best window</span>')
    w("</div>")


    w('<h2>Checking Grip against real days</h2><div class="method">')
    if cal is None:
        w("<p>Logged days are scored against the archived forecasts once the day is over, and the results appear here.</p>")
    elif cal["n"] == 0:
        w(f"<p>No scored days yet. {cal['pending']} logged and waiting to be scored.</p>")
    else:
        w(f"<p>{cal['n']} logged day{'s' if cal['n'] != 1 else ''} scored so far"
          f"{', ' + str(cal['pending']) + ' waiting' if cal['pending'] else ''}. "
          f"Grip landed in the felt band {cal['bands_right']} time{'s' if cal['bands_right'] != 1 else ''}, and within a point of it {cal['within']} time{'s' if cal['within'] != 1 else ''}. "
          f"Misses are measured from the edge of the band, since the form records a band rather than a number: "
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
            return f'<span class="chip {css}" style="display:inline-block;min-width:2.2rem;text-align:center;padding:1px 6px;border-radius:3px;font-weight:600">{fmt(x)}</span>'

        w('<table class="cal"><tr><th>Date</th><th>Crag</th><th>Felt</th><th>Grip</th>' + "".join(f"<th>{lab}</th>" for _m, lab, _d, _w in MODELS) + "<th>Actual weather</th></tr>")
        for v in cal["rows"]:
            cells = "".join(f'<td>{chip(v.get("models", {}).get(lab))}</td>' for _m, lab, _d, _w in MODELS) + f'<td>{chip(v.get("era"))}</td>'
            lo, hi = FEEL_RANGE[v["feel"]]
            times = f' <small>({v["n_logs"]} logs)</small>' if v.get("n_logs", 1) > 1 else ""
            w(f'<tr><td>{date.fromisoformat(v["date"]).strftime("%-d %b %Y")}</td><td>{escape(v["crag"])}{times}</td><td>{escape(v["feel"])} ({lo:g} to {min(hi - 1, 10):g})</td>'
              f'<td>{chip(v["grip"])} {band(v["grip"])[0]}</td>{cells}</tr>')
        w("</table>")
    w("</div>")
    w('<h2>How Grip works</h2><div class="method">')
    w("<p>Grip estimates the state of the rock, hour by hour, for each wall. It models the two things that make sea-cliff rock greasy: "
      "water on the surface, from rain, spray, sea salt drawing moisture out of damp air, or condensation on rock colder than the air's dew point; "
      "and how fast the air, wind and sun can dry it again. Each daylight hour collects points from the factors below, which are turned into a "
      "0 to 10 index. The three weather models are scored separately and blended, with the Met Office 2 km model weighted highest for the first two days. "
      "A day's score is its best three-hour window; the number of usable hours and the wet-rock risk are shown alongside.</p>")
    w("<table><tr><th>Factor</th><th>Points</th><th>Why</th></tr>"
      "<tr><td>Air moisture</td><td>+1 for every 4% below 76% humidity (up to +4 at 60%) and -1 for every 5% above (down to -4), with an extra -1 once humidity passes 75%</td>"
      "<td>Sea salt on the rock starts drawing water out of the air at about 75% humidity. The scale is continuous so a small forecast error does not flip the score. Below 76% the reward was steepened after logged days showed the rock keeps improving as the air dries.</td></tr>"
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
      "<tr><td>Sea state</td><td>5 ft+ -2, 2.5-5 ft -1, 1-2.5 ft 0, under 1 ft +1</td>"
      "<td>Spray wets the rock and lays down fresh salt. Waves from behind or along the face count at 40%, or 70% for long-period swell, which wraps round headlands. In narrow inlets the swell funnels and reflects, so the height counts 1.5 times from any direction; walls protected by offshore rock count it at half.</td></tr>"
      "<tr><td>Water on the rock</td><td>Raining -5. Otherwise, by the water left on the rock: over 0.5 mm -3, 0.1-0.5 mm -2, a trace -1</td>"
      "<td>The film is tracked hour by hour. Rain adds to it, up to 2 mm; a big sea (over 2.5 m, or 2 m at tidal walls) adds a little spray; and at 85%+ humidity the salt draws in a thin brine film of up to 0.15 mm. "
      "It dries at a rate set by the vapour pressure deficit (how much more moisture the air can take), the wind (halved at sheltered crags) and sun on the face. "
      "Humid, still air barely dries it; warm, breezy, sunny air clears a light shower in two or three hours. This is what makes the morning after a humid night greasy until the air dries.</td></tr>"
      "<tr><td>Seepage</td><td>5 mm+ of rain in the last 24 hours -2, 10 mm+ -3, a further -1 for 25 mm+ in the last three days</td>"
      "<td>Drainage after heavy rain lasts much longer than surface water.</td></tr></table>")
    w("<p>The index is 3 plus half the points, held between 0 and 10. Hours with the sun less than 5 degrees above the horizon are not scored. "
      "Tides are shown for planning but not scored, and so are nesting birds: a crag in its bird season is marked, not marked down. Model disagreement is shown rather than hidden: striped cells and the wet-rock risk tell you when the forecasts differ. "
      "The weightings are a first estimate and are being checked against real days; expect them to change.</p>")
    w('<p>Forecast data: <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0), including UK Met Office data (CC BY-SA 4.0). '
      "Crag details, aspects and tidal status from the <a href=\"https://routes.smc.org.uk/\">SMC routes database</a>, with local corrections; nesting bird notes from the SMC database and UKC.</p></div>")
    w('<dialog id="detail"><form method="dialog"><h3 id="d-title"></h3><p id="d-sub"></p><table id="d-models"></table>'
      '<p>The blend weights the Met Office 2 (1 beyond two days), ECMWF 1.5 and ICON 1.</p>'
      '<p id="d-birds" style="display:none;color:var(--ink)"></p>'
      '<p><a id="d-detail" href="#">Hour by hour for this crag</a></p>'
      '<p><a id="d-log" href="#" target="_blank" rel="noopener">Log how it actually was</a> &middot; <a id="d-note" href="#" target="_blank" rel="noopener">Send a crag note</a></p><button>Close</button></form></dialog>')
    w("""<script>
(function(){
  var dlg=document.getElementById('detail');
  function band(s){s=Math.round(s);return s>=8?'b5':s>=6?'b4':s>=4?'b3':s>=2?'b2':'b1';}
  function chip(s){return '<span class="chip '+band(s)+'">'+Math.round(s)+'</span>';}
  document.querySelectorAll('button.cell').forEach(function(b){
    b.addEventListener('click',function(){
      document.getElementById('d-title').textContent=b.dataset.crag;
      var who=b.dataset.wall?(' on '+b.dataset.wall):'';
      document.getElementById('d-sub').textContent=b.dataset.day+', best window '+b.dataset.win+who+'. Usable hours: '+b.dataset.usable+'. Wet-rock risk: '+b.dataset.wet+'.'+(b.dataset.drying?(' '+b.dataset.drying+'.'):'');
      var rows='';
      if(b.dataset.walls){
        rows+='<tr><td colspan="2" style="text-align:left"><strong>Walls</strong></td></tr>';
        b.dataset.walls.split('|').forEach(function(m){var p=m.split('~');rows+='<tr><td>'+p[0]+'<br><small>'+p[2]+', '+p[3]+' usable, wet risk '+p[4]+'</small></td><td>'+chip(parseFloat(p[1]))+'</td></tr>';});
        rows+='<tr><td colspan="2" style="text-align:left"><strong>Models'+who+'</strong></td></tr>';
      }
      rows+='<tr><td>'+(b.dataset.walls?'Blended':'<strong>Blended</strong>')+'</td><td>'+chip(parseFloat(b.dataset.score))+'</td></tr>';
      b.dataset.models.split('|').forEach(function(m){var p=m.split('~');rows+='<tr><td>'+p[0]+'</td><td>'+chip(parseFloat(p[1]))+'</td></tr>';});
      document.getElementById('d-models').innerHTML=rows;
      document.getElementById('d-log').href=b.dataset.log;
      document.getElementById('d-note').href=b.dataset.note;
      document.getElementById('d-detail').href=b.dataset.detail;
      var bp=document.getElementById('d-birds'); if(b.dataset.birds){bp.textContent='Birds: '+b.dataset.birds; bp.style.display='block';} else {bp.style.display='none';}
      if(dlg.showModal){dlg.showModal();}else{dlg.setAttribute('open','');}
    });
  });
  dlg.addEventListener('click',function(e){if(e.target===dlg){dlg.close();}});
})();
</script>""")
    w("</main></body></html>")
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
    os.makedirs(os.path.join(SITE_DIR, "detail"), exist_ok=True)
    for gname, walls in groups_of(results):
        with open(os.path.join(SITE_DIR, "detail", slug(gname) + ".html"), "w") as f:
            f.write(render_detail(gname, walls, tides, now, now.date()))
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
