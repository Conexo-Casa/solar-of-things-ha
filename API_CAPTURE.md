# Capturing the API data behind an "unknown" entity

Almost every `unknown` entity in this integration has the same cause: the
portal reports the value under an attribute name (or in a payload) that the
integration is not looking at. Nothing is broken on your inverter — we just
need the name your model actually uses.

There are three ways to collect that, easiest first. **Option 1 is enough for
most reports.**

---

## Option 1 — Download diagnostics from Home Assistant (recommended)

1. **Settings → Devices & Services → Solar of Things**
2. Click the **⋮** menu on the integration card → **Download diagnostics**
3. Attach the downloaded `.json` file to a GitHub issue

The file contains, per device:

| Section | What it tells us |
|---|---|
| `time_series_keys` | attribute names the history endpoint returned |
| `settings_keys` | keys present in the remote-config cache (often empty — that is normal) |
| `state_field_keys` | **every attribute your inverter publishes** — this is the important one |
| `state_fields` | the full snapshot, with each value, display label and unit |
| `resolution` | which names the integration searched, what it found, and how it mapped them |

Credentials, tokens and your account ID are stripped automatically. Device
names and readings are not, so give the file a quick look before posting it.

---

## Option 2 — Enable debug logging

Add to `configuration.yaml` and restart:

```yaml
logger:
  default: warning
  logs:
    custom_components.solar_of_things: debug
```

On the first poll after startup the integration logs one line per device
listing every attribute name it saw:

```
SolarOfThings device 8765…4321 attribute names — time-series: [...] |
settings-cache: [...] | state-snapshot: [...]
```

It also logs a warning whenever a priority value cannot be mapped onto a known
option, including the raw value and display string. Both lines are exactly what
is needed to add a mapping.

You can see the same information without the log: the two priority select
entities expose `source`, `api_key`, `raw_value` and `raw_display` as entity
attributes (**Developer tools → States**), and the *Charger Priority (current)*
/ *Output Priority (current)* diagnostic sensors show the label the API
returned verbatim.

---

## Option 3 — Run the dump script against your account

For a full capture without Home Assistant in the way:

```bash
pip install requests pycryptodome
python3 tools/dump_solar_api.py --user-id YOUR_ID --station-id YOUR_STATION_ID
```

It prompts for the password (never stored), logs in, and prints the attribute
names from all three endpoints plus how each contested value resolves. The same
data is written to `solar_of_things_dump.json`.

Your station ID is the long number in the portal URL when a station is open.

---

## Option 4 — Capture from the portal with browser DevTools

Useful when the portal shows a value that no endpoint above seems to carry —
it proves which request the web UI itself used.

1. Open <https://solar.siseli.com/#/operator/overview> and log in
2. Press **F12** → **Network** tab → filter `Fetch/XHR`
3. Tick **Preserve log**, then open the page that shows the value in question
   (the device detail page for live readings, the control panel for the
   priority settings)
4. Find the request whose **Response** contains the value you can see on screen
   — usually one of:
   - `deviceState/simple/state/latest/v1` — live readings
   - `deviceState/simple/attribute/keys/history/v1` — charts
   - `remote/device/configs/cache/get` — remote-control panel
5. Right-click the request → **Copy → Copy response**, and paste it into the
   issue

**Before pasting, remove these:** the `IOT-Token` request header, anything under
`accessToken` / `refreshToken`, and your account ID. They grant full access to
your account. Only the response *body* is needed — never the request headers.

---

## Adding a name once you have it

Attribute names live in one place, `custom_components/solar_of_things/const.py`:

- `STATE_KEY_CANDIDATES` — names in the live snapshot (selects, switches, numbers)
- `SETTING_KEY_CANDIDATES` — names in the remote-config write cache
- `TELEMETRY_STATE_FALLBACKS` — names for the measurement sensors, with the unit
  family (`"power"` → normalised to W, `"energy"` → kWh, `None` → as-is)

Add the new name to the relevant list; matching is case-insensitive, so
capitalisation does not matter. For a mode reported as an unfamiliar word
rather than a number, add it to `OUTPUT_PRIORITY_ALIASES` or
`CHARGER_PRIORITY_ALIASES` (keys are lowercase with punctuation replaced by
spaces). `tests/test_value_resolution.py` covers this logic and runs without a
Home Assistant install:

```bash
python3 -m pytest tests/ -q
```
