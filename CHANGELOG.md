# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.6.0] - 2026-08-07

Rebuilt against captured live traffic from a PI30 / VMIII inverter on
solar.siseli.com, which showed several of the API assumptions in earlier
releases to be wrong.

### Fixed
- **Writes never reached the device.** The remote-config write body must be
  `{"id": <deviceId>, "key": …, "value": …}`. Earlier releases sent `deviceId`
  instead of `id`; the endpoint answers `code: 0` ("Success") and does nothing,
  so every control appeared to work while changing nothing on the inverter.
- **Writes used the wrong key names.** Reads and writes live in two different
  name spaces: the live snapshot reports `outputSourcePriority` /
  `chargerSourcePriority`, but the write endpoint expects
  `settingDeviceOutputSourcePriority` / `settingDeviceChargerPriority`. Enum
  values are sent as strings, as the portal sends them.
- **Charger Source Priority had the wrong options.** It is the PI30 `PCP` code
  with **four** values — 0 Utility First, 1 Solar First, 2 Solar + Utility,
  3 Solar Only. The previous three-option CSO/SNU/OSO map matched neither what
  the device reports nor what it accepts, so an inverter set to "Solar Only" (3)
  could not be displayed at all.
- **Grid Feed-in Power.** Off-grid models publish no feed-in measurement, only a
  `solarFeedToGrid` permit flag. When feed-in is disabled the sensor now reports
  0 W — true, and it makes the derived Grid Import figure correct — instead of
  `unknown`.
- **Telemetry attribute names** corrected to the ones the device actually
  publishes: PV power is `generationPower` (kW), battery SOC is
  `batteryCapacity`, and AC output power is reported in kW.
- **"PV Generated" was mislabelled** — the device's own label for
  `pvGeneratedEnergyOfDay` is "Total photovoltaic power generation". Renamed to
  *PV Total Production*.

### Removed
- **Grid Charging (AC Input Range) switch.** The device reports
  `inputVoltageRange` (Appliance / UPS) but the portal exposes no write key for
  it, so the switch could not change anything. It is now the read-only
  *Input Voltage Range* diagnostic sensor.
- **Battery Charge Limit, Battery Discharge Limit and Grid Charge Limit.** No
  such attributes exist on PI30/VMIII and there are no write keys for them —
  the sliders were permanently unavailable and their writes went nowhere. The
  current limits the device *does* report are exposed as diagnostic sensors.

### Added
- **Ten switches** for the settings the device genuinely accepts: Solar Feed to
  Grid, Buzzer, Overload Bypass, Overload Restart, Over-temperature Restart,
  LCD Backlight, LCD Return to Default Page, Fault Code Recording and Alarm on
  Primary Source Interrupt, alongside Backup Mode.
- **Three writable numbers**: battery equalization voltage, period and timeout.
- **New sensors**: PV2 voltage/current/power, battery float and bulk voltage,
  max charging / utility-charging / discharging current, AC and solar charging
  status, input voltage range, model, serial number and firmware version.
- `request_config_read()` / `fetch_config_read_details()` wrap the portal's
  "Batch Read", which asks the inverter to report its stored configuration.

### Changed
- Control entities are now table-driven (`BOOLEAN_CONTROLS`, `NUMBER_CONTROLS`,
  `SETTING_KEY_CANDIDATES`, `STATE_KEY_CANDIDATES` in `const.py`) — adding a
  control is a table entry rather than a new entity class.
- Tests cover the captured payload directly: the live snapshot resolves every
  core measurement, and the write path is asserted byte-for-byte against what
  the portal sends (52 tests, no Home Assistant install required).

---

## [2.5.0] - 2026-08-06

### Fixed
- **Charger Source Priority and Output Source Priority selects showed
  `unknown`.** Both read their current value only from the remote-config cache
  (`/apis/remote/device/configs/cache/get`), which holds just the keys that have
  previously been *written* through the portal — on an account that has never
  used remote control it comes back empty. They now read the live state snapshot
  (`/apis/deviceState/simple/state/latest/v1`) first and fall back to the cache,
  and they accept every value shape the API uses: an integer code, a numeric
  string, an abbreviation (`"SBU"`) or a full label.
- **Grid Feed-in Power showed `unknown`.** The history endpoint only returns the
  attribute names it was asked for and that the model records, so models that
  publish feed-in under another name returned nothing. Missing telemetry keys
  are now filled from the state snapshot, with units normalised (kW → W), and
  the derived values (`batteryPower`, `gridPower`, `loadPower`) are recomputed
  afterwards so they benefit from the recovered readings.
- **Number entities (charge/discharge/grid-charge limits) were unavailable.**
  They returned the raw settings entry — a `{"key": …, "value": …}` dict —
  instead of its value.
- **Switches now read back from the live snapshot too**, and understand word
  renderings (`"ON"`, `"Appliance"`) as well as integer codes.
