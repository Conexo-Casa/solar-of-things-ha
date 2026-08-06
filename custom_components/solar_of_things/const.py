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
API_STATE_LATEST   = "/apis/deviceState/simple/state/latest/v1"

# ─── Token refresh window ──────────────────────────────────────────────────────
# Refresh the access token this many seconds *before* its stated expiry.
# Mirrors the portal JS which refreshes when ≤300 s remain.
TOKEN_REFRESH_LEAD_SECONDS = 300  # 5 minutes

# ─── Attribute-key candidates ──────────────────────────────────────────────────
# Inverter models expose the same measurement under different attribute names
# (and the state endpoint is inconsistent about capitalisation), so every lookup
# tries a list of candidates case-insensitively.  Add a name here when a new
# model reports one we do not know about yet — see API_CAPTURE.md for how to
# find out which names your device actually uses.

# Setting keys written through /apis/remote/device/config/write.
SETTING_KEY_CANDIDATES: dict[str, list[str]] = {
    "outputSourcePriority": [
        "outputSourcePrioritySetting",
        "outputSourcePriority",
        "outputPrioritySetting",
        "outputPriority",
    ],
    "chargerSourcePriority": [
        "chargerSourcePrioritySetting",
        "chargerSourcePriority",
        "chargeSourcePrioritySetting",
        "chargerPrioritySetting",
        "chargingSourcePriority",
    ],
    "acInputRange": [
        "acInputRangeSetting",
        "acInputRange",
        "inputVoltageRangeSetting",
    ],
    "gridFeedIn": [
        "batteryPowerLimitingSetting",
        "feedInGridSetting",
        "gridFeedInSetting",
    ],
    "batteryChargeLimit": ["batteryChargeLimit", "batteryChargeLimitSetting"],
    "batteryDischargeLimit": ["batteryDischargeLimit", "batteryDischargeLimitSetting"],
    "gridChargeLimit": ["gridChargeLimit", "gridChargeLimitSetting", "maxUtilityChargingCurrent"],
}

# Live-snapshot field names from /apis/deviceState/simple/state/latest/v1.
# The snapshot carries the *current* device state, which is what the selects and
# switches read back — unlike the settings cache, which only holds values that
# were previously written through the portal.
STATE_KEY_CANDIDATES: dict[str, list[str]] = {
    "outputSourcePriority": [
        "outputSourcePriority",
        "outputSourcePrioritySetting",
        "outputPriority",
        "outputSourcePriorityStatus",
        "outputMode",
    ],
    "chargerSourcePriority": [
        "chargerSourcePriority",
        "chargerSourcePrioritySetting",
        "chargeSourcePriority",
        "chargerPriority",
        "chargingSourcePriority",
    ],
    "acInputRange": ["acInputRange", "acInputRangeSetting", "inputVoltageRange"],
    "gridFeedIn": [
        "batteryPowerLimiting",
        "batteryPowerLimitingSetting",
        "feedInGrid",
        "gridFeedIn",
    ],
    "batteryChargeLimit": ["batteryChargeLimit", "batteryChargeLimitSetting"],
    "batteryDischargeLimit": ["batteryDischargeLimit", "batteryDischargeLimitSetting"],
    "gridChargeLimit": ["gridChargeLimit", "maxUtilityChargingCurrent"],
}

