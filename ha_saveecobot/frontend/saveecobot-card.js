const CARD_TAG = "saveecobot-card";

const AQI_STALE = {
  color: "#bbbbbb",
  short: { en: "N/A", uk: "с/д" },
  label: {
    en: "Data is stale or insufficient",
    uk: "Дані застарілі або їх недостатньо",
  },
  range: { en: "stale", uk: "с/д" },
};

const AQI_LEVELS = [
  {
    max: 50,
    color: "#17a355",
    short: { en: "0-50", uk: "0-50" },
    label: { en: "Good level", uk: "Добрий рівень" },
    range: { en: "0-50", uk: "0-50" },
  },
  {
    max: 100,
    color: "#F8CC4A",
    short: { en: "51-100", uk: "51-100" },
    label: { en: "Moderate level", uk: "Помірний рівень" },
    range: { en: "51-100", uk: "51-100" },
  },
  {
    max: 150,
    color: "#FF9A01",
    short: { en: "101-150", uk: "101-150" },
    label: {
      en: "Unhealthy for sensitive groups",
      uk: "Шкідливий рівень для чутливих груп",
    },
    range: { en: "101-150", uk: "101-150" },
  },
  {
    max: 200,
    color: "#ea270d",
    short: { en: "151-200", uk: "151-200" },
    label: { en: "Unhealthy level", uk: "Шкідливий рівень" },
    range: { en: "151-200", uk: "151-200" },
  },
  {
    max: 300,
    color: "#7c2c85",
    short: { en: "201-300", uk: "201-300" },
    label: { en: "Very unhealthy level", uk: "Дуже шкідливий рівень" },
    range: { en: "201-300", uk: "201-300" },
  },
  {
    max: Infinity,
    color: "#66001f",
    short: { en: "301+", uk: "301+" },
    label: { en: "Hazardous level", uk: "Небезпечний рівень" },
    range: { en: "301+", uk: "301+" },
  },
];

const LABELS = {
  en: {
    titleFallback: "SaveEcoBot",
    aqi: "AQI",
    pm25: "PM2.5",
    pm10: "PM10",
    temperature: "Temperature",
    humidity: "Humidity",
    updatedAt: "Updated",
    stale: "Stale data",
    fresh: "Fresh data",
    range: "Range",
    unavailable: "Unavailable",
    configure: "Provide marker_id or explicit entities",
  },
  uk: {
    titleFallback: "SaveEcoBot",
    aqi: "AQI",
    pm25: "PM2.5",
    pm10: "PM10",
    temperature: "Температура",
    humidity: "Вологість",
    updatedAt: "Оновлено",
    stale: "Дані застарілі",
    fresh: "Дані актуальні",
    range: "Діапазон",
    unavailable: "Недоступно",
    configure: "Вкажіть marker_id або явні entity",
  },
};

class SaveEcoBotCard extends HTMLElement {
  setConfig(config) {
    if (!config.marker_id && !config.aqi_entity) {
      throw new Error("SaveEcoBot card requires 'marker_id' or 'aqi_entity'");
    }

    this._config = {
      title: null,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._card) {
      this._card = document.createElement("ha-card");
      this._card.style.overflow = "hidden";
      this._card.style.cursor = "pointer";
      this._card.addEventListener("click", () => {
        const aqiEntityId = this._entityId("aqi", "aqi_entity");
        if (aqiEntityId) {
          this._fire("hass-more-info", { entityId: aqiEntityId });
        }
      });
      this.appendChild(this._card);
    }

    this._render();
  }

  getCardSize() {
    return 4;
  }

  static getStubConfig() {
    return {
      type: `custom:${CARD_TAG}`,
      marker_id: "14634",
      title: "SaveEcoBot",
    };
  }

  _lang() {
    const lang = this._hass?.locale?.language || this._hass?.language || "en";
    return String(lang).startsWith("uk") ? "uk" : "en";
  }

  _t(key) {
    return LABELS[this._lang()][key] || LABELS.en[key] || key;
  }

  _entityId(key, explicitKey) {
    if (this._config?.[explicitKey]) {
      return this._config[explicitKey];
    }
    if (this._config?.marker_id) {
      return `sensor.saveecobot_${this._config.marker_id}_${key}`;
    }
    return null;
  }

  _stateObj(key, explicitKey) {
    const entityId = this._entityId(key, explicitKey);
    return entityId ? this._hass.states[entityId] : undefined;
  }

