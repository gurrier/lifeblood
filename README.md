# Lifeblood Blood Supply Levels for Home Assistant

Tracks the [Australian Red Cross Lifeblood blood supply levels](https://www.lifeblood.com.au/donors/blood-plasma-platelets/blood-supply-levels) in Home Assistant, so you can see when your blood type is running low and get a nudge to book a donation.

Lifeblood updates the figures once a day at about 6:00am (AEST/AEDT). The integration checks twice a day, at 6:30am and 6:30pm Sydney time, and when Home Assistant starts.

☕ If this integration's useful to you, [buy me a coffee](https://ko-fi.com/gurrier).

## Installation

### HACS (recommended)

This integration isn't in the HACS default store yet, but you can add it to HACS as a custom repository and get updates through HACS like any other integration.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gurrier&repository=lifeblood&category=integration)

Click the badge above, or add it by hand:

1. In HACS, open the menu → **Custom repositories**, and add `https://github.com/gurrier/lifeblood` as an **Integration**.
2. Install **Lifeblood Blood Supply Levels** and restart Home Assistant.

### Manual

1. Download this repository: **Code → Download ZIP**, and unzip it.
2. Copy the `custom_components/lifeblood` folder into your Home Assistant `config/custom_components/` folder (create `custom_components` if it doesn't exist). You should end up with `config/custom_components/lifeblood/manifest.json`.
3. Restart Home Assistant.

To update, replace the folder with the new version and restart again.

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
| `sensor.lifeblood_victoria_plasma_shortfall` | `0` % | How far plasma supply is below Lifeblood's target, e.g. NSW `3.72` %. `0` means on or above target. The raw figure is in the `percent_of_target` attribute (e.g. `100.11`) |
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

The plasma shortfall comes from a percentage Lifeblood includes in the page's markup but doesn't show on the site or document. It behaves like supply against target: so far, a shortfall of about 2% or more has shown as "Need more". It may disappear if Lifeblood changes the page.

Each blood type sensor also has a `label` attribute (the text exactly as shown on the site) and an `appeal` attribute (`true` when the "Critical" appeal banner is showing).

## Dashboard card

Each region is its own device, named for the region (e.g. "NSW"), so entities show as "NSW A positive". Home Assistant's suggested cards for a device are chosen by Home Assistant, not the integration. For a compact list, add an Entities card instead, and set short names:

```yaml
type: entities
title: Blood supply NSW
entities:
  - entity: sensor.lifeblood_nsw_a_positive
    name: A+
  - entity: sensor.lifeblood_nsw_plasma
    name: Plasma
  - entity: sensor.lifeblood_nsw_plasma_shortfall
    name: Plasma shortfall
  - entity: sensor.lifeblood_nsw_last_updated
    name: Updated
```

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
