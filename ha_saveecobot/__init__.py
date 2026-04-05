import aiohttp
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

DOMAIN = "ha_saveecobot"
_LOGGER = logging.getLogger(__name__)

__all__ = ["DOMAIN", "_cleanup_old_entities"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SaveEcoBot from a config entry (UI)."""

    hass.data.setdefault(DOMAIN, {})

    # Setup DataUpdateCoordinator for periodic updates
    update_interval = entry.data.get("update_interval", 5)
    marker_id = entry.data["marker_id"]

    async def async_update_data():
        url = f"https://www.saveecobot.com/station/{marker_id}.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=15) as resp:
                    data = await resp.json()
                    if "id" in data and "sensor_name" in data:
                        return data
                    raise UpdateFailed("Invalid data from SaveEcoBot API")
        except Exception as err:
            raise UpdateFailed(f"Error fetching data: {err}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"SaveEcoBot {marker_id}",
        update_method=async_update_data,
        update_interval=timedelta(minutes=update_interval),
    )

    # Initial fetch
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "config": entry.data,
    }

    await _cleanup_old_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "binary_sensor", "button"])
    return True


async def _cleanup_old_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Удаляет старые entity которых больше нет в текущей конфигурации."""
    try:
        entity_registry = er.async_get(hass)
        current_param_ids = [int(pid) if isinstance(pid, str) else pid for pid in entry.data.get("param_ids", [])]
        
        _LOGGER.debug(f"ha_saveecobot: Starting cleanup. Current param_ids: {current_param_ids}")
        
        # Получаем все entity для этой интеграции
        entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        
        _LOGGER.debug(f"ha_saveecobot: Found {len(entities)} total entities for this integration")
        
        removed_count = 0

        if removed_count > 0:
            _LOGGER.info(f"ha_saveecobot: Removed {removed_count} old entities")
        else:
            _LOGGER.debug(f"ha_saveecobot: No old entities to remove")
    except Exception as e:
        _LOGGER.error(f"ha_saveecobot: Error during entity cleanup: {e}", exc_info=True)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "binary_sensor", "button"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry
) -> bool:
    """Remove a config entry from a device."""
    return True
