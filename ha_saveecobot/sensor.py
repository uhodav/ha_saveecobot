from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity
from datetime import timedelta
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.core import callback

from . import DOMAIN
from .consts.phenomenon_icons import PHENOMENON_ICONS


def _build_device_info(marker_id, device_name):
    return {
        "identifiers": {(DOMAIN, str(marker_id))},
        "name": device_name,
        "manufacturer": "SaveEcoBot",
        "model": "Device",
    }

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data["ha_saveecobot"][entry.entry_id]["coordinator"]
    marker_id = entry.data["marker_id"]
    sensors = []
    created_keys = {"longitude", "latitude", "type_name", "aqi", "last_measurement_at"}


    # Use latest data from coordinator
    station_info = coordinator.data or {}

    # Determine device name for all sensors (address or marker_id)
    device_name = station_info.get("sensor_name") or station_info.get("address") or str(marker_id)

    # Static marker ID as plain text sensor (read-only, not input)
    sensors.append(SaveEcoBotMarkerIdSensor(
        marker_id,
        device_name,
        entry.data.get("marker_id") or marker_id,
    ))

    # Sensors for coordinates, type, AQI
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
        marker_id, device_name, "aqi", coordinator, is_phenomenon=False,
          extra_attrs={
              "updated_at": station_info.get("aqi_updated_at"),
              "is_old": station_info.get("aqi_is_old")
              }
    ))
    sensors.append(SaveEcoBotSensor(
        marker_id, device_name, "last_measurement_at", coordinator, is_phenomenon=False
    ))
    sensors.append(SaveEcoBotTimerDiagnosticSensor(
        marker_id, device_name, "next_update_in", coordinator, entry
    ))

    # Sensors for each phenomenon in last_data
    for d in station_info.get("last_data", []):
        phenomenon = d["phenomenon"]
        if phenomenon in created_keys:
            continue
        created_keys.add(phenomenon)
        sensors.append(SaveEcoBotSensor(
            marker_id, device_name, phenomenon, coordinator
        ))

    async_add_entities(sensors)


class SaveEcoBotMarkerIdSensor(SensorEntity):
    def __init__(self, marker_id, device_name, value):
        self._marker_id = marker_id
        self._device_name = device_name
        self._attr_unique_id = f"saveecobot_{marker_id}_marker_id"
        self._attr_translation_key = "marker_id"
        self._attr_has_entity_name = True
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:identifier"
        self._attr_should_poll = False
        self._attr_native_value = None if value is None else str(value)
        self.entity_id = f"sensor.saveecobot_{marker_id}_marker_id"

    @property
    def suggested_object_id(self):
        return f"saveecobot_{self._marker_id}_marker_id"

    @property
    def device_info(self):
        return _build_device_info(self._marker_id, self._device_name)

    @property
    def native_value(self):
        return self._attr_native_value

class BaseSaveEcoBotCoordinatorSensor(CoordinatorEntity, SensorEntity):
    def __init__(
        self,
        marker_id,
        device_name,
        key,
        coordinator,
        *,
        icon_fallback="mdi:cloud-question",
        entity_category=None,
    ):
        super().__init__(coordinator)
        self._marker_id = marker_id
        self._device_name = device_name
        self._sensor_key = key

        self._attr_unique_id = f"saveecobot_{marker_id}_{key}"
        self._attr_translation_key = key
        self._attr_has_entity_name = True
        self._attr_icon = PHENOMENON_ICONS.get(key, icon_fallback)
        self.entity_id = f"sensor.saveecobot_{marker_id}_{key}"

        if entity_category is not None:
            self._attr_entity_category = entity_category

    @property
    def suggested_object_id(self):
        return f"saveecobot_{self._marker_id}_{self._sensor_key}"

    @property
    def device_info(self):
        return _build_device_info(self._marker_id, self._device_name)


class SaveEcoBotSensor(BaseSaveEcoBotCoordinatorSensor):
    def __init__(self, marker_id, device_name, key, coordinator, *, is_phenomenon=True, extra_attrs=None):
        super().__init__(
            marker_id,
            device_name,
            key,
            coordinator,
            entity_category=EntityCategory.DIAGNOSTIC if (not is_phenomenon and key != "aqi") else None,
        )
        self._is_phenomenon = is_phenomenon
        self._extra_attrs = extra_attrs or {}

        if key == "aqi":
            self._attr_state_class = "measurement"
            self._attr_suggested_display_precision = 0

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        if self._is_phenomenon:
            for d in data.get("last_data", []):
                if d["phenomenon"] == self._sensor_key:
                    if self._sensor_key == "pressure_pa" and d["value"] is not None:
                        return round(d["value"] / 1000, 1)
                    if self._sensor_key == "aqi" and d["value"] is not None:
                        try:
                            return int(d["value"])
                        except Exception:
                            return d["value"]
                    return d["value"]
            return None
        else:
            val = data.get(self._sensor_key)
            if self._sensor_key == "pressure_pa" and val is not None:
                return round(val / 1000, 1)
            if self._sensor_key == "aqi" and val is not None:
                try:
                    return int(val)
                except Exception:
                    return val
            return val

    @property
    def extra_state_attributes(self):
        if self._is_phenomenon:
            data = self.coordinator.data or {}
            for d in data.get("last_data", []):
                if d["phenomenon"] == self._sensor_key:
                    return {
                        "updated_at": d.get("updated_at"),
                        "is_old": d.get("is_old"),
                    }
            return {}
        else:
            if self._sensor_key == "aqi":
                data = self.coordinator.data or {}
                return {
                    **self._extra_attrs,
                    "updated_at": data.get("aqi_updated_at"),
                    "is_old": data.get("aqi_is_old"),
                }
            return self._extra_attrs


class SaveEcoBotTimerDiagnosticSensor(BaseSaveEcoBotCoordinatorSensor):
    def __init__(self, marker_id, device_name, key, coordinator, config_entry):
        super().__init__(
            marker_id,
            device_name,
            key,
            coordinator,
            icon_fallback="mdi:timer-outline",
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._config_entry = config_entry
        self._timer_unsub = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._sensor_key in {"next_update_in"}:
            self._timer_unsub = async_track_time_interval(
                self.hass,
                self._async_handle_timer_tick,
                timedelta(seconds=1),
            )

    async def async_will_remove_from_hass(self) -> None:
        if self._timer_unsub is not None:
            self._timer_unsub()
            self._timer_unsub = None
        await super().async_will_remove_from_hass()

    @callback
    def _async_handle_timer_tick(self, _now) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        runtime = self.hass.data.get(DOMAIN, {}).get(self._config_entry.entry_id) if self.hass else None
        coordinator = runtime.get("coordinator") if runtime else None

        configured_interval = int(
            self._config_entry.options.get(
                "update_interval",
                self._config_entry.data.get("update_interval", 5),
            )
        )

        interval_td = coordinator.update_interval or timedelta(minutes=configured_interval)
        interval_seconds = int(interval_td.total_seconds())

        last_update = getattr(coordinator, "last_update_success_time", None)
        if last_update is None:
            last_update = getattr(coordinator, "_last_update_success_time", None)
        if last_update is None and runtime is not None:
            last_update = runtime.get("last_refresh_at")
        if last_update is None:
            return None

        now = dt_util.utcnow()
        remaining_seconds = max(0, int((last_update + interval_td - now).total_seconds()))

        if self._sensor_key == "next_update_in":
            return f"{remaining_seconds // 60:02d}:{remaining_seconds % 60:02d}"
        return None