# Telemetry keys that the time-series endpoint may not return for a given model.
# When a key is missing there we fall back to the state snapshot, which reports
# every attribute the device publishes.  Each entry is (candidates, kind); kind
# drives unit normalisation ("power" → W, "energy" → kWh, None → as-is).
TELEMETRY_STATE_FALLBACKS: dict[str, tuple[list[str], str | None]] = {
    "pvInputPower": (
        ["pvInputPower", "pvChargingPower", "PV1ChargingPower", "generationPower"],
        "power",
    ),
    "acOutputActivePower": (
        ["acOutputActivePower", "acOutputPower", "outputActivePower", "loadActivePower"],
        "power",
    ),
    "feedInPower": (
        [
            "feedInPower",
            "gridFeedInPower",
            "feedInActivePower",
            "acFeedInPower",
            "feedbackPower",
            "gridExportPower",
            "exportPower",
            "onGridPower",
            "gridConnectedPower",
        ],
        "power",
    ),
    "batteryVoltage": (["batteryVoltage", "batteryTerminalVoltage"], None),
    "batteryChargingCurrent": (
        ["batteryChargingCurrent", "batteryChargeCurrent"],
        None,
    ),
    "batteryDischargeCurrent": (
        ["batteryDischargeCurrent", "batteryDischargingCurrent"],
        None,
    ),
    "batterySOC": (
        ["batterySOC", "batteryCapacity", "batteryPercentage", "soc"],
        None,
    ),
}

# ─── Control option maps ───────────────────────────────────────────────────────
# Output Source Priority (outputSourcePrioritySetting): 0=USO, 1=SUB, 2=SBU.
OUTPUT_PRIORITY_BY_VALUE: dict[int, str] = {
    0: "Utility First (USO)",
    1: "Solar First (SUB)",
    2: "Solar+Battery First (SBU)",
}
OUTPUT_PRIORITY_OPTIONS: list[str] = list(OUTPUT_PRIORITY_BY_VALUE.values())

# Alias table for resolving a text value/valueDisplay onto an option.  Keys are
# normalised (lowercase, non-alphanumerics collapsed to single spaces).
OUTPUT_PRIORITY_ALIASES: dict[str, str] = {
    "uso": OUTPUT_PRIORITY_BY_VALUE[0],
    "utility": OUTPUT_PRIORITY_BY_VALUE[0],
    "utility first": OUTPUT_PRIORITY_BY_VALUE[0],
    "utility priority": OUTPUT_PRIORITY_BY_VALUE[0],
    "grid first": OUTPUT_PRIORITY_BY_VALUE[0],
    "sub": OUTPUT_PRIORITY_BY_VALUE[1],
    "solar first": OUTPUT_PRIORITY_BY_VALUE[1],
    "solar priority": OUTPUT_PRIORITY_BY_VALUE[1],
    "solar utility battery": OUTPUT_PRIORITY_BY_VALUE[1],
    "sbu": OUTPUT_PRIORITY_BY_VALUE[2],
    "battery first": OUTPUT_PRIORITY_BY_VALUE[2],
    "solar battery first": OUTPUT_PRIORITY_BY_VALUE[2],
    "solar battery utility": OUTPUT_PRIORITY_BY_VALUE[2],
}

# Charger Source Priority (chargerSourcePrioritySetting): 0=CSO, 1=SNU, 2=OSO.
CHARGER_PRIORITY_BY_VALUE: dict[int, str] = {
    0: "Solar + Utility (CSO)",
    1: "Solar First (SNU)",
    2: "Solar Only (OSO)",
}
CHARGER_PRIORITY_OPTIONS: list[str] = list(CHARGER_PRIORITY_BY_VALUE.values())

CHARGER_PRIORITY_ALIASES: dict[str, str] = {
    "cso": CHARGER_PRIORITY_BY_VALUE[0],
    "solar utility": CHARGER_PRIORITY_BY_VALUE[0],
    "solar and utility": CHARGER_PRIORITY_BY_VALUE[0],
    "utility first": CHARGER_PRIORITY_BY_VALUE[0],
    "snu": CHARGER_PRIORITY_BY_VALUE[1],
    "solar first": CHARGER_PRIORITY_BY_VALUE[1],
    "solar priority": CHARGER_PRIORITY_BY_VALUE[1],
    "oso": CHARGER_PRIORITY_BY_VALUE[2],
    "solar only": CHARGER_PRIORITY_BY_VALUE[2],
    "only solar": CHARGER_PRIORITY_BY_VALUE[2],
}

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
