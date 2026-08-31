# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.4.3] - 2026-08-31

### Fixed
- **Setup no longer implies the Station/Device ID must be exactly 18 digits.**
  Users read the "18-digit number" wording in the config-flow dialog as a hard
  requirement and concluded the integration was broken when their own value had a
  different length. There has never been any length validation — `station_id` and
  `device_id` are plain strings, and an ID of any length is accepted. The dialog
  text, README, QUICKSTART and bug-report template now say "usually 18 digits".
- **Added an explicit warning that the Station ID is not a serial number.** The
  value must be the numeric `stationId` from the portal's API request payload
  (DevTools → Network). The number printed on the inverter or WiFi dongle, and
  plant/registration codes shown in the portal UI, are different identifiers and
  will not work — this is the most common cause of the mix-up above.
- **"More info" link in the IOT-token setup step pointed at an unrelated
  project** (`Hyllesen/solar-of-things-solar-usage`). It now points here.
- Normalised the remaining `conexocasa/` URLs to the canonical `Conexo-Casa/`
  organisation, including the outbound `User-Agent`.
- `User-Agent` version string was pinned at `2.3.0` and no longer matched the
  shipped release; it now reports the correct version.

### Notes
- Documentation, wording and metadata only — no functional, entity or API
  changes. Existing configured stations are unaffected and no re-setup is needed.
- If your sensors are `unknown` or stuck at `0`, that is a separate, known issue
  tracked in #7 (some inverters/dongles return live data from
  `/energy/flow/v1` under different field keys) and is not addressed by this
  release.

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
