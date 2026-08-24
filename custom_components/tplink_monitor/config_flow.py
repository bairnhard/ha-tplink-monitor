import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_SCAN_INTERVAL, CONF_MTU, CONF_IP, CONF_USERNAME, CONF_PASSWORD, CONF_PORT_NAMES

_LOGGER = logging.getLogger(__name__)

# Explicitly Register the Config Flow Handler
@config_entries.HANDLERS.register(DOMAIN)
class TPLinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TP-Link Monitor."""

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input:
            try:
                from .tplink_monitor import fetch_port_statistics
                result = await self.hass.async_add_executor_job(
                    fetch_port_statistics, user_input[CONF_IP], user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
                if result is None:
                    errors["base"] = "auth_failed"  # Uses `en.json`
                else:
                    # Collect 24 individual port_name_N fields into a list
                    port_names = [user_input.get(f"port_name_{i}", "") for i in range(1, 25)]

                    data = {
                        CONF_IP: user_input[CONF_IP],
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, 15),
                        CONF_MTU: user_input.get(CONF_MTU, 1500),
                        CONF_PORT_NAMES: port_names,
                    }

                    return self.async_create_entry(title="TP-Link Switch", data=data)
            except Exception:
                _LOGGER.exception("Unexpected error during validation")
                errors["base"] = "cannot_connect"  # Uses `en.json`

        # Build a schema with 24 optional port name fields
        base_schema = {
            vol.Required(CONF_IP): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=15): int,
            vol.Optional(CONF_MTU, default=1500): int,
        }

        # Add 24 optional per-port name fields named port_name_1 ... port_name_24
        schema_dict = {**base_schema}
        for i in range(1, 25):
            schema_dict[vol.Optional(f"port_name_{i}", default="")] = str

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )
    @staticmethod
    @callback
    def async_get_options_flow(entry):
        """Return the options flow handler."""
        return TPLinkOptionsFlowHandler(entry)


class TPLinkOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for TP-Link Monitor."""

    def __init__(self, entry):
        """Initialize options flow."""
        self.entry = entry

    async def async_step_init(self, user_input=None):
        """Manage options."""
        if user_input:
            # Build options dict: scan interval, mtu, and 24 port names
            port_names = [user_input.get(f"port_name_{i}", "") for i in range(1, 25)]
            options = {
                CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, self.entry.options.get(CONF_SCAN_INTERVAL, 15)),
                CONF_MTU: user_input.get(CONF_MTU, self.entry.options.get(CONF_MTU, 1500)),
                CONF_PORT_NAMES: port_names,
            }
            return self.async_create_entry(title="", data=options)

        # Prepare defaults for the 24 port name fields from options or data
        current_port_names = self.entry.options.get(CONF_PORT_NAMES, None)
        if current_port_names is None:
            current_port_names = self.entry.data.get(CONF_PORT_NAMES, [""] * 24)

        # Ensure we have a list of length 24
        if isinstance(current_port_names, list):
            defaults = list(current_port_names) + [""] * (24 - len(current_port_names))
            defaults = defaults[:24]
        else:
            defaults = [""] * 24

        # Build schema with 24 port name fields
        schema = {
            vol.Optional(CONF_SCAN_INTERVAL, default=self.entry.options.get(CONF_SCAN_INTERVAL, 15)): int,
            vol.Optional(CONF_MTU, default=self.entry.options.get(CONF_MTU, 1500)): int,
        }
        for i in range(1, 25):
            schema[vol.Optional(f"port_name_{i}", default=defaults[i - 1])] = str

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )
