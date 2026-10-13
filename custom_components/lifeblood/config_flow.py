"""Config and options flows for the Lifeblood integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import selected_blood_types
from .api import LifebloodClient, LifebloodConnectionError, LifebloodError
from .const import (
    ALL_BLOOD_TYPES,
    CONF_BLOOD_TYPES,
    CONF_REGION,
    DOMAIN,
    REGION_FORM_VALUES,
    REGION_NAMES,
)
from .coordinator import USER_AGENT_TEMPLATE, LifebloodConfigEntry

_LOGGER = logging.getLogger(__name__)

REGION_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=list(REGION_FORM_VALUES),
        mode=SelectSelectorMode.DROPDOWN,
        translation_key=CONF_REGION,
    )
)

BLOOD_TYPES_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=ALL_BLOOD_TYPES,
        multiple=True,
        mode=SelectSelectorMode.LIST,
        translation_key=CONF_BLOOD_TYPES,
    )
)


class LifebloodConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per region; add the integration again for another region."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            region = user_input[CONF_REGION]
            await self.async_set_unique_id(region)
            self._abort_if_unique_id_configured()

            if not user_input[CONF_BLOOD_TYPES]:
                errors[CONF_BLOOD_TYPES] = "no_blood_types"
            else:
                # Fetch once before creating the entry, so a site that's down
                # or a page layout we no longer understand shows up here
                # rather than as an entry that never finishes setting up.
                client = LifebloodClient(
                    async_get_clientsession(self.hass),
                    USER_AGENT_TEMPLATE.format(version="config-flow"),
                )
                try:
                    await client.async_get_levels(region)
                except LifebloodConnectionError:
                    errors["base"] = "cannot_connect"
                except LifebloodError:
                    _LOGGER.exception("Lifeblood page didn't parse")
                    errors["base"] = "cannot_parse"
                else:
                    return self.async_create_entry(
                        title=f"Lifeblood {REGION_NAMES[region]}",
                        data={
                            CONF_REGION: region,
                            CONF_BLOOD_TYPES: user_input[CONF_BLOOD_TYPES],
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_REGION): REGION_SELECTOR,
                        vol.Required(CONF_BLOOD_TYPES): BLOOD_TYPES_SELECTOR,
                    }
                ),
                user_input
                or {CONF_REGION: "national", CONF_BLOOD_TYPES: ALL_BLOOD_TYPES},
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: LifebloodConfigEntry) -> OptionsFlow:
        return LifebloodOptionsFlowHandler()


class LifebloodOptionsFlowHandler(OptionsFlow):
    """Change which blood types an entry tracks."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_BLOOD_TYPES]:
                errors[CONF_BLOOD_TYPES] = "no_blood_types"
            else:
                # Saved to options; the update listener in __init__.py
                # reloads the entry, which adds or removes the entities.
                return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_BLOOD_TYPES): BLOOD_TYPES_SELECTOR}),
                user_input
                or {CONF_BLOOD_TYPES: selected_blood_types(self.config_entry)},
            ),
            errors=errors,
        )
