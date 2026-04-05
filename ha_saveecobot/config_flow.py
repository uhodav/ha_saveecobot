import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from . import DOMAIN, _cleanup_old_entities
import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)


class HaSaveEcobotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SaveEcoBot."""

    @staticmethod
    def build_entry(marker_id, update_interval, station_info):
        city = station_info.get("city_name", "") if station_info else ""
        address = station_info.get("sensor_name", "") if station_info else ""
        title = f"{city} {address}".strip() or str(marker_id)
        data = {
            "marker_id": marker_id,
            "update_interval": update_interval,
            "station_info": station_info,
        }
        return title, data

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    @staticmethod
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return HaSaveEcobotOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            marker_id = str(user_input.get("marker_id", "")).strip()
            update_interval = user_input.get("update_interval", 5)
            existing_ids = [entry.data.get("marker_id") for entry in self._async_current_entries()]
            if not marker_id:
                errors["marker_id"] = "required"
            elif not marker_id.isdigit():
                errors["marker_id"] = "digits_only"
            elif marker_id in existing_ids:
                errors["marker_id"] = "already_configured"
            elif not (1 <= update_interval <= 20):
                errors["update_interval"] = "invalid"
            else:
                self.marker_id = marker_id
                self.update_interval = update_interval
                self.station_info = None
                # Перевіряємо коректність marker_id
                url = f"https://www.saveecobot.com/station/{marker_id}.json"
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, timeout=15) as resp:
                            data = await resp.json()
                            # Если пришёл корректный ответ (есть id и sensor_name), считаем marker_id валидним
                            if "id" in data and "sensor_name" in data:
                                self.station_info = data  # сохраняем ответ для дальнейшего использования
                            elif data.get("message") == "Station not found.":
                                errors["marker_id"] = "not_found"
                            else:
                                errors["marker_id"] = "invalid_marker"
                except Exception as e:
                    _LOGGER.error(f"SaveEcoBot: health check error: {e}")
                    errors["base"] = "cannot_connect"
                
                if not errors:
                    title, data = self.build_entry(
                        self.marker_id,
                        self.update_interval,
                        self.station_info,
                    )
                    return self.async_create_entry(title=title, data=data)
        
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("marker_id"): cv.positive_int,
                vol.Required("update_interval", default=5): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }),
            errors=errors,
            description_placeholders={"step": "1"},
        )

class HaSaveEcobotOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for HaSaveEcobot."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        _LOGGER.debug(f"ha_saveecobot Options: async_step_init called with user_input={user_input}")
        try:
            return await self.async_step_marker_id()
        except Exception as e:
            _LOGGER.error(f"ha_saveecobot Options: Error in async_step_init: {e}", exc_info=True)
            raise

    async def async_step_marker_id(self, user_input=None):
        _LOGGER.debug(f"ha_saveecobot Options: async_step_marker_id called with user_input={user_input}")
        errors = {}
        current_data = self.station_info if hasattr(self, "station_info") and self.station_info else self.config_entry.data
        _LOGGER.debug(f"ha_saveecobot Options: current_data={current_data}")
        
        try:
            if user_input is not None:
                marker_id = str(user_input.get("marker_id", "")).strip().rstrip("/")
                update_interval = user_input.get("update_interval", 5)
                old_marker_id = str(current_data.get("marker_id", ""))
                marker_id_changed = marker_id and marker_id != old_marker_id
                if not marker_id:
                    errors["marker_id"] = "required"
                elif not marker_id.isdigit():
                    errors["marker_id"] = "digits_only"
                elif not (1 <= update_interval <= 60):
                    errors["update_interval"] = "invalid"
                else:
                    # Если marker_id изменился — удаляем старые сущности
                    if marker_id_changed:
                        try:
                            await _cleanup_old_entities(self.config_entry.hass, old_marker_id)
                        except Exception as e:
                            _LOGGER.error(f"Error cleaning up old entities for marker_id {old_marker_id}: {e}")
                    self.marker_id = marker_id
                    self.update_interval = update_interval
                    data = {
                        "marker_id": marker_id,
                        "update_interval": update_interval,
                    }
                    result = self.async_create_entry(title=marker_id, data=data)

                    try:
                        await self.config_entry.hass.config_entries.async_reload(self.config_entry.entry_id)
                    except Exception as e:
                        _LOGGER.error(f"Error reloading config entry after options update: {e}")
                    return result
        except Exception as e:
            _LOGGER.error(f"ha_saveecobot Options: Error in async_step_marker_id: {e}", exc_info=True)
            errors["base"] = "unknown"
        
        _LOGGER.debug(f"ha_saveecobot Options: Showing api form with errors={errors}")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("marker_id", default=current_data.get("marker_id", "")): cv.positive_int,
                vol.Required("update_interval", default=current_data.get("update_interval", 5)): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }),
            errors=errors,
        )