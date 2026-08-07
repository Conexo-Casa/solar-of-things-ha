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
# Portal "Batch Read": asks the inverter to report its config, then poll the
# details endpoint with the returned batch id.
API_SETTINGS_READ         = "/apis/remote/device/configs/read"          # ?deviceId=<id>
API_SETTINGS_READ_DETAILS = "/apis/remote/device/configs/read/details"  # ?batchReadId=<id>
API_DEVICE_LIST    = "/apis/device/list"
API_STATE_LATEST   = "/apis/deviceState/simple/state/latest/v1"

# ─── Token refresh window ──────────────────────────────────────────────────────
# Refresh the access token this many seconds *before* its stated expiry.
# Mirrors the portal JS which refreshes when ≤300 s remain.
TOKEN_REFRESH_LEAD_SECONDS = 300  # 5 minutes

# ─── Attribute names ───────────────────────────────────────────────────────────
# All names below were captured from a live PI30 / VMIII inverter on
# solar.siseli.com (see API_CAPTURE.md).  Lookups match case-insensitively and
# try each candidate in order, so a model that uses a different name only needs
# that name appended to the relevant list.
#
# The portal uses three different name spaces for the same control:
#
#   read  (live)   state/latest field       e.g. "chargerSourcePriority"
#   read  (cache)  remote-config cache key  e.g. "settingDeviceChargerPriority"
#   write          config/write key         e.g. "settingDeviceChargerPriority"
#
# The cache is only populated after a remote read/write round-trip, so the live
# snapshot is what the integration reads and the write keys are separate.

# Keys accepted by POST /apis/remote/device/config/write.
SETTING_KEY_CANDIDATES: dict[str, list[str]] = {
    "outputSourcePriority": [
        "settingDeviceOutputSourcePriority",
        # Pre-2.6 name, kept so a firmware that still accepts it keeps working.
        "outputSourcePrioritySetting",
    ],
    "chargerSourcePriority": [
        "settingDeviceChargerPriority",
        "chargerSourcePrioritySetting",
    ],
    "gridFeedIn": ["setGridConnectionStatus"],
    "buzzer": ["buzzerEnabled"],
    "overloadBypass": ["overloadBypass"],
    "overLoadRestart": ["overLoadRestartSetting"],
    "overTemperatureRestart": ["overTemperatureRestartSetting"],
    "lcdBacklight": ["lcdBackLightControlSetting"],
    "lcdReturnToDefaultPage": ["lcdReturnToDefaultPageSetting"],
    "faultCodeRecord": ["faultCodeRecordSetting"],
    "alarmOnPrimarySourceInterrupt": ["alarmOnWhenPrimarySourceInterruptSetting"],
    "equalizationVoltage": ["setBatteryEqualizationVoltage"],
    "equalizationPeriod": ["setBatteryEqualizationPeriod"],
    "equalizationOverTime": ["setBatteryEqualizationOverTime"],
    "outputRatingFrequency": ["settingInverterOutputRatingFrequency"],
}

# Field names in GET /apis/deviceState/simple/state/latest/v1 — the live
# snapshot, and the source every control reads its current value from.
STATE_KEY_CANDIDATES: dict[str, list[str]] = {
    "outputSourcePriority": ["outputSourcePriority", "outputSourcePrioritySetting"],
    "chargerSourcePriority": ["chargerSourcePriority", "chargeSourcePriority"],
    "gridFeedIn": ["solarFeedToGrid", "gridConnectionStatus", "feedInGrid"],
    "acInputRange": ["inputVoltageRange", "acInputRange"],
    "buzzer": ["buzzerSetup", "buzzerEnabled"],
    "overloadBypass": ["overloadBypassFunction", "overloadBypass"],
    "overLoadRestart": ["overLoadRestart"],
    "overTemperatureRestart": ["overTemperatureRestart"],
    "lcdBacklight": ["lcdBackLightControl"],
    "lcdReturnToDefaultPage": ["lcdReturnToDefaultPage"],
    "faultCodeRecord": ["faultCodeRecord"],
    "alarmOnPrimarySourceInterrupt": ["alarmOnWhenPrimarySourceInterrupt"],
    "equalizationVoltage": ["batteryEqualizationVoltage"],
    "equalizationPeriod": ["equalizationPeriod"],
    "equalizationOverTime": ["equalizationOverTime"],
    "outputRatingFrequency": ["acOutputRatingFrequency"],
}

