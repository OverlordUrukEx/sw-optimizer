"""Spanish (es-LA / es) localization loader and helpers for SW-OptiPy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

I18N_DIR = Path(__file__).resolve().parent
ES_JSON_PATH = I18N_DIR / "es.json"


def load_spanish_locale() -> dict[str, Any]:
    """Loads the centralized Spanish localization dictionary from `src/i18n/es.json`."""
    return json.loads(ES_JSON_PATH.read_text(encoding="utf-8"))


ES_LOCALE: dict[str, Any] = load_spanish_locale()
ES_DICT: dict[str, Any] = ES_LOCALE
ELEMENT_NAMES_ES: dict[str, str] = ES_LOCALE["elements"]
ELEMENT_BADGES_ES: dict[str, str] = ES_LOCALE["element_badges"]
TOOLTIPS_ES: dict[str, str] = ES_LOCALE["tooltips"]

STAT_TOOLTIPS_ES: dict[str, str] = {
    "HP": TOOLTIPS_ES["hp"],
    "ATK": TOOLTIPS_ES["atk"],
    "DEF": TOOLTIPS_ES["def"],
    "SPD": TOOLTIPS_ES["spd"],
    "CR": TOOLTIPS_ES["cr"],
    "CD": TOOLTIPS_ES["cd"],
    "RES": TOOLTIPS_ES["res"],
    "ACC": TOOLTIPS_ES["acc"],
    "EHP": TOOLTIPS_ES["effective_hp"],
}


def translate_element(element: str) -> str:
    """Translates an internal English element identifier ('Water') to Spanish ('Agua')."""
    return ELEMENT_NAMES_ES.get(element, element)


def get_element_badge_es(element: str) -> str:
    """Returns the Spanish element badge with icon (e.g., '💧 Agua', '🔥 Fuego')."""
    if element in ELEMENT_BADGES_ES:
        return ELEMENT_BADGES_ES[element]
    for eng_key, esp_name in ELEMENT_NAMES_ES.items():
        if element.lower() == esp_name.lower():
            return ELEMENT_BADGES_ES[eng_key]
    return f"❓ {element}"
