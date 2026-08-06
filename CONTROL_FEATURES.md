# Control Features

This integration exposes 8 control entities that write directly to your inverter
via the Siseli remote-config API.

> Controls require your device and Siseli account to support the settings API.
> Read settings are fetched every 5 minutes alongside telemetry.

---

## Number Entities (Sliders)

### Battery Charge Limit
**Entity:** `number.{device}_battery_charge_limit`  
**API key:** `batteryChargeLimit`  
**Range:** 0 – 100 %  
Sets the maximum State of Charge the inverter will charge the battery to.

### Battery Discharge Limit
**Entity:** `number.{device}_battery_discharge_limit`  
**API key:** `batteryDischargeLimit`  
**Range:** 0 – 100 %  
Sets the minimum SOC at which the inverter stops discharging the battery.
Acts as a floor for battery protection.

### Grid Charge Limit
**Entity:** `number.{device}_grid_charge_limit`  
**API key:** `gridChargeLimit`  
**Range:** 0 – 5000 W, step 100 W  
Maximum grid power the inverter is allowed to use for battery charging.
Set to 0 to disable grid charging via this limit.

---

## Select Entities (Dropdowns)

### Output Source Priority
**Entity:** `select.{device}_output_source_priority`  
**API key:** `outputSourcePrioritySetting`

| Option | API value | Description |
|---|---|---|
| Utility First (USO) | 0 | Grid is the primary power source; solar and battery supplement |
| Solar First (SUB) | 1 | Solar is primary; grid fills the gap; battery charges from surplus |
| Solar+Battery First (SBU) | 2 | Solar and battery power the load; grid only as last resort |

### Charger Source Priority
**Entity:** `select.{device}_charger_source_priority`  
**API key:** `chargerSourcePrioritySetting`

| Option | API value | Description |
|---|---|---|
| Solar + Utility (CSO) | 0 | Both solar and grid charge the battery; utility has priority |
| Solar First (SNU) | 1 | Solar charges the battery first; grid fills the shortfall |
| Solar Only (OSO) | 2 | Only solar charges the battery; no grid charging |

### How the current value is read back

Writes go to `POST /apis/remote/device/config/write` under the `…Setting` key
above. Reads do **not** come from the matching config cache: that cache only
holds keys previously written through the portal, so it is empty on accounts
that have never used remote control — which is why these selects reported
`unknown` before 2.5.0.

The current value is read from the live snapshot
(`GET /apis/deviceState/simple/state/latest/v1`, fields `outputSourcePriority`
and `chargerSourcePriority`), falling back to the config cache. Both an integer
code and a label such as `"SBU"` are accepted. If your model uses different
names, add them to `STATE_KEY_CANDIDATES` in `const.py` — see
[API_CAPTURE.md](API_CAPTURE.md).

---

## Switch Entities

### Grid Charging (AC Input Range)
**Entity:** `switch.{device}_grid_charging_ac_input_range`  
**API key:** `acInputRangeSetting`

| State | API value | Behaviour |
|---|---|---|
| ON | 0 | **Appliance mode** — wide voltage range, grid charging allowed |
| OFF | 1 | **UPS mode** — narrow voltage range, stricter bypass |

### Grid Feed-In
**Entity:** `switch.{device}_grid_feed_in`  
**API key:** `batteryPowerLimitingSetting`

| State | API value | Behaviour |
|---|---|---|
| ON | 1 | Grid switch enabled — excess power exported to grid |
| OFF | 0 | Grid switch disabled — no feed-in |

### Backup Mode (SBU Priority)
**Entity:** `switch.{device}_backup_mode_sbu_priority`  
**API key:** `outputSourcePrioritySetting`

| State | API value | Behaviour |
|---|---|---|
| ON | 2 (SBU) | Solar+Battery first — battery reserved for outages |
| OFF | 1 (SUB) | Solar first — grid supplements when solar is insufficient |

> **Note:** Backup Mode and Output Source Priority share the same API key.
> Turning Backup Mode ON changes Output Source Priority to SBU, and vice versa.

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

### Protect battery on cloudy days
```yaml
automation:
  - alias: "Solar — Raise discharge floor on low solar"
    trigger:
      - platform: numeric_state
        entity_id: sensor.1_inverter_pv_input_power
        below: 50
        for: "00:30:00"
    action:
      - service: number.set_value
        target:
          entity_id: number.1_inverter_battery_discharge_limit
        data:
          value: 30
```
