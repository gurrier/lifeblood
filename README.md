# Lifeblood Blood Supply Levels for Home Assistant

Tracks the [Australian Red Cross Lifeblood blood supply levels](https://www.lifeblood.com.au/donors/blood-plasma-platelets/blood-supply-levels) in Home Assistant, so you can see when your blood type is running low and get a nudge to book a donation.

Lifeblood updates the figures once a day at about 6:00am (AEST/AEDT). The integration checks hourly.

☕ If this integration's useful to you, [buy me a coffee](https://ko-fi.com/gurrier).

## Installation

### Manual

1. Download this repository: **Code → Download ZIP**, and unzip it.
2. Copy the `custom_components/lifeblood` folder into your Home Assistant `config/custom_components/` folder (create `custom_components` if it doesn't exist). You should end up with `config/custom_components/lifeblood/manifest.json`.
3. Restart Home Assistant.

To update, replace the folder with the new version and restart again.

### HACS (custom repository)

This integration isn't in the HACS default store yet, but you can add it yourself:

1. In HACS, open the menu → **Custom repositories**, and add `https://github.com/gurrier/lifeblood` as an **Integration**.
2. Install **Lifeblood Blood Supply Levels** and restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → Lifeblood Blood Supply Levels**

- **Region**: All Australia, or a state or territory.
- **Blood types**: tick the ones you care about (your own type, or everyone's in the house). You can change this later with **Configure**.

To track more than one region, add the integration again.

## Entities

For a region, e.g. Victoria:

| Entity | Example state | Notes |
|---|---|---|
| `sensor.lifeblood_victoria_o_positive` … `ab_negative` | `critical` | One per ticked red cell blood type |
| `sensor.lifeblood_victoria_plasma` | `ok` | Plasma, all blood types |
| `sensor.lifeblood_victoria_plasma_supply` | `100.11` % | The figure Lifeblood attaches to the plasma level |
| `sensor.lifeblood_victoria_last_updated` | timestamp | When Lifeblood last published |

The blood type sensors are enum sensors, worst first:

| State | Shown as | Lifeblood's meaning |
|---|---|---|
| `critical` | Critical | Lifeblood is running an appeal. Shown on the site over "Very low". |
| `very_low` | Very low | Give blood now |
| `low` | Low | Give blood now |
| `need_more` | Need more | Give in the next 5 days or so |
| `ok` | Ok | Could give blood, or consider plasma |
| `good` | Good | Supply is strong; consider plasma |
| `not_collected` | Not collected | Red cells for this type aren't collected in this region |

Plasma uses only `need_more`, `ok` and `good`.

Each blood type sensor also has a `label` attribute (the text exactly as shown on the site) and an `appeal` attribute (`true` when the "Critical" appeal banner is showing).

## Example automation

Notify when your blood type drops to Low or worse:

```yaml
automation:
  - alias: "Lifeblood: O- needs donors"
    triggers:
      - trigger: state
        entity_id: sensor.lifeblood_victoria_o_negative
        to:
          - low
          - very_low
          - critical
    actions:
      - action: notify.notify
        data:
          title: "Blood supply"
          message: >
            O- is {{ states('sensor.lifeblood_victoria_o_negative') | replace('_', ' ') }}
            in Victoria. Book a donation: https://www.lifeblood.com.au
```

## How it works

There's no public API. The integration reads the same server-rendered page you see in a browser. For a state or territory, it makes the same request the page's region dropdown does. If Lifeblood redesigns the page, the sensors will go unavailable until the integration is updated. Download diagnostics from the integration page and open an issue.

This project isn't affiliated with or endorsed by Australian Red Cross Lifeblood.
