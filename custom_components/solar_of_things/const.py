"""Constants for the Solar of Things integration."""

DOMAIN = "solar_of_things"

# ─── Configuration keys ────────────────────────────────────────────────────────
CONF_IOT_TOKEN = "iot_token"          # legacy / advanced manual entry
CONF_STATION_ID = "station_id"
CONF_DEVICE_ID = "device_id"
CONF_TIME_ZONE = "time_zone"

# Credential-based auth (preferred)
CONF_USER_ID = "user_id"       # Siseli account / user-ID login (not email)
CONF_PASSWORD = "password"

# Runtime-stored token state (written back to config entry)
CONF_REFRESH_TOKEN = "refresh_token"
CONF_ACCESS_TOKEN_EXPIRES = "access_token_expires"   # ISO-8601 string
CONF_REFRESH_TOKEN_EXPIRES = "refresh_token_expires" # ISO-8601 string

# ─── API bases ─────────────────────────────────────────────────────────────────
# Both auth and data endpoints live on the production server solar.siseli.com.
# The portal JS bundle embeds both test/prod AppIDs; AppID rBrTRfAPXz is the
# one accepted by solar.siseli.com (confirmed by live API testing 2026-03-07).
API_BASE_URL        = "https://solar.siseli.com"         # data endpoints
API_AUTH_BASE_URL   = "https://solar.siseli.com"         # auth / login endpoints

# ─── Auth endpoints (discovered from portal JS bundle) ─────────────────────────
# The login endpoint requires IOT-Open-AppID signing (see api.py _sign_request).
API_LOGIN           = "/apis/login/account"              # POST + signed headers
API_REFRESH_TOKEN   = "/apis/login/refresh/access/token"  # POST, no token needed

# ─── IOT Open Platform app credentials (embedded in portal umi.js) ────────────
# rBrTRfAPXz is the production AppID accepted by solar.siseli.com.
# JO4DAiNeys is the test AppID (accepted only by test.solar.siseli.com).
IOT_APP_ID          = "rBrTRfAPXz"
IOT_APP_SECRET_ENC  = "I4D0KRr2339z3pQ/at91V9BpFAOe54DaTafwSm6suIQ="

# ─── Data endpoints ────────────────────────────────────────────────────────────
API_TIME_SERIES    = "/apis/deviceState/simple/attribute/keys/history/v1"
API_MONTHLY_SUMMARY = "/apis/stationOverView/stateAttributeSummary/category/yearly"
# Remote device config endpoints (discovered 2026-03-07 from live API testing).
# These accept a plain IOT-Token header (no IOT-Open-Sign) and use the device ID
# as a query parameter.  Write sends one setting key+value per call.
API_SETTINGS_GET   = "/apis/remote/device/configs/cache/get"  # ?deviceId=<id>
API_SETTINGS_SET   = "/apis/remote/device/config/write"       # ?deviceId=<id>
API_DEVICE_LIST    = "/apis/device/list"
# Live "energy flow" endpoint.  GET with ?deviceId=<id>&dataSource=1; values are
# returned under data.deviceAttributeState.fields.  Used as a fallback when the
# historical time-series endpoint yields nothing (see ENERGY_FLOW_RULES below).
API_ENERGY_FLOW    = "/apis/deviceState/simple/energy/flow/v1"

# ─── Token refresh window ──────────────────────────────────────────────────────
# Refresh the access token this many seconds *before* its stated expiry.
# Mirrors the portal JS which refreshes when ≤300 s remain.
TOKEN_REFRESH_LEAD_SECONDS = 300  # 5 minutes

# ─── Sensor keys ───────────────────────────────────────────────────────────────
SENSOR_KEYS = [
    "pvInputPower",
    "acOutputActivePower",
    "batteryDischargeCurrent",
    "batteryChargingCurrent",
    "batteryVoltage",
    "feedInPower",
    "batteryPower",
    "batterySOC",
    "gridPower",
    "loadPower",
]