- **State sensors match attribute names case-insensitively**, fixing readings
  lost to the snapshot's inconsistent capitalisation (`PV1InputVoltage` vs
  `pv1InputCurrent`), and scale values using the unit the API reports.

### Added
- **Diagnostics support** — *Settings → Devices & Services → Solar of Things →
  ⋮ → Download diagnostics* dumps the raw payloads with credentials, tokens and
  the account ID redacted, including every attribute name the device publishes
  and how each contested value resolved.
- **`tools/dump_solar_api.py`** — standalone script that logs in and prints the
  attribute names from all three endpoints, for capturing the same data outside
  Home Assistant.
- **[API_CAPTURE.md](API_CAPTURE.md)** — four ways to capture the data needed to
  map an `unknown` entity, and how to add a new attribute name.
- Priority selects expose `source`, `api_key`, `raw_value` and `raw_display` as
  entity attributes, and log a warning (once per distinct value) when a value
  cannot be mapped onto a known option.
- Per-device attribute names are logged at debug level on the first poll.

### Changed
- All attribute names now live in candidate lists in `const.py`
  (`STATE_KEY_CANDIDATES`, `SETTING_KEY_CANDIDATES`,
  `TELEMETRY_STATE_FALLBACKS`), matched case-insensitively — supporting a new
  inverter model is a one-line addition there.
- The option ↔ integer maps are defined once in `const.py` and inverted for the
  write path, so read-back and write cannot drift apart.
- `tests/` runs without Home Assistant installed (36 new tests covering payload
  shapes, unit scaling and option resolution); CI now fails on test failures
  instead of tolerating them.

---

## [2.4.2] - 2026-05-31

### Security / Quality
- **Removed stale root-level duplicate files** (`__init__.py`, `api.py`, `config_flow.py`,
  `const.py`, `sensor.py`, `number.py`, `select.py`, `switch.py`, `manifest.json`,
  `strings.json`, `translations/`) — these were leftover copies from before the
  v2.4.0 HACS restructure. They confused CodeQL (triggering duplicate alerts on
  deleted code), could mislead HACS, and were dead code.
- **GitHub Actions `permissions` hardened** — `validate.yml` and `codeql.yml` now
  declare `permissions: contents: read` (principle of least privilege). Resolves
  CodeQL alert #1 *(actions/missing-workflow-permissions)*.
- **CodeQL workflow added** (`.github/workflows/codeql.yml`) — explicit weekly
  security scan scoped to `custom_components/solar_of_things/` only, with a
  documented exclusion for the protocol-mandated MD5 pre-hash.
- **CodeQL config added** (`.github/codeql-config.yml`) — scopes analysis to the
  integration source, ignores `dist/` and `tests/`, and documents the
  `py/weak-sensitive-data-hashing` suppression rationale.
- **MD5 suppression documented in source** (`api.py` line ~315) — added
  `# noqa: S324` and an explanatory comment. The Siseli API rejects plaintext
  passwords (returns error code 7); MD5(password) is a protocol requirement of
  the upstream service transmitted over HTTPS. This is not password storage and
  cannot be changed without breaking authentication.
- **`validate.yml` fixed** — was still pointing at root-level `.py` files and
  `manifest.json` (which no longer exist). Now correctly validates
  `custom_components/solar_of_things/`. Added `integration_type` and
  `homeassistant` to the manifest required-key check.
- **`release.yml` fixed** — was building the ZIP from root-level files. Now zips
  `custom_components/solar_of_things/` correctly.

---

## [2.4.1] - 2026-05-31