# Telemetry keys the time-series endpoint may not return for a given model.
# Filled from the state snapshot instead; each entry is (candidates, kind), and
# kind drives unit normalisation ("power" → W, "energy" → kWh, None → as-is)
# using the unit the snapshot reports alongside the value.
TELEMETRY_STATE_FALLBACKS: dict[str, tuple[list[str], str | None]] = {
    # PI30/VMIII reports PV power as generationPower in kW.
    "pvInputPower": (
        ["pvInputPower", "generationPower", "pvChargingPower", "PV1ChargingPower"],
        "power",
    ),
    "acOutputActivePower": (
        ["acOutputActivePower", "acOutputPower", "outputActivePower"],
        "power",
    ),
    "feedInPower": (
        ["feedInPower", "gridFeedInPower", "feedInActivePower", "onGridPower"],
        "power",
    ),
    "batteryVoltage": (["batteryVoltage"], None),
    "batteryChargingCurrent": (["batteryChargingCurrent"], None),
    "batteryDischargeCurrent": (["batteryDischargeCurrent"], None),
    # No batterySOC on PI30 — it publishes batteryCapacity / batteryPercentage.
    "batterySOC": (["batterySOC", "batteryCapacity", "batteryPercentage"], None),
}

# ─── Control option maps ───────────────────────────────────────────────────────
# Output Source Priority.  Read from the state field `outputSourcePriority`,
# written as `settingDeviceOutputSourcePriority`; both use the PI30 POP codes.
OUTPUT_PRIORITY_BY_VALUE: dict[int, str] = {
    0: "Utility First (USO)",
    1: "Solar First (SUB)",
    2: "Solar+Battery First (SBU)",
}
OUTPUT_PRIORITY_OPTIONS: list[str] = list(OUTPUT_PRIORITY_BY_VALUE.values())

# Alias table for resolving a text value/valueDisplay onto an option.  Keys are
# normalised (lowercase, non-alphanumerics collapsed to single spaces).  The
# "->" strings are the live labels the portal returns.
OUTPUT_PRIORITY_ALIASES: dict[str, str] = {
    "uso": OUTPUT_PRIORITY_BY_VALUE[0],
    "usb": OUTPUT_PRIORITY_BY_VALUE[0],
    "utility": OUTPUT_PRIORITY_BY_VALUE[0],
    "utility first": OUTPUT_PRIORITY_BY_VALUE[0],
    "utilitysolarbat": OUTPUT_PRIORITY_BY_VALUE[0],
    "mains power photovoltaic battery": OUTPUT_PRIORITY_BY_VALUE[0],
    "sub": OUTPUT_PRIORITY_BY_VALUE[1],
    "solar first": OUTPUT_PRIORITY_BY_VALUE[1],
    "solarutilitybat": OUTPUT_PRIORITY_BY_VALUE[1],
    "photovoltaic mains power battery": OUTPUT_PRIORITY_BY_VALUE[1],
    "sbu": OUTPUT_PRIORITY_BY_VALUE[2],
    "battery first": OUTPUT_PRIORITY_BY_VALUE[2],
    "solarbatutility": OUTPUT_PRIORITY_BY_VALUE[2],
    "solar battery first": OUTPUT_PRIORITY_BY_VALUE[2],
    "photovoltaic battery mains power": OUTPUT_PRIORITY_BY_VALUE[2],
}

# Charger Source Priority.  Read from the state field `chargerSourcePriority`,
# written as `settingDeviceChargerPriority`.  These are the PI30 PCP codes —
# **four** of them, not three.  Releases before 2.6.0 mapped 0/1/2 onto
# CSO/SNU/OSO, which does not match what the device reports or accepts.
CHARGER_PRIORITY_BY_VALUE: dict[int, str] = {
    0: "Utility First",
    1: "Solar First",
    2: "Solar + Utility",
    3: "Solar Only",
}
CHARGER_PRIORITY_OPTIONS: list[str] = list(CHARGER_PRIORITY_BY_VALUE.values())

