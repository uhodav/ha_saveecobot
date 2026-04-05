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
    sensors.append(SaveEcoBotSimpleSensor(
        marker_id, "longitude", station_info.get("longitude"), "Довгота", coordinator
    ))
    sensors.append(SaveEcoBotSimpleSensor(
        marker_id, "latitude", station_info.get("latitude"), "Широта", coordinator
    ))
    sensors.append(SaveEcoBotSimpleSensor(
        marker_id, "type_name", station_info.get("type_name"), "Тип станції", coordinator
    ))
    sensors.append(SaveEcoBotSimpleSensor(
        marker_id, "aqi", station_info.get("aqi"), "AQI", coordinator, extra_attrs={"aqi_updated_at": station_info.get("aqi_updated_at")}
    ))
    sensors.append(SaveEcoBotSimpleSensor(
        marker_id, "last_measurement_at", station_info.get("last_measurement_at"), "Час останнього вимірювання", coordinator
    ))

    # Sensors for each phenomenon in last_data
    for d in station_info.get("last_data", []):
        phenomenon = d["phenomenon"]
        value = d["value"]
        updated_at = d.get("updated_at")
        is_old = d.get("is_old")
        sensors.append(SaveEcoBotPhenomenonSensor(
            marker_id, device_name, phenomenon, value, updated_at, is_old, coordinator
        ))

    async_add_entities(sensors)

class SaveEcoBotSimpleSensor(Entity):
    def __init__(self, marker_id, key, value, name, coordinator, extra_attrs=None):
        self._param_id = f"{marker_id}_{key}"
        self._attr_unique_id = f"saveecobot_{self._param_id}_{key}"
        self.entity_id = f"sensor.saveecobot_{self._param_id}_{key}"
        self._attr_name = name
        self._key = key
        self._coordinator = coordinator
        self._extra_attrs = extra_attrs or {}
        # Icon assignment for main sensors
        icon_map = {
            "longitude": "mdi:map-marker",
            "latitude": "mdi:map-marker",
            "type_name": "mdi:factory",
            "aqi": "mdi:cloud",
            "last_measurement_at": "mdi:clock-outline",
        }
        self._attr_icon = icon_map.get(key, "mdi:cloud-question")

    @property
    def name(self):
        return self._attr_name

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def state(self):
        # Always get latest value from coordinator
        data = self._coordinator.data or {}
        if self._key in data:
            return data[self._key]
        return None

    @property
    def extra_state_attributes(self):
        return self._extra_attrs

    async def async_update(self):
        await self._coordinator.async_request_refresh()

class SaveEcoBotPhenomenonSensor(Entity):
    def __init__(self, marker_id, device_name, phenomenon, value, updated_at, is_old, coordinator):
        self._attr_unique_id = f"saveecobot_{marker_id}_{phenomenon}"
        self.entity_id = f"sensor.saveecobot_{marker_id}_{phenomenon}"
        self._attr_name = phenomenon
        self._phenomenon = phenomenon
        self._coordinator = coordinator
        self._updated_at = updated_at
        self._is_old = is_old
        self._device_name = device_name
        # Icon assignment for phenomena
        icon_map = {
            "co_mg": "mdi:molecule-co",
            "co_ppm": "mdi:molecule-co",
            "gamma": "mdi:radioactive",
            "h2s_ppb": "mdi:molecule",
            "h2s_ug": "mdi:molecule",
            "humidity": "mdi:water-percent",
            "nh3_ppb": "mdi:cloud",
            "nh3_ug": "mdi:cloud",
            "no2_ppb": "mdi:cloud",
            "no2_ug": "mdi:cloud",
            "no_ppb": "mdi:cloud",
            "no_ug": "mdi:cloud",
            "o3_ppb": "mdi:cloud",
            "o3_ug": "mdi:cloud",
            "pm1": "mdi:blur",
            "pm10": "mdi:blur",
            "pm25": "mdi:blur",
            "pressure_pa": "mdi:gauge",
            "so2_ppb": "mdi:cloud",
            "so2_ug": "mdi:cloud",
            "temperature": "mdi:thermometer",
        }
        self._attr_icon = icon_map.get(phenomenon, "mdi:cloud-question")

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, "saveecobot_device")},
            "name": self._device_name,
            "manufacturer": "SaveEcoBot",
            "model": "Device",
        }

    @property
    def name(self):
        return self._attr_name

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def state(self):
        # Always get latest value from coordinator
        data = self._coordinator.data or {}
        for d in data.get("last_data", []):
            if d["phenomenon"] == self._phenomenon:
                return d["value"]
        return None

    @property
    def extra_state_attributes(self):
        # Get latest attributes from coordinator
        data = self._coordinator.data or {}
        for d in data.get("last_data", []):
            if d["phenomenon"] == self._phenomenon:
                return {
                    "updated_at": d.get("updated_at"),
                    "is_old": d.get("is_old"),
                }
        return {}

    async def async_update(self):
        await self._coordinator.async_request_refresh()