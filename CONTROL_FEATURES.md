# Control Features

This integration exposes 15 control entities that write directly to your
inverter through the Siseli remote-config API.

Every name and value below was captured from a live PI30 / VMIII inverter on
solar.siseli.com. If your model differs, see [API_CAPTURE.md](API_CAPTURE.md)
for how to find the names it uses.

---

## How reads and writes work

The portal uses **two different name spaces** for the same control, which is why
earlier releases could set a value but never show it back:

| Direction | Endpoint | Key style | Example |
|---|---|---|---|
| Read (live) | `GET /apis/deviceState/simple/state/latest/v1` | attribute name | `chargerSourcePriority` |
| Write | `POST /apis/remote/device/config/write` | setting name | `settingDeviceChargerPriority` |

The write body is `{"id": "<deviceId>", "key": "<settingKey>", "value": "<value>"}` —
note **`id`**, not `deviceId`. Sending `deviceId` returns `code: 0` ("Success")
and changes nothing, which is what releases before 2.6.0 did.

There is also a remote-config *cache* (`/apis/remote/device/configs/cache/get`),
but it stays empty until a batch read or write round-trips to the inverter, so
the integration reads the live snapshot instead and uses the cache only as a
fallback.

---

## Select Entities (Dropdowns)

### Output Source Priority
**Entity:** `select.{device}_output_source_priority`
**Reads:** `outputSourcePriority` · **Writes:** `settingDeviceOutputSourcePriority`

| Option | API value | Device label | Description |
|---|---|---|---|
| Utility First (USO) | 0 | UtilitySolarBat | Grid is the primary source; solar and battery supplement |
| Solar First (SUB) | 1 | SolarUtilityBat | Solar first, then grid, battery last |
| Solar+Battery First (SBU) | 2 | SolarBatUtility | Solar and battery power the load; grid only as last resort |

### Charger Source Priority
**Entity:** `select.{device}_charger_source_priority`
**Reads:** `chargerSourcePriority` · **Writes:** `settingDeviceChargerPriority`

| Option | API value | Device label | Description |
|---|---|---|---|
| Utility First | 0 | — | Grid charges the battery first |
| Solar First | 1 | for solar first | Solar charges the battery; grid fills the shortfall |
| Solar + Utility | 2 | — | Both sources charge the battery |
| Solar Only | 3 | Only Solar Permitted | Only solar charges the battery; no grid charging |

> **Changed in 2.6.0.** This is the PI30 `PCP` code and it has **four** values.
> Earlier releases mapped 0/1/2 onto CSO/SNU/OSO, which matches neither what the
> device reports nor what it accepts — a device sitting on "Solar Only" (3)
> could not be displayed at all.

---

## Switch Entities

| Entity | Reads | Writes | ON / OFF |
|---|---|---|---|
| `switch.{device}_backup_mode_sbu_priority` | `outputSourcePriority` | `settingDeviceOutputSourcePriority` | SBU (2) / SUB (1) |
| `switch.{device}_solar_feed_to_grid` | `solarFeedToGrid` | `setGridConnectionStatus` | 1 / 0 |
| `switch.{device}_buzzer` | `buzzerSetup` | `buzzerEnabled` | 1 / 0 |
| `switch.{device}_overload_bypass` | `overloadBypassFunction` | `overloadBypass` | 1 / 0 |
| `switch.{device}_overload_restart` | `overLoadRestart` | `overLoadRestartSetting` | 1 / 0 |
| `switch.{device}_over_temperature_restart` | `overTemperatureRestart` | `overTemperatureRestartSetting` | 1 / 0 |
| `switch.{device}_lcd_backlight` | `lcdBackLightControl` | `lcdBackLightControlSetting` | 1 / 0 |
| `switch.{device}_lcd_return_to_default_page` | `lcdReturnToDefaultPage` | `lcdReturnToDefaultPageSetting` | 1 / 0 |
| `switch.{device}_fault_code_recording` | `faultCodeRecord` | `faultCodeRecordSetting` | 1 / 0 |
| `switch.{device}_alarm_on_primary_source_interrupt` | `alarmOnWhenPrimarySourceInterrupt` | `alarmOnWhenPrimarySourceInterruptSetting` | 1 / 0 |

> Backup Mode and Output Source Priority are the same device setting. Turning
> Backup Mode ON moves the select to SBU, and vice versa.

**Removed in 2.6.0:** *Grid Charging (AC Input Range)*. The device reports its
input voltage range (`inputVoltageRange`: Appliance / UPS) but the portal
exposes no write key for it, so the switch could never change anything. It is
now the read-only *Input Voltage Range* diagnostic sensor.

---

## Number Entities

| Entity | Reads | Writes | Range |
|---|---|---|---|
| `number.{device}_battery_equalization_voltage` | `batteryEqualizationVoltage` | `setBatteryEqualizationVoltage` | 20 – 60 V |
| `number.{device}_battery_equalization_period` | `equalizationPeriod` | `setBatteryEqualizationPeriod` | 0 – 99 days |
| `number.{device}_battery_equalization_timeout` | `equalizationOverTime` | `setBatteryEqualizationOverTime` | 0 – 900 min |

**Removed in 2.6.0:** *Battery Charge Limit*, *Battery Discharge Limit* and
*Grid Charge Limit*. No such attributes exist on PI30/VMIII and the write
endpoint has no keys for them, so the sliders were permanently unavailable and
their writes went nowhere. Charge and discharge current limits *are* reported
(`optionalValueForMaximumChargingCurrent`, `maxDischargingCurren`) and are
exposed as diagnostic sensors — the portal offers no way to write them.

---

## Automation Examples

### Maximise self-consumption during the day
```yaml
automation:
  - alias: "Solar — Solar First during daylight"
    trigger:
      - platform: sun
        event: sunrise
    action:
      - service: select.select_option
        target:
          entity_id: select.1_inverter_output_source_priority
        data:
          option: "Solar First (SUB)"

  - alias: "Solar — Utility First at night"
    trigger:
      - platform: sun
        event: sunset
    action:
      - service: select.select_option
        target:
          entity_id: select.1_inverter_output_source_priority
        data:
          option: "Utility First (USO)"
```

### Only charge from solar while the sun is up
```yaml
automation:
  - alias: "Solar — Solar-only charging by day"
    trigger:
      - platform: sun
        event: sunrise
    action:
      - service: select.select_option
        target:
          entity_id: select.1_inverter_charger_source_priority
        data:
          option: "Solar Only"

  - alias: "Solar — Allow grid charging overnight"
    trigger:
      - platform: sun
        event: sunset
    action:
      - service: select.select_option
        target:
          entity_id: select.1_inverter_charger_source_priority
        data:
          option: "Solar + Utility"
```
