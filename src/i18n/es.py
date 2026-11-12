"""Centralized Spanish (es-LA / es) localization dictionary and helpers for SW-OptiPy."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ES_JSON_PATH = Path(__file__).resolve().parent / "es.json"


def _load_es_dictionary() -> dict[str, Any]:
    """Loads the Spanish translation dictionary from `src/i18n/es.json`."""
    return json.loads(ES_JSON_PATH.read_text(encoding="utf-8"))


ES_DICT: dict[str, Any] = _load_es_dictionary()

# Element mappings (English <-> Spanish)
ELEMENT_EN_TO_ES: dict[str, str] = {
    "Water": "Agua",
    "Fire": "Fuego",
    "Wind": "Viento",
    "Light": "Luz",
    "Dark": "Oscuridad",
    "Pure": "Puro",
    "Unknown": "Desconocido",
}

ELEMENT_ES_TO_EN: dict[str, str] = {v.lower(): k for k, v in ELEMENT_EN_TO_ES.items()}

ELEMENT_BADGE_MAP_ES: dict[str, str] = {
    "Water": "💧 Agua",
    "Fire": "🔥 Fuego",
    "Wind": "🌪️ Viento",
    "Light": "✨ Luz",
    "Dark": "🌑 Oscuridad",
    "Pure": "🌀 Puro",
    "Unknown": "❓ Desconocido",
    # Direct Spanish keys for convenience
    "Agua": "💧 Agua",
    "Fuego": "🔥 Fuego",
    "Viento": "🌪️ Viento",
    "Luz": "✨ Luz",
    "Oscuridad": "🌑 Oscuridad",
    "Puro": "🌀 Puro",
    "Desconocido": "❓ Desconocido",
}

# Standard competitive stat abbreviations and Spanish tooltips
STAT_ABBREVIATIONS_ES: dict[str, str] = ES_DICT["stats"]
STAT_TOOLTIPS_ES: dict[str, str] = ES_DICT["stats"]["tooltips"]

# Rune set dual labels (Competitive English set name + Spanish bonus hint)
RUNE_SET_LABELS_ES: dict[str, str] = ES_DICT["rune_sets"]

# Technical tooltips in Spanish
TOOLTIPS_ES: dict[str, str] = ES_DICT["tooltips"]

# HelpGuideModal 3-Step Spanish Markdown
HELP_STEP_1_SWEX_MD = """
### Paso 1: Exportación de Datos con SWEX (Summoners War Exporter)
Para importar tu propia cuenta de Summoners War en **SW-OptiPy**, extrae el archivo JSON de tu cuenta utilizando **Summoners War Exporter (SWEX)**:

1. **Descarga e Inicia SWEX:** Abre *Summoners War Exporter* en tu PC o Mac y activa el servidor proxy integrado.
2. **Conecta tu Dispositivo o Emulador:** Configura el proxy Wi-Fi de tu móvil o emulador (MuMu, BlueStacks, Nox, Google Play Games) apuntando a la IP y puerto que muestra SWEX (con el certificado HTTPS instalado).
3. **Inicia Sesión en Summoners War:** Al cargar el juego y recibir el paquete `HubUserLogin`, SWEX capturará y guardará automáticamente un archivo llamado `<WizardName>-<WizardID>.json`.
4. **Cargar JSON Aquí:** Arrastra y suelta ese archivo `.json` en el botón **Cargar JSON** — tus monstruos, runas y artefactos se procesan 100% localmente en tiempo $O(1)$ sin llamadas externas por unidad.
"""

HELP_STEP_2_STATS_MD = """
### Paso 2: Mapeo de Estadísticas, Runas Antiguas (Ancient) y Grinds
**SW-OptiPy** aplica de forma estricta las fórmulas matemáticas oficiales del dominio de Summoners War:

- **HP Base (`CON * 15`):** En el paquete crudo `HubUserLogin` de SWEX, la constitución del monstruo viene en el campo `con`. El parser calcula automáticamente $\\text{HP Base} = \\text{con} \\times 15$ en Nivel 40.
- **Bonos de Encantamientos y Grinds (`base + grind`):** Cada sub-estadística `sec_eff` (`[stat_id, base_val, gemmed, grind_val]`) se evalúa sumando su valor efectivo real ($\\text{base\\_val} + \\text{grind\\_val}$).
- **Runa Antigua (`6★ Ancient`):** Las runas con `class = 16` se identifican como **Runa Antigua (Ancient)** de 6★, preservando sus rolls iniciales superiores en el cálculo de la **Fórmula de Eficiencia de Barion**.
- **EHP (Vida Efectiva):** La resistencia real del monstruo se mide mediante $\\text{EHP} = \\frac{\\text{Total HP} \\times (1140 + \\text{Total DEF} \\times 3.5)}{1000}$.
"""

HELP_STEP_3_OPTIMIZER_MD = """
### Paso 3: Uso del Optimizador de Builds y Speed Tuning
1. **Seleccionar Monstruo:** Busca por nombre (`Buscar monstruo...`) o filtra por **Elemento** (`💧 Agua`, `🔥 Fuego`, `🌪️ Viento`, `✨ Luz`, `🌑 Oscuridad`) en la pestaña **Optimizador de Builds** o **Speed Tuning RTA / PVE**.
2. **Sets de Runas y Sets Rotos:** Elige los sets competitivos requeridos de 4 piezas (`Violent`, `Swift`, `Rage`, `Despair`, `Fatal`, `Vampire`, `Seal`) o de 2 piezas (`Will`, `Blade`, `Nemesis`, `Destroy`, `Fight`, `Energy`, `Shield`, `Revenge`). Activa **Permitir Sets Rotos (Broken)** (Broken Sets) para rellenar huecos libres con tus mejores runas sueltas; además, las runas **Intangible (`set_id = 25`)** actúan automáticamente como comodín de 1 pieza.
3. **Estadísticas Principales (Slots 2 / 4 / 6) y Filtros:** Restringe las estadísticas principales en los Slots 2, 4 y 6 (ej. `SPD / CDmg% / ATK%`) y define tus **Filtros de Estadísticas Mínimas** (`SPD`, `CR / Tasa Crít.`, `ACC`, `HP`, `ATK`).
4. **Calcular Builds y Bloquear:** Haz clic en **Calcular Builds** para evaluar miles de combinaciones mediante *Branch & Bound* con Numba JIT, revisa los **Resultados encontrados** y bloquea la build ganadora en modo PVE o RTA.
"""


def normalize_element_to_en(element: str) -> str:
    """Normalizes an English or Spanish element string to canonical English ('Water', 'Fire', etc.)."""
    clean = element.strip()
    # Strip emoji prefix if passed a badge
    for prefix in ("💧", "🔥", "🌪️", "✨", "🌑", "🌀", "❓"):
        clean = clean.replace(prefix, "").strip()
    lower = clean.lower()
    if lower in ELEMENT_ES_TO_EN:
        return ELEMENT_ES_TO_EN[lower]
    cap = clean.capitalize()
    if cap in ELEMENT_EN_TO_ES:
        return cap
    return "Unknown"


def translate_element_es(element: str) -> str:
    """Returns the Spanish element name ('Agua', 'Fuego', 'Viento', 'Luz', 'Oscuridad')."""
    en_key = normalize_element_to_en(element)
    return ELEMENT_EN_TO_ES.get(en_key, element)


def get_element_badge_es(element: str) -> str:
    """Returns the Spanish element badge with icon (e.g. '💧 Agua', '🌪️ Viento')."""
    if element in ELEMENT_BADGE_MAP_ES:
        return ELEMENT_BADGE_MAP_ES[element]
    en_key = normalize_element_to_en(element)
    return ELEMENT_BADGE_MAP_ES.get(en_key, f"❓ {element}")