  _aqiLevel(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return {
        color: AQI_STALE.color,
        label: AQI_STALE.label[this._lang()] || AQI_STALE.label.en,
        short: AQI_STALE.short[this._lang()] || AQI_STALE.short.en,
        range: AQI_STALE.range[this._lang()] || AQI_STALE.range.en,
      };
    }
    const level = AQI_LEVELS.find((item) => numeric <= item.max) || AQI_LEVELS[AQI_LEVELS.length - 1];
    return {
      color: level.color,
      label: level.label[this._lang()] || level.label.en,
      short: level.short[this._lang()] || level.short.en,
      range: level.range[this._lang()] || level.range.en,
    };
  }

  _formatState(stateObj, fractionDigits = null) {
    if (!stateObj || ["unknown", "unavailable", null, undefined].includes(stateObj.state)) {
      return "—";
    }

    let value = stateObj.state;
    const numeric = Number(value);
    if (Number.isFinite(numeric) && fractionDigits !== null) {
      value = numeric.toFixed(fractionDigits);
    }

    const unit = stateObj.attributes.unit_of_measurement || "";
    return unit ? `${value} ${unit}` : `${value}`;
  }

  _formatUpdatedAt(value) {
    if (!value) {
      return "—";
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }

    try {
      return new Intl.DateTimeFormat(this._lang() === "uk" ? "uk-UA" : "en-US", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
    } catch (_err) {
      return date.toLocaleString();
    }
  }

  _title(aqiState) {
    if (this._config.title) {
      return this._config.title;
    }
    const friendlyName = aqiState?.attributes?.friendly_name;
    if (friendlyName) {
      return friendlyName;
    }
    if (this._config.marker_id) {
      return `${this._t("titleFallback")} ${this._config.marker_id}`;
    }
    return this._t("titleFallback");
  }

  _metric(label, value, icon, accent = false) {
    return `
      <div class="metric ${accent ? "metric--accent" : ""}">
        <div class="metric__icon">${icon}</div>
        <div class="metric__body">
          <div class="metric__label">${label}</div>
          <div class="metric__value">${value}</div>
        </div>
      </div>
    `;
  }

  _render() {
    if (!this._config) {
      return;
    }

    const aqiState = this._stateObj("aqi", "aqi_entity");
    const pm25State = this._stateObj("pm25", "pm25_entity");
    const pm10State = this._stateObj("pm10", "pm10_entity");
    const temperatureState = this._stateObj("temperature", "temperature_entity");
    const humidityState = this._stateObj("humidity", "humidity_entity");

    if (!aqiState && !this._config.marker_id) {
      this._card.innerHTML = `
        <div class="wrapper error">
          <div class="title">SaveEcoBot</div>
          <div class="subtitle">${this._t("configure")}</div>
        </div>
        ${this._styles()}
      `;
      return;
    }

    const aqiValue = aqiState?.state;
    const isOld = Boolean(aqiState?.attributes?.is_old);
    const level = this._aqiLevel(aqiValue);
    const updatedAt = aqiState?.attributes?.updated_at;

    const statusText = isOld ? this._t("stale") : this._t("fresh");
    const statusClass = isOld ? "status status--old" : "status";

    this._card.innerHTML = `
      <div class="wrapper" style="--accent:${level.color}">
        <div class="hero">
          <div class="hero__left">
            <div class="hero__title">${this._title(aqiState)}</div>
            <div class="hero__badges">
              <span class="badge">${this._t("aqi")}</span>
              <span class="badge badge--level" title="${level.label}">${level.short}</span>
              <span class="${statusClass}">${statusText}</span>
            </div>
          </div>
          <div class="hero__right">
            <div class="aqi">${this._formatState(aqiState)}</div>
            <div class="updated">${this._t("updatedAt")}: ${this._formatUpdatedAt(updatedAt)}</div>
          </div>
        </div>

        <div class="level-line" title="${level.label}">
          <div class="level-line__swatch"></div>
          <div class="level-line__text">${level.label}</div>
          <div class="level-line__range">${this._t("range")}: ${level.range}</div>
        </div>

        <div class="metrics">
          ${this._metric(this._t("pm25"), this._formatState(pm25State, 1), this._icons.dots, true)}
          ${this._metric(this._t("pm10"), this._formatState(pm10State, 1), this._icons.cloud, true)}
          ${this._metric(this._t("temperature"), this._formatState(temperatureState, 1), this._icons.temp)}
          ${this._metric(this._t("humidity"), this._formatState(humidityState, 1), this._icons.humidity)}
        </div>
      </div>
      ${this._styles()}
    `;
  }

  _fire(type, detail, options = {}) {
    const event = new Event(type, {
      bubbles: options.bubbles ?? true,
      cancelable: options.cancelable ?? false,
      composed: options.composed ?? true,
    });
    event.detail = detail;
    this.dispatchEvent(event);
    return event;
  }

  _styles() {
    return `
      <style>
        .wrapper {
          --card-bg: var(--ha-card-background,var(--card-background-color,#fff));
          padding: 20px;
          background: var(--card-bg);
          border-top: 4px solid var(--accent, #38bdf8);
        }
        .wrapper.error {
          border-top-color: #ef4444;
        }
        .hero {
          display: flex;
          justify-content: space-between;
          gap: 16px;
          align-items: flex-start;
          margin-bottom: 16px;
        }
        .hero__title {
          font-size: 24px;
          font-weight: 700;
          line-height: 1.2;
          margin-bottom: 10px;
          color: var(--primary-text-color);
        }
        .hero__badges {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .badge, .status {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 6px 10px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 600;
          background: rgba(255,255,255,0.08);
          color: var(--primary-text-color);
        }
        .badge--level {
          background: color-mix(in srgb, var(--accent, #38bdf8) 20%, transparent);
          color: var(--primary-text-color);
          border: 1px solid color-mix(in srgb, var(--accent, #38bdf8) 55%, transparent);
        }
        .status {
          background: rgba(34,197,94,0.12);
          color: #86efac;
        }
        .status--old {
          background: rgba(239,68,68,0.14);
          color: #fca5a5;
        }
        .hero__right {
          text-align: right;
          min-width: 120px;
        }
        .aqi {
          font-size: 36px;
          font-weight: 800;
          line-height: 1;
          color: var(--accent, #38bdf8);
          margin-bottom: 8px;
        }
        .updated, .subtitle {
          color: var(--secondary-text-color);
          font-size: 13px;
        }
        .level-line {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 16px;
          padding: 10px 12px;
          border-radius: 14px;
          background: rgba(255,255,255,0.05);
          border: 1px solid rgba(255,255,255,0.06);
        }
        .level-line__swatch {
          width: 12px;
          height: 12px;
          border-radius: 50%;
          background: var(--accent, #38bdf8);
          flex: 0 0 12px;
        }
        .level-line__text {
          color: var(--primary-text-color);
          font-size: 14px;
          font-weight: 600;
          flex: 1;
        }
        .level-line__range {
          color: var(--secondary-text-color);
          font-size: 13px;
          white-space: nowrap;
        }
        .metrics {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }
        .metric {
          display: flex;
          gap: 12px;
          align-items: center;
          padding: 12px 14px;
          border-radius: 16px;
          background: rgba(255,255,255,0.05);
          border: 1px solid rgba(255,255,255,0.06);
        }
        .metric--accent {
          box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent, #38bdf8) 26%, transparent);
        }
        .metric__icon {
          width: 36px;
          height: 36px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 12px;
          background: rgba(255,255,255,0.08);
          color: var(--accent, #38bdf8);
        }
        .metric__label {
          color: var(--secondary-text-color);
          font-size: 12px;
          margin-bottom: 2px;
        }
        .metric__value {
          color: var(--primary-text-color);
          font-size: 16px;
          font-weight: 700;
          line-height: 1.2;
        }
        @media (max-width: 480px) {
          .hero {
            flex-direction: column;
          }
          .hero__right {
            text-align: left;
          }
          .metrics {
            grid-template-columns: 1fr;
          }
        }
      </style>
    `;
  }

  get _icons() {
    return {
      dots: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="7" cy="8" r="2.2"></circle><circle cx="17" cy="8" r="2.2"></circle><circle cx="12" cy="15.5" r="2.2"></circle></svg>`,
      cloud: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 18a4 4 0 1 1 .9-7.9A5.5 5.5 0 0 1 18.5 12H19a3 3 0 0 1 0 6H7Z"></path></svg>`,
      temp: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 14.76V5a2 2 0 1 0-4 0v9.76a4 4 0 1 0 4 0Z"></path></svg>`,
      humidity: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3s5 5.7 5 9.5A5 5 0 1 1 7 12.5C7 8.7 12 3 12 3Z"></path></svg>`,
    };
  }
}

if (!customElements.get(CARD_TAG)) {
  customElements.define(CARD_TAG, SaveEcoBotCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: CARD_TAG,
  name: "SaveEcoBot Card",
  description: "Beautiful AQI summary card for SaveEcoBot stations",
  preview: true,
});
