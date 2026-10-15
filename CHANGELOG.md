# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.8.4] - 2026-10-15

### Fixed
- **AC Output, Load and Grid Import no longer 1000× too high on the Datouboss JC-5052** (#42). On this model the time-series value arrives via the `outputActivePower` alias and the energy-flow data has no `acOutputActivePower` block, so v2.8.2's unit lookup found no tag and assumed kW. The unit is now taken from `acOutputActivePower`, then `outputActivePower`, then `loadActivePower`, whichever is tagged first. Devices tagging `acOutputActivePower`, or with no tag at all, are unchanged. Thanks to @otembajelle for the capture.

## [2.8.3] - 2026-10-14

### Fixed
- **Battery Power no longer reads a false 0 W** when a battery current is missing (Datouboss JC-5052, #42). It was computed with the missing current as 0 A; it now stays unknown unless voltage and both currents are reported. Grid Import, which is estimated from Battery Power, follows the same rule.
- **Grid Import uses the measured AC Input Power** when the device reports it with a unit tag (Gospower via RWB1, #41). It previously estimated 90 W with no grid connected.
- **Time-zone check no longer blocks Home Assistant's event loop** during setup (#14 log). The zone list is now read once, in the executor.

### Added
- **Station ID is optional** in the User ID + Password setup (#14). After login, your stations are listed to pick from, or selected automatically if there is only one. A typed ID that isn't a station on your account (e.g. a DTU-ID or serial) now opens the picker instead of failing with "Cannot connect". Thanks to @otembajelle for finding `/apis/station/list`.

## [2.8.2] - 2026-10-13

### Fixed
- AC Output, Load and Grid Import Power no longer read 1000× too high on devices that report `acOutputActivePower` in W (Datouboss JC-5052 / JC-50521 dongle, #42). The unit is now taken from the device's own energy-flow unit tag; devices reporting kW, or without a tag, are unchanged.

## [2.8.1] - 2026-10-12

### Fixed
- **PV Input Power under-reported on dual-MPPT inverters** (#9). On the
  Victor 19.2, `pvInputPower` is PV1 only (the portal labels it "PV1 Input
  Power"); the second string arrives as `pv2InputPower`. PV Input Power is
  now PV1 + PV2 — confirmed against the portal's own generation total
  (538 W + 2021 W = 2.559 kW). Single-string devices are unchanged, and the
  HPVINV02 `pvPower` alias (already a device total) is not double-counted.

### Added
- **Grid Voltage** sensor (`acInputVoltage`, #36) — reads 0 V when the grid
  is down, so it can drive "grid present" automations.
- **PV1 / PV2 Input Power** and **PV1 / PV2 Input Voltage** sensors (#9),
  on both the time-series and energy-flow paths (SRNE per-string kW fields
  included).

## [2.8.0] - 2026-10-12

### Fixed
- **PV Input Power, AC Output Power and grid sensors stayed unknown when the
  time-series endpoint was only partly populated** (#35, #37). The
  energy-flow fallback ran only when *no* realtime key was present; firmware
  that reports battery keys but no power keys never reached it, and Load
  Power then read 0 W while battery discharge was reported as Grid Import.
  The fallback now runs whenever any realtime key is missing, and fills keys
  the time-series returned as `None`. It never overrides a real reading.
- **PV power reported only on the `pvPanelFlow` card** (EASUN RWB1-04, #35)
  is now read.
- **Deprecated `via_device` warning on HA 2026.10** (#34, #37). Inverter
  devices now link to the station hub with `via_device_id`; the old key stops
  working in HA 2027.8. HA releases before 2026.8 keep the old behaviour.

### Added
- **SRNE-family energy-flow mappings** (DatouBoss 4863U #37, same payload as
  the Maniy 11 kW in #32): `pv1RealTimePower` + `pv2RealTimePower` (kW),
  `loadPower` (W), `mainsInputRealTimePower` (W, import), `batteryCapacity`,
  `lithiumBatteryVoltage` — units confirmed against the inverter's RS485
  registers.
- **Unit-tag-aware mapping.** When a field carries its own `W`/`kW` unit tag
  it now wins over the table scale. Keys whose unit differs by model
  (`acOutputActivePower`, `pvInputPower`, `pv2InputPower`, `generationPower`
  — #9, #24) are mapped **only** when tagged; untagged values stay unknown
  rather than risk a 1000x error. Signed `GridPower` (#24) is split into
  Grid Import / Feed-in.

### Changed
- Devices that already have some realtime data and merely lack one key log
  the fallback diagnostics at DEBUG instead of WARNING on every poll.

## [2.7.1] - 2026-09-16

### Notes
- **Grid Feed-in Power's exporting case is now directly confirmed**, not just
  inferred by symmetry. v2.6.1 shipped it without a capture of a device
  actually exporting; hidemichixt-creator's follow-up capture (#7) has a full
  battery and PV surplus flowing out (897 W PV, 0 W battery, 351 W load),
  and `aPhaseMainsPower` reads +495 W — positive really does mean feeding
  into the grid. No code change; this closes out the caveat from the
  previous release.

## [2.7.0] - 2026-09-15

### Fixed
- **Writing a control setting failed with `code=70134 "Config attribute not
  exists"` on some firmware** — the integration always sent one hardcoded
  key name per control (e.g. `outputSourcePrioritySetting`), but
  lukaszkwapien's full writable-config dump for a FCHAO inverter (#18)
  confirmed that firmware exposes the same control as
  `setOutputSourcePriority` instead, and does not expose Battery Charge
  Limit, Battery Discharge Limit, or Grid Charge Limit under **any** key
  name at all. This is the same class of bug #13 fixed for sensor reads,
  now fixed for control writes and their read-back too: each control now
  resolves the real key name from the device's own writable-config listing
  (already fetched every update cycle), and an entity whose control isn't
  exposed under any known name now reports **unavailable** in Home
  Assistant instead of accepting a click that is guaranteed to fail.
- **Battery Charge Limit, Battery Discharge Limit, and Grid Charge Limit
  number entities never displayed a value, even on devices that fully
  support them.** `native_value` was returning the entire settings object
  (`{"key", "value", "valueDisplay", ...}`) instead of extracting the numeric
  `value` field — the same object every other read path already correctly
  unwraps. Existing configured limits will now show correctly.

### Notes
- Every device that worked before this release keeps sending exactly the
  same key names it always has — the alias table only adds alternates, and
  falls back to the original documented key when nothing else is known.
- If your inverter exposes a control under yet another key name, the
  affected entity will now show as unavailable rather than fail silently or
  loudly — please open an issue with your device's writable-config listing
  (`GET /apis/remote/device/configs/cache/get?deviceId=<yours>`) so it can be
  added.

## [2.6.1] - 2026-09-15

### Fixed
- **A device with no energy-flow rule configured on the portal produced no
  sensors and no warning**, which was indistinguishable from a bug in this
  integration. The portal's `code=70132 "Energy flow rule not exists"`
  response fell into the same silent DEBUG-level handling as a merely
  unsupported/404 endpoint. That specific error now logs a clear WARNING
  explaining the fix is a portal-side setup step (configuring an
  energy-flow rule for the device on solar.siseli.com), not something a
  future field mapping can resolve. Reported in #21.

## [2.6.0] - 2026-09-15

### Added
- **AC Output Power, Grid Import Power, Grid Feed-in Power, Battery Charging
  Current and Battery Discharge Current now populate on devices that use the
  energy-flow fallback** (the UWB1 / RWB1-0x / JC-62xx / DatouBoss / EASUN
  family from #7). v2.5.0 shipped only Battery Voltage, State of Charge,
  Power and PV Input Power from this path because every field needed to
  confirm the rest — `load_power`'s unit, the mains-power sign convention,
  and the battery terminal current's charge/discharge direction — had only
  been captured at night, reading zero. Four daylight captures across every
  AC/PV/charging combination settled all three: `load_power` and the mains
  fields carry their own `"unit"` tag in the payload (kW and W
  respectively, not guessed), and the mains-power sign checks out against
  simple load-minus-generation arithmetic in every AC-connected sample.
  Thanks to @hidemichixt-creator for the four-state capture set (#7).

### Notes
- Grid Feed-in Power's positive-value (exporting) case is inferred from the
  same signed field as Grid Import Power by physical symmetry, not yet
  observed directly — no capture so far has shown the device actually
  exporting. If it reads wrong on a grid-tied system, please reopen #7 with
  a capture taken while exporting.

## [2.5.1] - 2026-09-14

### Fixed
- **Adding a station could fail outright with a cryptic portal error.**
  Time zone has always been a free-text field; a value that isn't a real
  IANA zone id (a continent name like `Europe` rather than `Europe/Warsaw`,
  for example) was sent as-is to the portal, which rejected the very first
  request with `Timeseries error code=20101 message=Illegal argument` — with
  nothing in the error pointing at time zone as the cause. The field is now
  validated locally before any API call, with a clear in-form error instead.
  Thanks to @Terrorr for the report (#21).
- **PV Input Power, AC Output Power and Battery State of Charge stuck on
  `unknown` on Siseli HPVINV02 devices** ("Inverter Top One" gather
  protocol), even though the account, station and other sensors all worked
  normally. This firmware reports those three fields under different key
  names (`pvPower`, `outputActivePower`, `batteryCapacity`) than the
  documented ones — the integration now recognises both. Thanks to
  @UnSpritz for root-causing this via live debug logging and submitting the
  fix (#13).

### Notes
- Both fixes are scoped and regression-tested against the full existing
  suite; a working installation's readings are unaffected either way.

## [2.5.0] - 2026-09-11

### Added
- **Realtime sensors now populate on inverters that never fill the historical
  time-series endpoint.** Several firmware families (UWB1, RWB1-0x, JC-62xx,
  DatouBoss DT-series, EASUN) left every realtime entity `unknown` while the
  portal showed live data — the shared cause behind #3, #7, #8, #11, #14 and
  #15. Those devices serve live values from
  `/apis/deviceState/simple/energy/flow/v1` under a different set of field
  names, and the integration now falls back to that endpoint and maps them.

  Populated by the fallback: **PV Input Power** (per-string `pv1Power`…`pv4Power`,
  summed), **Battery Voltage**, **Battery State of Charge**, **Battery Power**.

  Thanks to @jazuch for a report that included the endpoint, the data path, the
  field names and sample values, and to @hidemichixt-creator for confirming the
  fix against real hardware.

### Changed
- Derived values (battery / grid / load power) now **fill gaps rather than
  overwrite**, so a directly measured reading is preferred over the
  `voltage x current` estimate.

### Notes
- **The fallback is gated.** It runs only when the time-series endpoint yields
  no realtime value, so a working installation makes zero extra API calls and
  its readings are unchanged — pinned by a regression test.
- **Deliberately not mapped yet.** Publishing a wrong value is worse than an
  unknown sensor: a 1000x scaling error feeds the Energy dashboard and
  long-term statistics, which a later fix cannot un-poison.
  - `generationPower`, `load_power` / `loadPower`, and the per-phase
    `aPhaseMainsPower` / `bPhaseMainsPower` / `cPhaseMainsPower` — every
    captured sample was zero (night-time reading), so kW-vs-W is unconfirmed.
  - `positiveTerminalBatteryCurrent` / `negativeTerminalBatteryCurrent` — the
    magnitude is correct, but which terminal means charge and which means
    discharge is unverified, and a swap would invert the two.

  Load Power and Grid Import Power therefore keep their existing derived
  estimates. See `ENERGY_FLOW_UNVERIFIED` in `const.py`; tracked in #7.
- If your inverter reports fields this release does not recognise, the log now
  emits a warning listing the exact key names — please open an issue with them.

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
