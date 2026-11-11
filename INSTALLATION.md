# Installation Guide

## Requirements

- Home Assistant **2023.6** or newer
- Active account at [solar.siseli.com](https://solar.siseli.com)
- Network access from HA to `https://solar.siseli.com`

---

## Method 1: Marketplace or HACS (Recommended)

### Marketplace (Home Assistant 2026.11 and newer)

[![Open your Home Assistant instance and show this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Conexo-Casa&repository=solar-of-things-ha&category=integration)

Or by hand:

1. Go to **Settings → Marketplace**.
2. Select **Add from link** (top right) and enter `Conexo-Casa/solar-of-things-ha`.
   The first time, Home Assistant asks you to connect GitHub. That is a one-time,
   read-only sign-in on github.com.
3. Open **Solar of Things** and select **Install**. The setup screen opens right away; a first
   install doesn't need a restart.

Updates show up under **Settings → Updates**. After an update, Home Assistant shows a
repair that offers to restart.

### HACS (Home Assistant 2026.10 and older)

1. HACS → **Integrations** → **⋮** → **Custom repositories**.
2. Add `https://github.com/Conexo-Casa/solar-of-things-ha`, category **Integration**.
3. Download **Solar of Things**, then restart Home Assistant.

An existing HACS install moves to the Marketplace by itself when you upgrade to 2026.11.

Then go to **Settings → Devices & Services → + Add Integration** → search
**Solar of Things** if the setup screen didn't open by itself.

---

## Method 2: Manual

1. Download the latest release ZIP from:
   **[github.com/Conexo-Casa/solar-of-things-ha/releases/latest](https://github.com/Conexo-Casa/solar-of-things-ha/releases/latest)**

2. Extract and copy the `solar_of_things` folder to your HA config directory:
   ```
   /config/custom_components/solar_of_things/
   ```

   The final structure must be:
   ```
   /config/custom_components/solar_of_things/
   ├── __init__.py
   ├── api.py
   ├── config_flow.py
   ├── const.py
   ├── manifest.json
   ├── number.py
   ├── select.py
   ├── sensor.py
   ├── strings.json
   ├── switch.py
   └── translations/
       └── en.json
   ```

3. **Restart Home Assistant.**

4. Go to **Settings → Devices & Services → + Add Integration** → search **Solar of Things**.

---

## Verifying Installation

After restarting, go to **Settings → System → Logs**. If you see a line like:

```
Setting up custom_components.solar_of_things
```

with no errors, the component loaded correctly.

---

## Upgrading

### Via the Marketplace (2026.11+)
1. **Settings → Updates** → **Solar of Things** → **Install**.
2. Restart when the repair asks you to.

### Via HACS (2026.10 and older)
1. HACS → Integrations → find Solar of Things → **Update**.
2. Restart Home Assistant.

### Manual
1. Download the new release ZIP.
2. Replace the contents of `/config/custom_components/solar_of_things/`.
3. Restart Home Assistant.

> **Note:** When upgrading from v2.3.x or earlier, the config entry will be
> automatically migrated. No re-authentication is needed if you already use
> User ID + Password auth.

---

## Uninstalling

1. **Settings → Devices & Services → Solar of Things → Delete**.
2. Remove `/config/custom_components/solar_of_things/` from your HA filesystem.
3. Restart Home Assistant.
