from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from math import acos, asin, atan2, cos, degrees, floor, radians, sin, tan


@dataclass(frozen=True)
class SunPosition:
    azimuth_deg: float
    altitude_deg: float


def _julian_day(moment: datetime) -> float:
    utc = moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    y, m = utc.year, utc.month
    d = utc.day + (utc.hour + utc.minute / 60.0 + utc.second / 3600.0) / 24.0
    if m <= 2:
        y -= 1
        m += 12
    a = floor(y / 100)
    b = 2 - a + floor(a / 4)
    return floor(365.25 * (y + 4716)) + floor(30.6001 * (m + 1)) + d + b - 1524.5


def solar_position(moment: datetime, lat_deg: float, lon_deg: float) -> SunPosition:
    # NOAA-Sonnenstand. Azimut: 0° Norden, 90° Osten, 180° Süden.
    jd = _julian_day(moment)
    t = (jd - 2451545.0) / 36525.0
    l0 = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360.0
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    c = sin(radians(m)) * (1.914602 - t * (0.004817 + 0.000014 * t))
    c += sin(radians(2 * m)) * (0.019993 - 0.000101 * t) + sin(radians(3 * m)) * 0.000289
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t
    app_long = true_long - 0.00569 - 0.00478 * sin(radians(omega))
    eps0 = 23.0 + (26.0 + ((21.448 - t * (46.815 + t * (0.00059 - t * 0.001813)))) / 60.0) / 60.0
    eps = eps0 + 0.00256 * cos(radians(omega))
    decl = asin(sin(radians(eps)) * sin(radians(app_long)))
    y = tan(radians(eps) / 2.0) ** 2
    eq = 4.0 * degrees(y * sin(2 * radians(l0)) - 2 * e * sin(radians(m)) + 4 * e * y * sin(radians(m)) * cos(2 * radians(l0)) - 0.5 * y * y * sin(4 * radians(l0)) - 1.25 * e * e * sin(2 * radians(m)))
    minutes = moment.hour * 60.0 + moment.minute + moment.second / 60.0
    offset = moment.utcoffset().total_seconds() / 60.0 if moment.utcoffset() else 0.0
    tst = (minutes + eq + 4.0 * lon_deg - offset) % 1440.0
    ha = radians(tst / 4.0 - 180.0)
    lat = radians(lat_deg)
    zenith_cos = sin(lat) * sin(decl) + cos(lat) * cos(decl) * cos(ha)
    zenith = acos(max(-1.0, min(1.0, zenith_cos)))
    altitude = 90.0 - degrees(zenith)
    az = atan2(sin(ha), cos(ha) * sin(lat) - tan(decl) * cos(lat))
    return SunPosition((degrees(az) + 180.0) % 360.0, altitude)


def daylight_times(date_dt: datetime, lat_deg: float, lon_deg: float) -> tuple[time, time]:
    samples = []
    base = date_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    for minute in range(0, 24 * 60, 5):
        m = base.replace(hour=minute // 60, minute=minute % 60)
        samples.append((m, solar_position(m, lat_deg, lon_deg).altitude_deg))
    above = [m for m, alt in samples if alt > -0.833]
    if not above:
        return time(12, 0), time(12, 0)
    return above[0].time(), above[-1].time()


def season_date(year: int, season_key: str) -> datetime:
    dates = {
        "spring": (3, 20),
        "summer": (6, 21),
        "autumn": (9, 22),
        "winter": (12, 21),
    }
    month, day = dates.get(season_key, dates["summer"])
    return datetime(year, month, day, 12, 0)
