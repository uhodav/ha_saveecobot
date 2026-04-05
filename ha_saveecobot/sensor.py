from .consts.phenomenon_units import PHENOMENON_UNITS
from .consts.phenomenon_icons import PHENOMENON_ICONS

from homeassistant.helpers.translation import async_get_translations
from homeassistant.helpers.entity import Entity

from . import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["ha_saveecobot"][entry.entry_id]["coordinator"]
    marker_id = entry.data["marker_id"]
    sensors = []


    # Use latest data from coordinator
    station_info = coordinator.data or {}

    # Determine device name for all sensors (address or marker_id)
    device_name = station_info.get("sensor_name") or station_info.get("address") or str(marker_id)

    # Sensors for coordinates, type, AQI, last measurement time
    sensors.append(SaveEcoBotSensor(
        marker_id, device_name, "longitude", coordinator, is_phenomenon=False
    ))
    sensors.append(SaveEcoBotSensor(
        marker_id, device_name, "latitude", coordinator, is_phenomenon=False
    ))
    sensors.append(SaveEcoBotSensor(
        marker_id, device_name, "type_name", coordinator, is_phenomenon=False
    ))
    sensors.append(SaveEcoBotSensor(
        marker_id, device_name, "aqi", coordinator, is_phenomenon=False, extra_attrs={"aqi_updated_at": station_info.get("aqi_updated_at")}
    ))
    sensors.append(SaveEcoBotSensor(
        marker_id, device_name, "last_measurement_at", coordinator, is_phenomenon=False
    ))

    # Sensors for each phenomenon in last_data
    for d in station_info.get("last_data", []):
        phenomenon = d["phenomenon"]
        sensors.append(SaveEcoBotSensor(
            marker_id, device_name, phenomenon, coordinator, is_phenomenon=True
        ))

    async_add_entities(sensors)


# Универсальный сенсор для SaveEcoBot
class SaveEcoBotSensor(Entity):
    def __init__(self, marker_id, device_name, key, coordinator, *, is_phenomenon=False, extra_attrs=None):
        self._phenomenon = key
        self._coordinator = coordinator
        self._device_name = device_name
        self._attr_translation_key = key
        self._attr_has_entity_name = True
        self._attr_icon = PHENOMENON_ICONS.get(key, "mdi:cloud-question")
        self._translations = None
        self._is_phenomenon = is_phenomenon
        self._extra_attrs = extra_attrs or {}
        if is_phenomenon:
            self._attr_unique_id = f"saveecobot_{marker_id}_{key}"
            self.entity_id = f"sensor.saveecobot_{marker_id}_{key}"
        else:
            self._param_id = f"{marker_id}_{key}"
            self._attr_unique_id = f"saveecobot_{self._param_id}"
            self.entity_id = f"sensor.saveecobot_{self._param_id}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "saveecobot_device")},
            "name": self._device_name,
            "manufacturer": "SaveEcoBot",
            "model": "Device",
        }

    @property
    def unit_of_measurement(self):
        if self._translations:
            sensor_trans = self._translations.get("entity", {}).get("sensor", {}).get(self._phenomenon, {})
            unit = sensor_trans.get("unit")
            if unit:
                return unit
        return PHENOMENON_UNITS.get(self._phenomenon)

    async def async_added_to_hass(self) -> None:
        if hasattr(super(), "async_added_to_hass"):
            await super().async_added_to_hass()
        self._translations = await async_get_translations(self.hass, self.hass.config.language, "entity")

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def state(self):
        data = self._coordinator.data or {}
        if self._is_phenomenon:
            for d in data.get("last_data", []):
                if d["phenomenon"] == self._phenomenon:
                    return d["value"]
            return None
        else:
            return data.get(self._phenomenon)

    @property
    def extra_state_attributes(self):
        if self._is_phenomenon:
            data = self._coordinator.data or {}
            for d in data.get("last_data", []):
                if d["phenomenon"] == self._phenomenon:
                    return {
                        "updated_at": d.get("updated_at"),
                        "is_old": d.get("is_old"),
                    }
            return {}
        else:
            return self._extra_attrs

    async def async_update(self):
        await self._coordinator.async_request_refresh()