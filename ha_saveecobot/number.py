from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.entity import EntityCategory

from . import DOMAIN


def _build_device_info(marker_id, device_name):
    return {
        "identifiers": {(DOMAIN, str(marker_id))},
        "name": device_name,
        "manufacturer": "SaveEcoBot",
        "model": "Device",
    }


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    marker_id = entry.data["marker_id"]
    station_info = coordinator.data or {}
    device_name = station_info.get("sensor_name") or station_info.get("address") or str(marker_id)

    async_add_entities([
        SaveEcoBotUpdateIntervalNumber(marker_id, device_name, entry),
    ])


class SaveEcoBotUpdateIntervalNumber(NumberEntity):
    def __init__(self, marker_id, device_name, config_entry):
        self._marker_id = marker_id
        self._device_name = device_name
        self._config_entry = config_entry
        self._attr_unique_id = f"saveecobot_{marker_id}_update_interval"
        self._attr_translation_key = "update_interval"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:timer"
        self._attr_mode = NumberMode.SLIDER
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_native_min_value = 1
        self._attr_native_max_value = 60
        self._attr_native_step = 1
        self.entity_id = f"number.saveecobot_{marker_id}_update_interval"

    @property
    def suggested_object_id(self):
        return f"saveecobot_{self._marker_id}_update_interval"

    @property
    def device_info(self):
        return _build_device_info(self._marker_id, self._device_name)

    @property
    def native_value(self):
        value = self._config_entry.options.get(
            "update_interval",
            self._config_entry.data.get("update_interval", 5),
        )
        return int(value)

    async def async_set_native_value(self, value):
        new_value = int(value)
        self.hass.config_entries.async_update_entry(
            self._config_entry,
            options={**self._config_entry.options, "update_interval": new_value},
        )
        await self.hass.config_entries.async_reload(self._config_entry.entry_id)