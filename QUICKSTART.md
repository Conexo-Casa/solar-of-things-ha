# Quick Start Guide

Get Solar of Things running in Home Assistant in under 5 minutes.

## Prerequisites

- ✅ Home Assistant 2023.6+
- ✅ Active account at [solar.siseli.com](https://solar.siseli.com)

---

## Step 1 — Find Your Station ID (2 min)

1. Open [https://solar.siseli.com](https://solar.siseli.com) and log in.
2. Press **F12** → **Network** tab → refresh the page (**Ctrl+R**).
3. Click any request to `solar.siseli.com`.
4. In the **Payload** tab, find `stationId` — a long number, usually 18 digits.

> Your **User ID** is your login account name (not an email address, and not a number).
> Your **Station ID** looks like `423564214316007425`.
>
> ⚠️ **The Station ID is not a serial number.** Do not use the number printed on
> your inverter or WiFi dongle, and do not use a plant/registration code shown in
> the portal UI — those are often a different length (20 digits or more) and will
> not work. The only value that works is the `stationId` from the Network payload
> shown above. Any length is accepted at setup; the integration does not require
> exactly 18 digits.

---

## Step 2 — Install (1 min)

### Option A: HACS
1. HACS → Integrations → **⋮** → Custom repositories
2. Add `https://github.com/Conexo-Casa/solar-of-things-ha` → Integration
3. Search **Solar of Things** → Download
4. Restart Home Assistant

### Option B: Manual
1. Download the ZIP from [Releases](https://github.com/Conexo-Casa/solar-of-things-ha/releases/latest)
2. Extract `solar_of_things/` → copy to `/config/custom_components/`
3. Restart Home Assistant

---

## Step 3 — Configure (2 min)

1. **Settings → Devices & Services → + Add Integration**
2. Search **Solar of Things**
3. Select **User ID + Password** (recommended)
4. Enter your **User ID**, **Password**, and **Station ID**
5. Leave Device ID blank (auto-discovers all inverters)
6. Click **Submit**

---

## Step 4 — Done ✅

Go to **Settings → Devices & Services → Solar of Things**.

You should see your inverter device with:
- ☀️ 10 real-time power sensors
- 🔋 3 battery control sliders
- 🔽 2 operating mode dropdowns
- 🔘 3 grid/backup switches
- 📊 4 monthly energy sensors

> Sensors show **Unknown** for the first 5 minutes — this is normal while the first poll runs.

---

## Next Steps

- [Energy Dashboard setup](README.md#energy-dashboard)
- [Automation examples](README.md#automation-examples)
- [Troubleshooting](README.md#troubleshooting)
- [Full documentation](README.md)
