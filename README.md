# Lifeblood Blood Supply Levels for Home Assistant

Tracks the [Australian Red Cross Lifeblood blood supply levels](https://www.lifeblood.com.au/donors/blood-plasma-platelets/blood-supply-levels) in Home Assistant, so you can see when your blood type is running low and get a nudge to book a donation.

Lifeblood updates the figures once a day at about 6:00am (AEST/AEDT). The integration checks twice a day, at 6:30am and 6:30pm Sydney time, and when Home Assistant starts. If a check fails it retries after 30 minutes, then backs off until the next scheduled check.

☕ If this integration's useful to you, [buy me a coffee](https://ko-fi.com/gurrier).

## Installation

### HACS (recommended)

Lifeblood Blood Supply Levels is in the HACS default store, so HACS installs it and offers updates like any other integration.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gurrier&repository=lifeblood&category=integration)

Click the badge above, or:

1. In HACS, search for **Lifeblood**.
2. Open **Lifeblood Blood Supply Levels**, select **Download**, and restart Home Assistant.

If you added this repository to HACS as a custom repository before it was in the default store, there's nothing to change: updates keep coming through HACS.

### Manual

Only if you don't use HACS. You'll need to repeat these steps for every update.

1. On the [latest release](https://github.com/gurrier/lifeblood/releases/latest), download **Source code (zip)** and unzip it.
2. Copy the `custom_components/lifeblood` folder into your Home Assistant `config/custom_components/` folder (create `custom_components` if it doesn't exist). You should end up with `config/custom_components/lifeblood/manifest.json`.
3. Restart Home Assistant.

To update, replace the folder with the one from the new release and restart again.

## Setup

**Settings → Devices & services → Add integration → Lifeblood Blood Supply Levels**

- **Region**: All Australia, or a state or territory.
- **Blood types**: tick the ones you care about (your own type, or everyone's in the house). You can change this later with **Configure**.

To track more than one region, add the integration again.

## Entities

Each region is its own device, named with the short code (`NSW`, `VIC`, `Australia`) so entity names stay short on dashboard buttons: "NSW A positive". For a region, e.g. Victoria:

| Entity | Example state | Notes |
|---|---|---|
| `sensor.lifeblood_vic_o_positive` … `ab_negative` | `critical` | One per ticked red cell blood type |
| `sensor.lifeblood_vic_plasma` | `ok` | Plasma, all blood types |
| `sensor.lifeblood_vic_plasma_shortfall` | `0` % | Disabled by default (see below). How far plasma supply is below Lifeblood's target, e.g. NSW `3.72` %. `0` means on or above target. The raw figure is in the `percent_of_target` attribute (e.g. `100.11`) |
| `sensor.lifeblood_vic_last_updated` | timestamp | When Lifeblood last published |

The blood type sensors are enum sensors, worst first:

| State | Shown as | Lifeblood's meaning |
|---|---|---|
| `critical` | Critical | Lifeblood is running an appeal for red cells. Shown on the site over "Very low". |
| `urgent` | Urgent | Lifeblood is running an appeal for plasma. Shown on the site over "Very low". |
| `very_low` | Very low | Give blood now |
| `low` | Low | Give blood now |
| `need_more` | Need more | Give in the next 5 days or so |
| `ok` | Ok | Could give blood, or consider plasma |
| `good` | Good | Supply is strong; consider plasma |
| `not_collected` | Not collected | Red cells for this type aren't collected in this region |

Plasma can show any of these except `not_collected`. Lifeblood's legend only lists Need more, Ok and Good for plasma, but it ran an "Urgent" plasma appeal in October 2026.

The plasma shortfall comes from a percentage Lifeblood includes in the page's markup but doesn't show on the site or document. It usually tracks the plasma level (a shortfall of about 2% or more has shown as "Need more"), but not always: during the October 2026 "Urgent" appeal it was above 100% everywhere, so the shortfall read 0. Use the Plasma level sensor for alerts. The percentage may disappear if Lifeblood changes the page.

Because of that, Plasma shortfall is disabled by default for new installs. To use it, open the sensor under **Settings → Devices & services → Lifeblood Blood Supply Levels**, select **Settings** (the cog), and turn on **Enabled**. Installs from before v0.3.0 keep it enabled.

Each blood type sensor also has a `label` attribute: the text exactly as shown on the site.

## Dashboard card

Home Assistant's suggested cards for a device are chosen by Home Assistant, not the integration. For a compact list, add an Entities card instead, and set short names:

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

## Get notified when your blood type is needed

The easiest way is the included blueprint. Pick your blood type sensor, the levels you want to hear about, and your phone (it uses the Home Assistant Companion app):

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fgurrier%2Flifeblood%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Flifeblood%2Fblood_type_in_demand.yaml)

Then **Settings → Automations & scenes → Blueprints → Lifeblood - notify when a blood type is in demand → Create automation**.

It defaults to Critical, Urgent and Very low, and only notifies when the level gets worse: an improvement from Critical back to Very low stays quiet, and so do restarts and website outages. Make one automation per blood type, or per person in the house.

### Writing your own automation

If you'd rather write it yourself, for example to notify a whole household:

```yaml
automation:
  - alias: "Lifeblood: O- needs donors"
    triggers:
      - trigger: state
        entity_id: sensor.lifeblood_vic_o_negative
        to:
          - very_low
          - critical
        not_from:
          - unavailable
          - unknown
    actions:
      - action: notify.notify
        data:
          title: "Blood supply"
          message: >
            O- is {{ state_attr('sensor.lifeblood_vic_o_negative', 'label') }}
            in Victoria. Book a donation: https://www.lifeblood.com.au
```

## How it works

There's no public API. The integration reads the same server-rendered page you see in a browser. For a state or territory, it makes the same request the page's region dropdown does. If Lifeblood redesigns the page, the sensors will go unavailable until the integration is updated. Download diagnostics from the integration page and open an issue.

This project isn't affiliated with or endorsed by Australian Red Cross Lifeblood.

## Development

```bash
pip install -r requirements_test.txt
python -m pytest
```

`python scripts/check_live_site.py` runs the parser against Lifeblood's live site for every region and fails if anything doesn't parse cleanly. GitHub runs it every morning after Lifeblood's update.