# ─── Energy-flow fallback mapping ──────────────────────────────────────────────
# Several inverter / WiFi-dongle firmware families never populate the historical
# time-series endpoint (API_TIME_SERIES) that this integration reads by default,
# so every realtime sensor stays "unknown" while the portal shows live data.
# Reported for UWB1, RWB1-0x, JC-62xx, DatouBoss DT-series and EASUN units in
# https://github.com/Conexo-Casa/solar-of-things-ha/issues/7 (and #3, #8, #11,
# #14, #15).  Those devices serve live values from API_ENERGY_FLOW instead,
# under a different set of field names.
#
# Each canonical sensor key maps to an ordered list of rules.  The first rule
# that produces a usable number wins.  A rule is (mode, source_fields, scale):
#   "first" – use the first source field that is present
#   "sum"   – add every source field that is present (multi-string PV inputs)
# `scale` converts the source value into the unit declared in
# SENSOR_DEFINITIONS.
#
# Units for the per-field values below are taken from the sample payload in
# issue #7 (bmsBatteryVoltage 26.6 V, batteryPercentage 100 %, batteryPower 9 W,
# positiveTerminalBatteryCurrent 0.4 A, pv1Power/pv2Power in W).  The kW→W
# scaling for the aggregate flow values (generationPower, load_power) matches
# both the reporter's own reading of the portal and the pre-existing kW→W
# normalisation this integration already applies to acOutputActivePower on the
# time-series path — i.e. this portal reports aggregate power in kW.
ENERGY_FLOW_RULES: dict[str, list[tuple[str, tuple[str, ...], float]]] = {
    "pvInputPower": [
        ("sum", ("pv1Power", "pv2Power", "pv3Power", "pv4Power"), 1.0),
        ("first", ("generationPower",), 1000.0),
    ],
    "batteryVoltage": [
        ("first", ("bmsBatteryVoltage", "positiveTerminalBatteryVoltage"), 1.0),
    ],
    "batterySOC": [
        ("first", ("batteryPercentage", "bmsSOC"), 1.0),
    ],
    "batteryPower": [
        ("first", ("batteryPower",), 1.0),
    ],
    "batteryDischargeCurrent": [
        ("first", ("positiveTerminalBatteryCurrent",), 1.0),
    ],
    "batteryChargingCurrent": [
        ("first", ("negativeTerminalBatteryCurrent",), 1.0),
    ],
    "loadPower": [
        ("first", ("load_power", "loadPower"), 1000.0),
    ],
    "acOutputActivePower": [
        ("first", ("load_power", "loadPower"), 1000.0),
    ],
}

# Fields observed in the issue #7 payload that are deliberately NOT mapped yet.
# Every sample value the reporter captured was zero (the reading was taken at
# night), so the kW-vs-W scale cannot be pinned down.  Guessing wrong here would
# push a value that is 1000x off into the HA Energy dashboard and long-term
# statistics, which is materially worse than leaving the sensor "unknown".
# Revisit once a daytime sample with non-zero values is available.
ENERGY_FLOW_UNVERIFIED: tuple[str, ...] = (
    "aPhaseMainsPower",   # candidate for gridPower (sum of the three phases)
    "bPhaseMainsPower",
    "cPhaseMainsPower",
)

# Canonical keys that indicate the time-series endpoint returned usable realtime
# data.  If none of these are present the energy-flow fallback is attempted.
REALTIME_PROBE_KEYS: tuple[str, ...] = (
    "pvInputPower",
    "acOutputActivePower",
    "batteryVoltage",
    "batterySOC",
    "batteryChargingCurrent",
    "batteryDischargeCurrent",
    "feedInPower",
)

SENSOR_DEFINITIONS = {
    "pvInputPower": {
        "name": "PV Input Power",
        "unit": "W",
        "device_class": "power",
        "icon": "mdi:solar-power",
    },
    "acOutputActivePower": {
        "name": "AC Output Power",
        "unit": "W",
        "device_class": "power",
        "icon": "mdi:power-plug",
    },
    "batteryDischargeCurrent": {
        "name": "Battery Discharge Current",
        "unit": "A",
        "device_class": "current",
        "icon": "mdi:battery-arrow-down",
    },
    "batteryChargingCurrent": {
        "name": "Battery Charging Current",
        "unit": "A",
        "device_class": "current",
        "icon": "mdi:battery-arrow-up",
    },
    "batteryVoltage": {
        "name": "Battery Voltage",
        "unit": "V",
        "device_class": "voltage",
        "icon": "mdi:battery",
    },
    "batteryPower": {
        "name": "Battery Power",
        "unit": "W",
        "device_class": "power",
        "icon": "mdi:battery-charging",
    },
    "batterySOC": {
        "name": "Battery State of Charge",
        "unit": "%",
        "device_class": "battery",
        "icon": "mdi:battery",
    },
    "feedInPower": {
        "name": "Grid Feed-in Power",
        "unit": "W",
        "device_class": "power",
        "icon": "mdi:transmission-tower-export",
    },
    "gridPower": {
        "name": "Grid Import Power",
        "unit": "W",
        "device_class": "power",
        "icon": "mdi:transmission-tower-import",
    },
    "loadPower": {
        "name": "Load Power",
        "unit": "W",
        "device_class": "power",
        "icon": "mdi:home-lightning-bolt",
    },
    # Monthly summary sensors
    "monthly_pv_generated": {
        "name": "Monthly PV Generated",
        "unit": "kWh",
        "device_class": "energy",
        "icon": "mdi:solar-power",
    },
    "monthly_grid_import": {
        "name": "Monthly Grid Import",
        "unit": "kWh",
        "device_class": "energy",
        "icon": "mdi:transmission-tower-import",
    },
    "monthly_total_consumption": {
        "name": "Monthly Total Consumption",
        "unit": "kWh",
        "device_class": "energy",
        "icon": "mdi:home-lightning-bolt",
    },
    "monthly_solar_percentage": {
        "name": "Monthly Solar Coverage",
        "unit": "%",
        "icon": "mdi:percent",
    },
}
