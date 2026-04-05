from homeassistant.helpers.entity import Entity

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["ha_saveecobot"][entry.entry_id]["coordinator"]
    marker_id = entry.data["marker_id"]
    sensors = []

    # Use latest data from coordinator
    station_info = coordinator.data or {}

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
            marker_id, phenomenon, value, updated_at, is_old, coordinator
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
    def __init__(self, marker_id, phenomenon, value, updated_at, is_old, coordinator):
        self._attr_unique_id = f"saveecobot_{marker_id}_{phenomenon}"
        self.entity_id = f"sensor.saveecobot_{marker_id}_{phenomenon}"
        self._attr_name = phenomenon
        self._phenomenon = phenomenon
        self._coordinator = coordinator
        self._updated_at = updated_at
        self._is_old = is_old

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