# ☀️ Solar of Things — Home Assistant Integration

<p align="center">
  <a href="https://github.com/Conexo-Casa/solar-of-things-ha/releases/latest">
    <img src="https://img.shields.io/github/v/release/Conexo-Casa/solar-of-things-ha?style=for-the-badge&label=Latest%20Release&color=orange" alt="Latest Release">
  </a>
  <a href="https://github.com/custom-components/hacs">
    <img src="https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge" alt="HACS Custom">
  </a>
  <a href="https://www.home-assistant.io/">
    <img src="https://img.shields.io/badge/Home%20Assistant-2023.6%2B-41BDF5?style=for-the-badge&logo=home-assistant" alt="Home Assistant">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/github/license/Conexo-Casa/solar-of-things-ha?style=for-the-badge" alt="MIT License">
  </a>
</p>

<p align="center">
  <strong>Monitor and control your Siseli solar inverter directly from Home Assistant.</strong><br>
  Real-time power data · Battery management · Grid control · Energy Dashboard ready
</p>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Sensors](#sensors)
- [Control Entities](#control-entities)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Energy Dashboard](#energy-dashboard)
- [Automation Examples](#automation-examples)
- [Dashboard Cards](#dashboard-cards)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [Changelog](#changelog)

---

## Overview

The **Solar of Things** integration connects Home Assistant to the
[Siseli solar portal](https://solar.siseli.com) and provides:

- **Auto-discovery** of every inverter under your station — enter your Station ID once and Home Assistant finds all devices automatically.
- **10+ real-time sensors** updated every 5 minutes.
- **4 monthly summary sensors** for energy totals and solar coverage.
- **8 control entities** (sliders, dropdowns, switches) to manage battery limits, operating modes, and grid settings from HA.
- Full **Home Assistant Energy Dashboard** compatibility.
- **Multi-station support** — add the integration once per station.

> **Developed by [Conexo Casa](https://conexocasa.org)** — building accessible technology for people with neurocognitive impairments and the elderly.

---

## Features

| Category | What you get |
|---|---|
| 🔍 **Auto-discovery** | Enter Station ID → HA fetches all device IDs automatically |
| 📊 **Real-time monitoring** | 10 per-device sensors, updated every 5 min |
| 📅 **Monthly statistics** | 4 station-level energy summary sensors |
| 🎛️ **System control** | 8 control entities (battery limits, modes, grid switches) |
| ⚡ **Energy Dashboard** | All power and energy sensors are dashboard-ready |
| 🏠 **Multi-station** | Unlimited stations via multiple config entries |
| 🔒 **Secure auth** | User ID + Password with automatic token refresh |
| 🌏 **Timezone-aware** | Configurable `IOT-Time-Zone` header per integration |
| 🔄 **Auto-retry** | HA coordinator pattern with automatic retry on failure |

---

## Sensors

### Real-time Device Sensors
> Updated every **5 minutes** · One set per discovered device

| Entity | Unit | Device Class | Description |
|---|---|---|---|
| `{device} PV Input Power` | W | `power` | Solar panel DC input power |
| `{device} AC Output Power` | W | `power` | AC power delivered to loads |
| `{device} Battery Charging Current` | A | `current` | Current flowing into battery |
| `{device} Battery Discharge Current` | A | `current` | Current flowing out of battery |
| `{device} Battery Voltage` | V | `voltage` | Battery bank terminal voltage |
| `{device} Battery Power` | W | `power` | Net battery power (discharge − charge × voltage) |
| `{device} Battery State of Charge` | % | `battery` | Battery charge level |
| `{device} Grid Feed-in Power` | W | `power` | Power exported to the utility grid |
| `{device} Grid Import Power` | W | `power` | Power imported from the utility grid |
| `{device} Load Power` | W | `power` | Total household / load consumption |

### Monthly Station Sensors
> Updated every **30 minutes** · Requires Station ID

| Entity | Unit | Device Class | Description |
|---|---|---|---|
| `Station {id} Monthly PV Generated` | kWh | `energy` | Total solar generation this month |
| `Station {id} Monthly Grid Import` | kWh | `energy` | Total grid import this month |
| `Station {id} Monthly Total Consumption` | kWh | `energy` | Total household consumption this month |
| `Station {id} Monthly Solar Coverage` | % | — | Percentage of consumption met by solar |

---

## Control Entities

> Controls require your device firmware/account to support the settings API.
> If unresponsive, see [Troubleshooting](#troubleshooting).

### Number Entities (Sliders)

| Entity | Range | Step | Unit | Description |
|---|---|---|---|---|
| `{device} Battery Charge Limit` | 0 – 100 | 1 | % | Maximum SOC target for charging |
| `{device} Battery Discharge Limit` | 0 – 100 | 1 | % | Minimum SOC before stopping discharge |
| `{device} Grid Charge Limit` | 0 – 5000 | 100 | W | Max grid power used for battery charging |

### Select Entities (Dropdowns)

| Entity | Options | Description |
|---|---|---|
| `{device} Output Source Priority` | Utility First (USO) · Solar First (SUB) · Solar+Battery First (SBU) | System power source priority |
| `{device} Charger Source Priority` | Solar + Utility (CSO) · Solar First (SNU) · Solar Only (OSO) | Battery charging source priority |

### Switch Entities

| Entity | Description |
|---|---|
| `{device} Grid Charging (AC Input Range)` | Allow/deny battery charging from the grid (Appliance vs UPS mode) |
| `{device} Grid Feed-In` | Allow/deny exporting excess power to the grid |
| `{device} Backup Mode (SBU Priority)` | Reserve battery capacity for power outages (SBU vs SUB priority) |

---

## Requirements

| Requirement | Details |
|---|---|
| Home Assistant | **2023.6** or newer |
| Siseli account | Active account at [solar.siseli.com](https://solar.siseli.com) |
| Station ID | Numeric `stationId` from the Siseli portal (usually 18 digits) |
| Network | HA must reach `https://solar.siseli.com` |

---

## Installation

### HACS (Recommended)

1. Open **HACS** in the HA sidebar → **Integrations**.
2. Click **⋮** (top-right) → **Custom repositories**.
3. Enter:
   ```
   https://github.com/Conexo-Casa/solar-of-things-ha
   ```
   Category: **Integration** → **Add**.
4. Search **Solar of Things** → **Download**.
5. **Restart Home Assistant.**

### Manual

1. Download the latest release ZIP from the [Releases page](https://github.com/Conexo-Casa/solar-of-things-ha/releases/latest).
2. Extract and copy the `solar_of_things` folder to:
   ```
   /config/custom_components/solar_of_things/
   ```
3. **Restart Home Assistant.**

---

## Configuration

### Step 1 — Find Your Credentials

1. Open [https://solar.siseli.com](https://solar.siseli.com) and log in.
2. Note your **User ID** (login account name) and **password**.
3. Press **F12** → **Network** tab → refresh the page.
4. Click any request to `solar.siseli.com` and find `stationId` in the **Payload** tab.

| Value | Where to find it |
|---|---|
| **User ID** | Your account login name on solar.siseli.com |
| **Password** | Your account password |
| **Station ID** | `stationId` field in any API request payload |

### Step 2 — Add the Integration

1. **Settings → Devices & Services → + Add Integration**.
2. Search **Solar of Things**.
3. Choose **User ID + Password** (recommended) and fill in:

   | Field | Required | Description |
   |---|---|---|
   | **User ID** | ✅ | Your Siseli account login name |
   | **Password** | ✅ | Your Siseli account password |
   | **Station ID** | ✅ | Numeric `stationId` (usually 18 digits) — **not** your inverter or WiFi-dongle serial number |
   | **Device ID** | Optional | Leave blank to auto-discover all devices |
   | **Time zone** | Optional | Default: `Asia/Manila` |

4. Click **Submit**. The integration logs in, discovers devices, and creates all entities.

> **IOT Token mode** is also available for advanced users who prefer not to store credentials. Tokens expire and require re-entry when they do.

### Step 3 — Verify

Go to **Settings → Devices & Services → Solar of Things** and confirm your devices appear with sensors, controls, and monthly sensors populated.

> Entities show **Unknown** for the first 5 minutes while the first coordinator poll runs.

---

## Energy Dashboard

Go to **Settings → Dashboards → Energy** and configure:

| Dashboard slot | Entity |
|---|---|
| Solar production | `sensor.{device}_pv_input_power` |
| Grid consumption | `sensor.{device}_grid_import_power` |
| Return to grid | `sensor.{device}_grid_feed_in_power` |
| Battery charge | `sensor.{device}_battery_charging_current` |
| Battery discharge | `sensor.{device}_battery_discharge_current` |
| Monthly solar (production) | `sensor.station_{id}_monthly_pv_generated` |
| Monthly grid import | `sensor.station_{id}_monthly_grid_import` |

---

## Automation Examples

### Low battery alert
```yaml
automation:
  - alias: "Solar — Low Battery Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.1_inverter_battery_state_of_charge
        below: 20
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Solar Battery Low"
          message: >
            Battery is at
            {{ states('sensor.1_inverter_battery_state_of_charge') }}%.
```

### Enable grid charging at night
```yaml
automation:
  - alias: "Solar — Enable Grid Charging at Night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.1_inverter_grid_charging_ac_input_range
```

### Switch to backup mode before a storm
```yaml
automation:
  - alias: "Solar — Backup Mode Before Storm"
    trigger:
      - platform: state
        entity_id: weather.home
        to: "rainy"
    condition:
      - condition: numeric_state
        entity_id: sensor.1_inverter_battery_state_of_charge
        below: 80
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.1_inverter_backup_mode_sbu_priority
      - service: number.set_value
        target:
          entity_id: number.1_inverter_battery_charge_limit
        data:
          value: 95
```

---

## Dashboard Cards

### Quick status overview
```yaml
type: entities
title: ☀️ Solar System
entities:
  - entity: sensor.1_inverter_pv_input_power
    name: Solar Generation
  - entity: sensor.1_inverter_battery_state_of_charge
    name: Battery Level
  - entity: sensor.1_inverter_load_power
    name: Home Load
  - entity: sensor.1_inverter_grid_import_power
    name: Grid Import
  - entity: sensor.1_inverter_grid_feed_in_power
    name: Grid Feed-In
```

### Control panel
```yaml
type: entities
title: 🎛️ Solar Controls
entities:
  - entity: select.1_inverter_output_source_priority
    name: Output Mode
  - entity: select.1_inverter_charger_source_priority
    name: Charger Priority
  - entity: number.1_inverter_battery_charge_limit
  - entity: number.1_inverter_battery_discharge_limit
  - entity: number.1_inverter_grid_charge_limit
  - type: divider
  - entity: switch.1_inverter_grid_charging_ac_input_range
  - entity: switch.1_inverter_grid_feed_in
  - entity: switch.1_inverter_backup_mode_sbu_priority
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Cannot Connect" on setup | Wrong credentials or network | Check User ID / password and HA network access to solar.siseli.com |
| No devices discovered | Wrong Station ID | Re-read `stationId` from the portal Network tab. A serial number printed on the inverter or WiFi dongle is **not** the Station ID |
| Entities show "Unavailable" | Token expired or portal unreachable | HA will prompt re-auth automatically; check logs |
| Sensors always "Unknown" | API returns null for that field | Normal for sensors not supported by your inverter model |
| Controls do nothing | Settings endpoint varies by firmware | Check HA logs for HTTP status codes |
| Integration not in search | Files in wrong location | Verify `/config/custom_components/solar_of_things/` exists |

### Enable debug logging
```yaml
logger:
  default: info
  logs:
    custom_components.solar_of_things: debug
```
Restart HA, reproduce the issue, then check **Settings → System → Logs**.

---

## Contributing

1. Fork the repo and create a feature branch.
2. Make changes and ensure Python syntax is valid:
   ```bash
   python3 -m py_compile custom_components/solar_of_things/*.py
   ```
3. Open a Pull Request with a clear description.

Bug reports and feature requests: [GitHub Issues](https://github.com/Conexo-Casa/solar-of-things-ha/issues)

---

## Changelog

See **[CHANGELOG.md](CHANGELOG.md)** for full history.

| Version | Highlights |
|---|---|
| **v2.4.0** | HACS structure, brand icon, missing API methods fixed, translation keys, device registry fix |
| **v2.3.3** | Correct settings API endpoints from live portal |
| **v2.3.0** | User ID auth, working IOT-Open signing |
| **v2.2.0** | Auto token refresh, HA re-auth flow |
| **v2.0.0** | Control entities (battery, modes, grid) |
| **v1.0.0** | Initial release — monitoring sensors |

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built by <a href="https://conexocasa.org">Conexo Casa</a> — accessible technology for everyone<br>
  <a href="https://github.com/Conexo-Casa/solar-of-things-ha/issues">Report a Bug</a> ·
  <a href="https://github.com/Conexo-Casa/solar-of-things-ha/issues">Request a Feature</a> ·
  <a href="https://community.home-assistant.io">HA Community Forum</a>
</p>