CHARGER_PRIORITY_ALIASES: dict[str, str] = {
    "utility first": CHARGER_PRIORITY_BY_VALUE[0],
    "for utility first": CHARGER_PRIORITY_BY_VALUE[0],
    "utility": CHARGER_PRIORITY_BY_VALUE[0],
    "solar first": CHARGER_PRIORITY_BY_VALUE[1],
    "for solar first": CHARGER_PRIORITY_BY_VALUE[1],
    "snu": CHARGER_PRIORITY_BY_VALUE[1],
    "solar utility": CHARGER_PRIORITY_BY_VALUE[2],
    "solar and utility": CHARGER_PRIORITY_BY_VALUE[2],
    "for solar and utility charging": CHARGER_PRIORITY_BY_VALUE[2],
    "cso": CHARGER_PRIORITY_BY_VALUE[2],
    "solar only": CHARGER_PRIORITY_BY_VALUE[3],
    "only solar": CHARGER_PRIORITY_BY_VALUE[3],
    "only solar permitted": CHARGER_PRIORITY_BY_VALUE[3],
    "for only solar charging": CHARGER_PRIORITY_BY_VALUE[3],
    "oso": CHARGER_PRIORITY_BY_VALUE[3],
}

# ─── Boolean controls ──────────────────────────────────────────────────────────
# Switches that map onto a single enable/disable setting.  `on_value` /
# `off_value` are what the write endpoint expects (strings — the portal sends
# enum values quoted); `on_codes` are the state-snapshot codes that mean "on".
BOOLEAN_CONTROLS: dict[str, dict] = {
    "gridFeedIn": {
        "name": "Solar Feed to Grid",
        "icon": "mdi:transmission-tower-export",
        "on_value": "1",
        "off_value": "0",
        "on_codes": {1},
    },
    "buzzer": {
        "name": "Buzzer",
        "icon": "mdi:volume-high",
        "on_value": "1",
        "off_value": "0",
        "on_codes": {1},
    },
    "overloadBypass": {
        "name": "Overload Bypass",
        "icon": "mdi:transmission-tower",
        "on_value": "1",
        "off_value": "0",
        "on_codes": {1},
    },
    "overLoadRestart": {
        "name": "Overload Restart",
        "icon": "mdi:restart",
        "on_value": "1",
        "off_value": "0",
        "on_codes": {1},
    },
    "overTemperatureRestart": {
        "name": "Over-temperature Restart",
        "icon": "mdi:restart-alert",
        "on_value": "1",
        "off_value": "0",
        "on_codes": {1},
    },
    "lcdBacklight": {
        "name": "LCD Backlight",
        "icon": "mdi:monitor",
        "on_value": "1",
        "off_value": "0",
        "on_codes": {1},
    },
    "lcdReturnToDefaultPage": {
        "name": "LCD Return to Default Page",
        "icon": "mdi:monitor-arrow-down",
        "on_value": "1",
        "off_value": "0",
        "on_codes": {1},
    },
    "faultCodeRecord": {
        "name": "Fault Code Recording",
        "icon": "mdi:clipboard-alert",
        "on_value": "1",
        "off_value": "0",
        "on_codes": {1},
    },
    "alarmOnPrimarySourceInterrupt": {
        "name": "Alarm on Primary Source Interrupt",
        "icon": "mdi:bell-alert",
        "on_value": "1",
        "off_value": "0",
        "on_codes": {1},
    },
}

# ─── Numeric controls ──────────────────────────────────────────────────────────
# Writable numbers, with the ranges the portal's own inputs enforce.  The
# battery charge/discharge/grid-charge limits shipped before 2.6.0 are gone:
# no such keys exist on PI30/VMIII, so those entities could never read or write.
NUMBER_CONTROLS: dict[str, dict] = {
    "equalizationVoltage": {
        "name": "Battery Equalization Voltage",
        "icon": "mdi:battery-heart-variant",
        "min": 20.0,
        "max": 60.0,
        "step": 0.1,
        "unit": "V",
        "device_class": "voltage",
        "numeric": True,
    },
    "equalizationPeriod": {
        "name": "Battery Equalization Period",
        "icon": "mdi:calendar-sync",
        "min": 0,
        "max": 99,
        "step": 1,
        "unit": "d",
        "numeric": True,
    },
    "equalizationOverTime": {
        "name": "Battery Equalization Timeout",
        "icon": "mdi:timer-sand",
        "min": 0,
        "max": 900,
        "step": 5,
        "unit": "min",
        "numeric": True,
    },
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
