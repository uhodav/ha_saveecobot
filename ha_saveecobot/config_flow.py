import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from . import DOMAIN
import aiohttp
import logging
import json
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)


def _normalize_language_code(language: str | None) -> str:
    if not language:
        return "en"
    code = str(language).strip().lower()
    if code in {"uk", "ua", "uk-ua", "ua-ua"}:
        return "uk"
    return "en"


def _station_url(marker_id: str, language: str | None = None) -> str:
    lang = _normalize_language_code(language)
    if lang == "uk":
        return f"https://www.saveecobot.com/station/{marker_id}.json"
    return f"https://www.saveecobot.com/en/station/{marker_id}.json"


async def _fetch_station_info(marker_id: str, language: str | None = None):
    preferred_lang = _normalize_language_code(language)
    fallback_lang = "uk" if preferred_lang == "en" else "en"
    urls = [_station_url(marker_id, preferred_lang), _station_url(marker_id, fallback_lang)]

    last_error: Exception | None = None
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url, timeout=15) as resp:
                    data = await resp.json()
                    if "id" in data and "sensor_name" in data:
                        return data
                    if data.get("message") == "Station not found.":
                        return None
            except (aiohttp.ClientError, TimeoutError) as err:
                last_error = err
                continue

    if last_error is not None:
        raise last_error
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

    def _get_ui_language(self) -> str:
        try:
            return _normalize_language_code(self.hass.config.language)
        except Exception:
            return "en"

    def _dictionaries_dir(self) -> Path:
        return Path(__file__).parent / "translations" / self._get_ui_language()

    def _dictionaries_dir_candidates(self) -> list[Path]:
        base = Path(__file__).parent / "translations"
        current = self._get_ui_language()
        candidates = [base / current]
        for code in ("en", "uk"):
            path = base / code
            if path not in candidates:
                candidates.append(path)
        return candidates

    def _load_json_dict(self, file_name: str) -> dict[str, Any]:
        for directory in self._dictionaries_dir_candidates():
            path = directory / file_name
            if not path.exists():
                continue
            try:
                raw = path.read_text(encoding="utf-8-sig").strip()
                if not raw:
                    continue
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except Exception as err:
                _LOGGER.error("SaveEcoBot: failed to load %s: %s", path, err)
        return {}

    def _ensure_reference_data_loaded(self) -> bool:
        if getattr(self, "_reference_loaded", False):
            return True

        self._regions = self._load_json_dict("regions.json")
        self._cities = self._load_json_dict("cities.json")
        self._districts = self._load_json_dict("districts.json")
        self._markers = self._load_json_dict("markers.json")

        self._reference_loaded = True
        return bool(self._regions and self._cities and self._markers)

    @staticmethod
    def _make_label(name: str | None, item_id: int | str) -> str:
        text = (name or "").strip()
        return f"{text} ({item_id})" if text else f"ID {item_id}"

    def _region_options(self):
        rows = []
        for region in self._regions.values():
            region_id = region.get("region_id")
            if region_id is None:
                continue
            label = self._make_label(region.get("region_name"), region_id)
            rows.append(
                {
                    "value": str(region_id),
                    "label": label,
                }
            )
        return sorted(rows, key=lambda x: x["label"].lower())

    def _city_options(self, region_id: int):
        region = self._regions.get(str(region_id), {})
        city_ids = region.get("city_ids") or []

        rows = []
        for city_id in city_ids:
            city = self._cities.get(str(city_id))
            if not city:
                continue

            city_name = city.get("city_name")
            city_type = city.get("city_type_name")
            base = self._make_label(city_name, city_id)
            label = f"{base}, {city_type}" if city_type else base

            rows.append({"value": str(city_id), "label": label})

        return sorted(rows, key=lambda x: x["label"].lower())

    def _district_options(self, region_id: int, city_id: int):
        rows = []
        for district in self._districts.values():
            district_id = district.get("district_id")
            district_name = district.get("district_name")
            district_region_id = district.get("region_id")
            district_city_ids = district.get("city_ids") or []

            if district_id is None or int(district_id) <= 0:
                continue
            if district_region_id is None or int(district_region_id) != int(region_id):
                continue
            if int(city_id) not in [int(c) for c in district_city_ids]:
                continue
            if not district_name:
                continue

            rows.append(
                {
                    "value": str(district_id),
                    "label": self._make_label(district_name, district_id),
                }
            )

        return sorted(rows, key=lambda x: x["label"].lower())

    def _marker_options(
        self,
        city_id: int,
        district_id: int | None = None,
    ):
        city = self._cities.get(str(city_id), {})
        marker_ids = city.get("marker_ids") or []

        district_marker_ids: set[str] | None = None
        if district_id is not None:
            district = self._districts.get(str(district_id), {})
            from_district = district.get("marker_ids") or []
            if from_district:
                district_marker_ids = {str(mid) for mid in from_district}

        rows = []
        for marker_id in marker_ids:
            marker = self._markers.get(str(marker_id))
            if not marker:
                continue

            if district_id is not None:
                if district_marker_ids is not None:
                    if str(marker_id) not in district_marker_ids:
                        continue
                else:
                    marker_district_id = marker.get("district_id")
                    if marker_district_id is not None:
                        try:
                            if int(marker_district_id) != int(district_id):
                                continue
                        except Exception:
                            pass

            rows.append(
                {
                    "value": str(marker_id),
                    "label": self._make_label(marker.get("sensor_name"), marker_id),
                }
            )

        return sorted(rows, key=lambda x: x["label"].lower())

    async def async_step_user(self, user_input=None):
        errors = {}

        if not self._ensure_reference_data_loaded():
            errors["base"] = "no_options"

        region_options = self._region_options() if not errors else []
        if not errors and not region_options:
            errors["base"] = "no_options"

        if user_input is not None and not errors:
            region_id = str(user_input.get("region_id", "")).strip()
            if not region_id:
                errors["region_id"] = "required"
            elif region_id not in [o["value"] for o in region_options]:
                errors["region_id"] = "invalid"
            else:
                self._selected_region_id = int(region_id)
                return await self.async_step_city()

        region_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=region_options,
                mode=selector.SelectSelectorMode.LIST,
                sort=False,
            )
        )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("region_id"): region_selector,
            }),
            errors=errors,
            description_placeholders={"step": "1"},
        )

    async def async_step_city(self, user_input=None):
        errors = {}
        region_id = getattr(self, "_selected_region_id", None)
        if region_id is None:
            return await self.async_step_user()

        city_options = self._city_options(region_id)
        if not city_options:
            errors["base"] = "no_options"

        if user_input is not None and not errors:
            city_id = str(user_input.get("city_id", "")).strip()
            if not city_id:
                errors["city_id"] = "required"
            elif city_id not in [o["value"] for o in city_options]:
                errors["city_id"] = "invalid"
            else:
                self._selected_city_id = int(city_id)
                district_options = self._district_options(region_id, self._selected_city_id)
                if district_options:
                    return await self.async_step_district()
                self._selected_district_id = None
                return await self.async_step_marker()

        city_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=city_options,
                mode=selector.SelectSelectorMode.LIST,
                sort=False,
            )
        )

        return self.async_show_form(
            step_id="city",
            data_schema=vol.Schema({
                vol.Required("city_id"): city_selector,
            }),
            errors=errors,
            description_placeholders={"step": "2"},
        )

    async def async_step_district(self, user_input=None):
        errors = {}
        region_id = getattr(self, "_selected_region_id", None)
        city_id = getattr(self, "_selected_city_id", None)

        if region_id is None or city_id is None:
            return await self.async_step_user()

        district_options = self._district_options(region_id, city_id)
        if not district_options:
            self._selected_district_id = None
            return await self.async_step_marker()

        if user_input is not None:
            district_id = str(user_input.get("district_id", "")).strip()
            if not district_id:
                errors["district_id"] = "required"
            elif district_id not in [o["value"] for o in district_options]:
                errors["district_id"] = "invalid"
            else:
                self._selected_district_id = int(district_id)
                return await self.async_step_marker()

        district_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=district_options,
                mode=selector.SelectSelectorMode.LIST,
                sort=False,
            )
        )

        return self.async_show_form(
            step_id="district",
            data_schema=vol.Schema({
                vol.Required("district_id"): district_selector,
            }),
            errors=errors,
            description_placeholders={"step": "3"},
        )

    async def async_step_marker(self, user_input=None):
        errors = {}
        city_id = getattr(self, "_selected_city_id", None)
        district_id = getattr(self, "_selected_district_id", None)
        if city_id is None:
            return await self.async_step_user()

        draft_update_interval = getattr(self, "_draft_update_interval", 20)
        if user_input is not None:
            try:
                draft_update_interval = int(user_input.get("update_interval", draft_update_interval))
            except (TypeError, ValueError):
                errors["update_interval"] = "invalid"
            self._draft_update_interval = draft_update_interval

        marker_options = self._marker_options(city_id, district_id)
        if not marker_options:
            errors["base"] = "no_options"

        if user_input is not None and not errors:
            marker_id = str(user_input.get("marker_id", "")).strip()
            update_interval = draft_update_interval
            existing_ids = [entry.data.get("marker_id") for entry in self._async_current_entries()]

            if not marker_id:
                errors["marker_id"] = "required"
            elif marker_id not in [o["value"] for o in marker_options]:
                errors["marker_id"] = "invalid"
            elif marker_id in existing_ids:
                errors["marker_id"] = "already_configured"
            elif not (1 <= update_interval <= 60):
                errors["update_interval"] = "invalid"
            else:
                self.marker_id = marker_id
                self.update_interval = update_interval
                self.station_info = None

                try:
                    data = await _fetch_station_info(marker_id, self._get_ui_language())
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

        marker_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=marker_options,
                mode=selector.SelectSelectorMode.LIST,
                sort=False,
            )
        )

        return self.async_show_form(
            step_id="marker",
            data_schema=vol.Schema({
                vol.Required("marker_id"): marker_selector,
                vol.Required("update_interval", default=draft_update_interval): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=60,
                        mode=selector.NumberSelectorMode.SLIDER,
                    )
                ),
            }),
            errors=errors,
            description_placeholders={"step": "4"},
        )
