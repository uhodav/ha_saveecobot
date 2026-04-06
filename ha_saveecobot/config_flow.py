import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from . import DOMAIN
import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)


async def _fetch_station_info(marker_id: str):
    url = f"https://www.saveecobot.com/station/{marker_id}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=15) as resp:
            data = await resp.json()
            if "id" in data and "sensor_name" in data:
                return data
            if data.get("message") == "Station not found.":
                return None
            raise ValueError("invalid_marker")


class HaSaveEcobotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SaveEcoBot."""

    @staticmethod
    def build_entry(marker_id, update_interval, station_info):
        update_interval = int(update_interval)
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

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            marker_id = str(user_input.get("marker_id", "")).strip()
            update_interval = int(user_input.get("update_interval", 5))
            existing_ids = [entry.data.get("marker_id") for entry in self._async_current_entries()]
            if not marker_id:
                errors["marker_id"] = "required"
            elif not marker_id.isdigit():
                errors["marker_id"] = "digits_only"
            elif marker_id in existing_ids:
                errors["marker_id"] = "already_configured"
            elif not (1 <= update_interval <= 60):
                errors["update_interval"] = "invalid"
            else:
                self.marker_id = marker_id
                self.update_interval = update_interval
                self.station_info = None
                # Перевіряємо коректність marker_id
                try:
                    data = await _fetch_station_info(marker_id)
                    if data is None:
                        errors["marker_id"] = "not_found"
                    else:
                        self.station_info = data
                except ValueError:
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