### Fixed
- **Thread-safety crash** (HA warning: *"calls hass.config_entries.async_update_entry
  from a thread other than the event loop"*) — the `on_token_refreshed` callback was
  decorated `@callback` but invoked from a background executor thread during token
  refresh. `async_update_entry` can only be called from the event loop. Fixed by
  wrapping the update in a nested `@callback` and scheduling it with
  `hass.loop.call_soon_threadsafe()`. Resolves crash/data-corruption risk reported
  in issue #2.

- **Token refresh 404** (*"token refresh request failed: 404 Not Found for url:
  https://solar.siseli.com/login/refresh/access/token"*) — the refresh endpoint
  was missing the `/apis/` prefix. Corrected to
  `/apis/login/refresh/access/token`. This caused every token refresh to fail
  silently, eventually leading to expired tokens and "Unknown" sensor values.
  Resolves the sensor data issue reported in issue #2.

- **`via_device` warning** (*"calls device_registry.async_get_or_create referencing
  a non existing via_device … This will stop working in Home Assistant 2025.12.0"*)
  — the station hub device was never explicitly registered in the device registry,
  so per-device entities' `via_device` reference pointed to a non-existent device.
  The station device is now registered in `async_setup_entry` before
  `async_forward_entry_setups` is called. Resolves issue #2 comments from Gaz93
  and andreasantorelli12-hue.

---

## [2.4.0] - 2026-05-30

### Added
- **HACS-compliant directory structure** — all integration files now live under
  `custom_components/solar_of_things/` as required by HACS. Installing via HACS
  or manual copy now works without any path adjustments.
- **Brand asset** — `brand/icon.png` added so the integration displays an icon
  in the HACS store and HA Integrations page.
- **Sensor translation keys** — all 14 sensors now use `translation_key` +
  `has_entity_name = True`, enabling future multi-language support and aligning
  with HA quality-scale best practices.

### Fixed
- **Missing API methods crash** — `number.py` called `api.set_battery_charge_limit()`,
  `api.set_battery_discharge_limit()`, and `api.set_grid_charge_limit()` which did not
  exist in `api.py`. Interacting with any number slider raised an `AttributeError`.
  All three methods are now implemented.
- **Select entity state mismatch** — `strings.json` defined state keys
  (`self_use`, `time_of_use`, `backup`, `grid_tie`, `off_grid`) that did not match
  the actual API option strings (`Utility First (USO)`, `Solar First (SUB)`, etc.).
  State translations now match the real API values exactly.
- **Device registry duplicates** — sensors used `(DOMAIN, station_id, device_id)`
  as the device identifier while switches, selects, and numbers used the same tuple
  but in a different evaluation path. All device-level entities now use
  `(DOMAIN, device_id)` and station-level entities use `(DOMAIN, station_id)`,
  eliminating duplicate device entries in the device registry.
- **Re-auth crash on HA 2024.x** — `async_step_reauth` declared `entry_data` as
  a required argument; HA 2024+ calls it with no argument. Made the parameter
  optional (`entry_data: dict | None = None`).

### Changed
- `manifest.json`: added `integration_type: hub` (required since HA 2023.6),
  set `homeassistant: "2023.6.0"` minimum version, updated `codeowners`.
- `hacs.json`: updated `homeassistant` minimum to `2023.6.0`, removed legacy
  `zip_release` / `filename` / `domains` fields incompatible with the new layout.
- `strings.json` / `translations/en.json`: corrected select state keys; added
  full sensor translation entries (previously absent).
- `.gitignore`: added `graphify-out/` to exclude local knowledge-graph cache.

---

## [2.3.3] - 2026-03-07

### Fixed
- **404 Not Found on device settings** — replaced incorrect settings endpoints with
  the correct remote-config API endpoints discovered from the live portal JS bundle:
  - **Read**: `POST /apis/remote/device/configs/cache/get?deviceId=<id>`
  - **Write**: `POST /apis/remote/device/config/write?deviceId=<id>`
- `select.py` — Operating Mode and Battery Priority selects now use real API keys
  (`outputSourcePrioritySetting`, `chargerSourcePrioritySetting`) with correct
  integer value mappings (USO/SUB/SBU, CSO/SNU/OSO).
- `switch.py` — all three switches map to correct API setting keys.

---

## [2.3.2] - 2026-03-07

### Fixed
- `fetch_settings` AttributeError — added class-level alias so both `get_device_settings`
  and `fetch_settings` work.
- Five missing control helper methods on `SolarOfThingsAPI` added
  (`set_operating_mode`, `set_battery_priority`, `set_grid_charging`,
  `set_grid_feed_in`, `set_backup_mode`).

---

## [2.3.1] - 2026-03-07

### Fixed
- Correct production AppID `rBrTRfAPXz` targeting `https://solar.siseli.com`.
  Previous release used the test AppID, causing "account error" for all real users.
- Password now MD5-hashed before transmission, matching portal behaviour.

---

## [2.3.0] - 2026-03-07

### Changed
- Authentication now uses **User ID / Account** instead of email address.

### Fixed
- Fully working IOT Open Platform request signing (AES-128-CBC + HMAC-SHA256 + MD5).
- Correct API base URLs and login path.

---

## [2.2.0] - 2026-03-06

### Added
- Email + Password authentication with automatic token refresh.
- HA re-auth flow on token expiry.
- `on_token_refreshed` callback persists tokens to config entry.
- Legacy IOT-token mode preserved.

---

## [2.1.1] - 2026-03-05

### Added
- PR template for HACS default submission.

### Changed
- `hacs.json` and `manifest.json` metadata updates.

---

## [2.1.0] - 2026-02-26

### Added
- Auto-discover all device IDs under a station via `POST /apis/device/list`.
- Optional `device_id` in config flow (blank = auto-discover all devices).

---

## [2.0.0] - 2024-02-10

### Added
- Full system control: number sliders, select dropdowns, switches.
- Settings API integration.

---

## [1.0.0] - 2024-02-10

### Added
- Initial release — monitoring sensors, config flow, multi-station support,
  Energy Dashboard compatibility.
