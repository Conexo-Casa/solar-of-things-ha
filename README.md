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
- **15 control entities** (dropdowns, switches, numbers) to manage charge/output priority, grid feed-in, and device behaviour from HA.
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
| 🎛️ **System control** | 15 control entities (priorities, grid feed-in, device settings) |
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
| `{device} Grid Feed-in Power` | W | `power` | Power exported to the grid — reads 0 on off-grid models, which report no feed-in measurement |
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

### Number Entities

| Entity | Range | Step | Unit | Description |
|---|---|---|---|---|
| `{device} Battery Equalization Voltage` | 20 – 60 | 0.1 | V | Equalization charge voltage |
| `{device} Battery Equalization Period` | 0 – 99 | 1 | d | Days between equalization cycles |
| `{device} Battery Equalization Timeout` | 0 – 900 | 5 | min | Maximum equalization duration |

### Select Entities (Dropdowns)

| Entity | Options | Description |
|---|---|---|
| `{device} Output Source Priority` | Utility First (USO) · Solar First (SUB) · Solar+Battery First (SBU) | System power source priority |
| `{device} Charger Source Priority` | Utility First · Solar First · Solar + Utility · Solar Only | Battery charging source priority |

### Switch Entities

| Entity | Description |
|---|---|
| `{device} Backup Mode (SBU Priority)` | Reserve battery capacity for power outages (SBU vs SUB priority) |
| `{device} Solar Feed to Grid` | Allow/deny exporting excess solar to the grid |
| `{device} Buzzer` | Audible alarm on/off |
| `{device} Overload Bypass` | Pass the load through to the grid on overload |
| `{device} Overload Restart` | Auto-restart after an overload shutdown |
| `{device} Over-temperature Restart` | Auto-restart after a thermal shutdown |
| `{device} LCD Backlight` | Front-panel backlight |
| `{device} LCD Return to Default Page` | Return the panel to its default page |
| `{device} Fault Code Recording` | Record fault codes on the device |
| `{device} Alarm on Primary Source Interrupt` | Beep when the primary source drops |

---

## Requirements

| Requirement | Details |
|---|---|
| Home Assistant | **2023.6** or newer |
| Siseli account | Active account at [solar.siseli.com](https://solar.siseli.com) |
| Station ID | 18-digit ID from the Siseli portal |
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
   | **Station ID** | ✅ | 18-digit Station ID |
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

### Allow grid charging at night
```yaml
automation:
  - alias: "Solar — Allow Grid Charging at Night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: select.select_option
        target:
          entity_id: select.1_inverter_charger_source_priority
        data:
          option: "Solar + Utility"
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
      - service: select.select_option
        target:
          entity_id: select.1_inverter_charger_source_priority
        data:
          option: "Solar + Utility"
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
  - type: divider
  - entity: switch.1_inverter_backup_mode_sbu_priority
  - entity: switch.1_inverter_solar_feed_to_grid
  - entity: switch.1_inverter_buzzer
  - type: divider
  - entity: number.1_inverter_battery_equalization_voltage
  - entity: number.1_inverter_battery_equalization_period
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Cannot Connect" on setup | Wrong credentials or network | Check User ID / password and HA network access to solar.siseli.com |
| No devices discovered | Wrong Station ID | Verify 18-digit stationId in the portal Network tab |
| Entities show "Unavailable" | Token expired or portal unreachable | HA will prompt re-auth automatically; check logs |
| Sensors always "Unknown" | Your model publishes that measurement under another attribute name | Follow [API_CAPTURE.md](API_CAPTURE.md) so the name can be added |
| Priority selects "Unknown" | Fixed in 2.5.0 — they used to read only the remote-config cache, which is empty until a setting is written through the portal | Update the integration |
| Controls do nothing | Settings endpoint varies by firmware | Check HA logs for HTTP status codes |
| Integration not in search | Files in wrong location | Verify `/config/custom_components/solar_of_things/` exists |

### Reporting an "Unknown" entity

The quickest fix path is **Settings → Devices & Services → Solar of Things →
⋮ → Download diagnostics**, attached to a GitHub issue. It lists every
attribute name your inverter publishes with credentials removed, which is all
that is needed to map a missing value. See [API_CAPTURE.md](API_CAPTURE.md) for
that and three other capture methods.

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
