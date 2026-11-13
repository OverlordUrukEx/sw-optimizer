# ⚡ SW-Optimizer (SW-OptiPy) — Optimizador de Runas, Artefactos y Speed Tuning para Summoners War

**SW-Optimizer (`SW-OptiPy`)** es una aplicación web de alto rendimiento en español diseñada para la comunidad competitiva de **Summoners War: Sky Arena**. Permite importar el archivo `.json` de tu cuenta generado por **Summoners War Exporter (SWEX)**, analizar la eficiencia real de tu inventario de runas y artefactos, calcular builds óptimas en milisegundos mediante **Branch & Bound compilado con Numba JIT**, y ajustar el **Speed Tuning** exacto por ticks para contenido **PVE / Siege / Arena (`tick = 0.07`)** y **RTA / World Arena (`tick = 0.015`)**.

---

## ✨ Características Principales

- **Resolución Instantánea de Bestiario en Tiempo $O(1)$ (SWARFARM API v2):**
  - Mapeo local pre-sincronizado ([`src/data/monster_map.json`](file:///home/johan/VM_Personal/sw_optimizer/src/data/monster_map.json)) con más de **3,140 monstruos**, resolviendo nombres oficiales, elementos (`Agua`, `Fuego`, `Viento`, `Luz`, `Oscuridad`), estrellas base e íconos de avatar sin realizar llamadas HTTP $N+1$ al importar tu cuenta.
  - Soporte completo para unidades **Second Awakening (2A)** (como *Icaru*, *Spectra*, *Kro*, *Raoq*, *Belladeon*, *Bernard*) y preservación automática de nombres personalizados de **Homúnculos**.
- **Parser Estricto del Paquete `HubUserLogin` (SWEX):**
  - **Cálculo exacto de HP Base:** Conversión automática de la estadística de constitución cruda ($\text{HP Base} = \text{CON} \times 15$).
  - **Soporte para Runas Antiguas (Ancient Runes 6★):** Detección nativa de `class = 16` y evaluación mediante la **Fórmula de Eficiencia de Barion**.
  - **Suma Automática de Grinds y Gemas (`base + grind`):** Cálculo del valor efectivo real en cada sub-estadística de runa y soporte de estadísticas principales de artefactos (`pri_effect` / `pri_eff`).
  - **Separación de Inventarios PVE vs RTA:** Manejo independiente de equipamiento y bloqueos de runas entre el modo Normal y World Arena (`world_arena_rune_equip_list` y `world_arena_rune_equip_sync`).
- **Motor Combinatorio Branch & Bound (`NumPy` + `Numba JIT`):**
  - Poda temprana en las ranuras principales (**Slots 2, 4 y 6**) validando compatibilidad de sets, comodín **Intangible (`set_id = 25`)**, **Sets Rotos (Broken)** y filtros de estadísticas mínimas (`SPD`, `CR / Tasa Crít.`, `CD / Daño Crít.`, `HP`, `ATK`, `ACC`, `RES`, `EHP`).
- **Modo Demo Interactivo (`Demo_Summoner`):**
  - Incluye un perfil real sanitizado ([`src/data/demo_account.json`](file:///home/johan/VM_Personal/sw_optimizer/src/data/demo_account.json), `< 80 KB`) con 8 monstruos representativos (6★, 2A y Homúnculo) y 78 runas para probar todas las funciones del optimizador con un solo clic, sin necesidad de subir archivos propios.
- **Guía de Usuario Integrada (`HelpGuideModal`) y Localización Competitiva (`es-LA` / `es`):**
  - Interfaz 100% en español adaptada a la terminología competitiva de Summoners War (`Violent`, `Swift`, `Will`, `Despair`, `Rage`, `Intangible`, `SPD`, `CR`, `CD`, `EHP`), con guía interactiva paso a paso y tooltips explicativos en cada métrica técnica.
- **Optimización de Memoria:**
  - Descarta automáticamente nodos y arreglos innecesarios del archivo de exportación de SWEX (`scenario_list`, `quest_active`, `quest_rewarded`, etc.), manteniendo en memoria únicamente las estructuras de monstruos, runas y artefactos.

---

## 📲 Cómo Obtener tu Archivo JSON (Guía Rápida de SWEX)

1. **Descarga Summoners War Exporter (SWEX):** Descarga la última versión desde el repositorio oficial de [SW-Exporter en GitHub](https://github.com/Xzandro/sw-exporter/releases).
2. **Inicia el Proxy:** Abre SWEX en tu PC o Mac, habilita la opción de certificado HTTPS y pulsa **Start Proxy**.
3. **Conecta tu Dispositivo o Emulador:** Configura el proxy Wi-Fi de tu teléfono o emulador (MuMu Player, BlueStacks, LDPlayer) con la dirección IP y el puerto indicados en la pantalla de SWEX.
4. **Abre Summoners War:** Inicia sesión en el juego. Cuando se cargue el paquete `HubUserLogin`, SWEX generará automáticamente el archivo `<TuNombre>-<TuID>.json` en su carpeta de salida.
5. **Cárgalo en SW-Optimizer:** Arrastra y suelta ese archivo `.json` en la zona **Cargar JSON** de la aplicación web.

---

## 🛠️ Instalación y Despliegue Local (Para Desarrolladores)

### Requisitos Previos
- **Python** `>= 3.14`
- **[uv](https://docs.astral.sh/uv/)** (gestor de paquetes y entornos virtuales ultrarrápido)
- **Git**

### 1. Clonar el repositorio e instalar dependencias
```bash
git clone https://github.com/OverlordUrukEx/sw-optimizer.git
cd sw-optimizer
uv sync
```

### 2. Sincronizar el catálogo del Bestiario desde SWARFARM (Opcional)
El repositorio ya incluye [`src/data/monster_map.json`](file:///home/johan/VM_Personal/sw_optimizer/src/data/monster_map.json) y [`src/data/demo_account.json`](file:///home/johan/VM_Personal/sw_optimizer/src/data/demo_account.json). Para actualizar el catálogo de monstruos contra la API v2 de SWARFARM o regenerar la cuenta demo:
```bash
# Actualizar src/data/monster_map.json desde https://swarfarm.com/api/v2/monsters/
uv run python scripts/sync_monsters.py

# Regenerar src/data/demo_account.json
uv run python scripts/generate_demo_account.py
```

### 3. Iniciar el servidor de desarrollo (Interfaz Web)
```bash
uv run streamlit run src/app.py
```

### 4. Ejecutar la suite de pruebas automatizadas (`pytest`)
```bash
uv run pytest -v
```

---

## 🔒 Privacidad y Seguridad

- **Procesamiento 100% Local:** Tu archivo `.json` de SWEX se analiza exclusivamente en la memoria local de tu sesión; tus runas, monstruos e identificadores de cuenta nunca se envían a servidores externos.
- **Protección en Git (`.gitignore`):** Las exportaciones personales de cuentas de SWEX (`/*.json` / `Invocador-12345678.json`) y cachés locales están excluidas en [`.gitignore`](file:///home/johan/VM_Personal/sw_optimizer/.gitignore) para evitar subir datos sensibles de cuentas reales al repositorio público, manteniendo únicamente el archivo anonimizado [`src/data/demo_account.json`](file:///home/johan/VM_Personal/sw_optimizer/src/data/demo_account.json).
