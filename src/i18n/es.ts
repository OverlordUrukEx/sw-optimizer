/**
 * Centralized Spanish (es-LA / es) Localization Dictionary for sw-optimizer.
 * Preserves competitive Summoners War terminology (Rune Sets & Stat Abbreviations).
 */
export const ES_TRANSLATIONS = {
  locale: "es-LA",
  navbar: {
    uploadJson: "Cargar JSON",
    tryDemoAccount: "Probar Cuenta Demo",
    switchOrClearAccount: "Cambiar Cuenta / Limpiar",
    helpGuide: "Guía de Uso",
    level: "Nivel",
    mana: "Maná",
    crystals: "Cristales",
  },
  tables: {
    monsters: "Monstruos",
    runes: "Runas",
    artifacts: "Artefactos",
    searchMonsterPlaceholder: "Buscar monstruo...",
    element: "Elemento",
    elements: {
      Water: "Agua",
      Fire: "Fuego",
      Wind: "Viento",
      Light: "Luz",
      Dark: "Oscuridad",
    },
    stars: "Estrellas",
    equippedOn: "Equipada en",
    inventoryFree: "Inventario (Libre)",
    ancientRune: "Runa Antigua (Ancient)",
  },
  optimizer: {
    title: "Optimizador de Builds",
    selectMonster: "Seleccionar Monstruo",
    runeSets: "Sets de Runas",
    mainStatsSlots246: "Estadísticas Principales (Slots 2 / 4 / 6)",
    minStatFilters: "Filtros de Estadísticas Mínimas",
    includeEquippedRunes: "Incluir runas equipadas",
    allowBrokenSets: "Permitir Sets Rotos (Broken)",
    calculateBuilds: "Calcular Builds",
    resultsFound: "Resultados encontrados",
  },
  stats: {
    HP: { label: "HP", tooltip: "Vida" },
    ATK: { label: "ATK", tooltip: "Ataque" },
    DEF: { label: "DEF", tooltip: "Defensa" },
    SPD: { label: "SPD", tooltip: "Velocidad" },
    CR: { label: "CR / Tasa Crít.", tooltip: "Tasa Crítica" },
    CD: { label: "CD / Daño Crít.", tooltip: "Daño Crítico" },
    RES: { label: "RES", tooltip: "Resistencia" },
    ACC: { label: "ACC", tooltip: "Precisión" },
    EHP: { label: "EHP", tooltip: "Vida Efectiva" },
  },
} as const;
