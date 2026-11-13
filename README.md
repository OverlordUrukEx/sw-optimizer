# ⚡ SW-Optimizer — Optimizador de Runas y Builds para Summoners War

**SW-Optimizer** es un optimizador combinatorio de runas, artefactos y *Speed Tuning* de alto rendimiento diseñado específicamente para la comunidad hispanohablante de *Summoners War: Sky Arena*. Combina un motor matemático **Branch & Bound** acelerado con **Numba JIT (`nogil=True`)**, una arquitectura limpia (*Clean Layered Architecture*) basada en principios **SOLID** y persistencia asíncrona *Local-First* mediante **IndexedDB**.

La plataforma traduce toda la interfaz, métricas, tablas y guías al español competitivo, preservando intactos los nombres oficiales de los monstruos (*Lushen*, *Verdehile*, *Kro*, *Spectra*) y la nomenclatura internacional de sets de runas (*Violent*, *Swift*, *Will*, *Despair*, *Rage*, *Intangible*).

---

## 🚀 Características Principales

- **Resolución Instantánea del Bestiario ($O(1)$):** Nombres, elementos (`💧 Agua`, `🔥 Fuego`, `🌪️ Viento`, `✨ Luz`, `🌑 Oscuridad`) e íconos oficiales sincronizados con la API v2 de **SWARFARM** mediante el diccionario estático [`src/data/monster_map.json`](file:///home/johan/VM_Personal/sw_optimizer/src/data/monster_map.json) (`3,141` especies mapeadas por `com2us_id`), con soporte completo para *Second Awakening (2A)* y *Homúnculos* sin realizar llamadas individuales ($N+1$) durante la importación.
- **Precisión Matemática Com2uS:**
  - Cálculo exacto de **HP Base** a partir del atributo interno de constitución ($\text{HP Base} = \text{CON} \times 15$).
  - Soporte nativo para **Runas Antiguas (Ancient Runes 6★)** (`class >= 10` o `rank >= 10`), suma automática de *Grindstones* (`valor_base + grind_val`) e indicador de *Enchanted Gems*.
  - Lógica completa de comodín para el set **Intangible (`set_id = 25`)**, capaz de reemplazar automáticamente `1` pieza faltante de cualquier set incompleto de 4 o 2 piezas (máximo 1 activa por build).
  - Separación estricta de inventarios y bloqueos entre **Modo Normal (PVE / Siege / Arena)** y **Modo RTA (World Arena)**.
- **Arquitectura Local-First (`IndexedDB`):** Persistencia asíncrona en el navegador (`SWOptimizerDB`) sin el cuello de botella ni el límite síncrono de 5 MB de `localStorage`. Tu inventario normalizado y tus builds bloqueadas se mantienen automáticamente al recargar la página (`F5`) sin enviarse a ningún servidor externo.
- **Motor de Optimización Multihilo (*Web Workers*):** Cálculo de permutaciones en segundo plano ([`src/workers/optimizer_worker.py`](file:///home/johan/VM_Personal/sw_optimizer/src/workers/optimizer_worker.py) y [`src/workers/optimizer.worker.js`](file:///home/johan/VM_Personal/sw_optimizer/src/workers/optimizer.worker.js)) con poda temprana (*Branch and Bound*) sobre los slots `(2, 4, 6)` y reporte de progreso en tiempo real para mantener la interfaz fluida a 60 FPS.
- **Modo Demo y Guía Integrada:** Prueba inmediata en un clic con una cuenta de demostración 100% anonimizada ([`src/data/demo_account.json`](file:///home/johan/VM_Personal/sw_optimizer/src/data/demo_account.json) — `Demo_Summoner`) y modal interactivo paso a paso (**"📖 Guía de Uso"**) integrado en la barra de navegación superior.

---

## 🏗️ Arquitectura del Proyecto (Clean Architecture & SOLID)

El código fuente sigue una arquitectura en capas con separación estricta de responsabilidades (**SRP**, **OCP**, **DIP** y **DRY**):

```text
sw-optimizer/
├── scripts/
│   ├── sync_monsters.py                 # Sincronizador CLI del bestiario SWARFARM v2 -> monster_map.json
│   └── generate_demo_account.py         # Generador y sanitizador sin PII de demo_account.json (< 150 KB)
├── src/
│   ├── domain/                          # Capa de Dominio Pura (Single Source of Truth)
│   │   ├── __init__.py                  # Exportaciones del dominio
│   │   ├── rune_set_mechanics.py        # Reglas declarativas de sets (4-set, 2-set, Broken e Intangible 25)
│   │   └── stat_calculator.py           # Fórmulas matemáticas (Eficiencia Barion, EHP, Daño, SPD Combate)
│   ├── services/
│   │   └── storage/
│   │       └── account_storage_service.py # Persistencia asíncrona IndexedDB (SWOptimizerDB) + Snapshot F5
│   ├── workers/
│   │   ├── optimizer_worker.py          # Worker multihilo (nogil=True) con progreso en vivo
│   │   └── optimizer.worker.js          # Web Worker cliente para poda Branch & Bound en navegador
│   ├── i18n/
│   │   ├── __init__.py                  # Cargador de localización y badges de elemento
│   │   └── es.json                      # Diccionario centralizado en español competitivo (es-LA / es)
│   ├── data/
│   │   ├── monster_map.json             # Diccionario O(1) de 3,141 monstruos de SWARFARM
│   │   └── demo_account.json            # Cuenta demo sanitizada (Demo_Summoner, 8 unidades, 30 runas libres)
│   ├── models.py                        # Modelos Pydantic (Monster, Rune, Artifact, AccountProfile)
│   ├── monster_data_service.py          # Servicio O(1) de resolución de metadatos e íconos de monstruos
│   ├── parser.py                        # Ingesta y normalización de archivos JSON de SWEX
│   ├── calculator.py                    # Fachada de compatibilidad y simulador de ticks PVE (0.07) / RTA (0.015)
│   ├── optimizer.py                     # Núcleo combinatorio Numba JIT (@njit(cache=True, nogil=True))
│   ├── ui_components.py                 # Hero de bienvenida, cargador Demo y modal Guía de Uso
│   └── app.py                           # Interfaz web principal en Streamlit
├── tests/                               # Suite de pruebas unitarias y de integración (pytest)
├── pyproject.toml                       # Configuración del paquete y dependencias
└── README.md                            # Documentación técnica y guía de usuario
```

---

## 📖 Guía Rápida de Uso (Para Jugadores)

### 1. Cómo exportar tu archivo `TuInvocador-12345678.json` desde SWEX
1. Descarga e inicia **Summoners War Exporter (SWEX)** en tu PC.
2. Activa el proxy integrado de SWEX y conecta tu dispositivo móvil o emulador a la misma red local configurando el proxy Wi-Fi (con el certificado HTTPS de SWEX instalado).
3. Inicia sesión en *Summoners War: Sky Arena*. Al cargar tu isla, SWEX interceptará el paquete `HubUserLogin` y guardará automáticamente el archivo **`TuInvocador-12345678.json`** en tu carpeta de exportaciones.

### 2. Cargar tu cuenta o usar el Modo Demo
- **Subir tu JSON:** Arrastra y suelta tu archivo **`TuInvocador-12345678.json`** en la zona **"📤 Cargar JSON de tu Cuenta (SWEX)"** de la pantalla principal o desde la barra lateral.
- **Probar sin archivo propio:** Haz clic en el botón **"🎮 Probar Cuenta Demo"** para cargar al instante la cuenta de prueba `Demo_Summoner` con monstruos 6★, unidades *Second Awakening (2A)*, Homúnculo y decenas de runas listas para optimizar.
- **Persistencia automática:** Tu cuenta permanecerá activa aunque recargues la página con `F5`. Cuando desees cambiar de archivo, pulsa **"🔄 Cambiar Cuenta / Limpiar"** en la barra superior.

---

## 🛠️ Instalación y Comandos (Para Desarrolladores)

### 1. Clonar el repositorio
```bash
git clone https://github.com/OverlordUrukEx/sw-optimizer.git
cd sw-optimizer
```

### 2. Instalar dependencias
Con **uv** (entorno Python nativo):
```bash
uv sync
```
*(O en entornos con scripts envolventes de Node: `npm install`)*

### 3. Sincronizar el diccionario del bestiario (`monster_map.json`) desde SWARFARM
```bash
uv run python scripts/sync_monsters.py
# Equivalente script: npm run sync-monsters
```

### 4. Iniciar el servidor de desarrollo y verificar compilación / pruebas
```bash
# Iniciar la aplicación web interactiva
uv run streamlit run src/app.py
# Equivalente script: npm run dev

# Ejecutar verificación de compilación y suite completa de pruebas
uv run pytest -v
# Equivalente script: npm run build
```

---

## 🔒 Privacidad y Seguridad

- **Procesamiento 100% Local (*Local-First*):** Todo el análisis del archivo `TuInvocador-12345678.json`, el cálculo de estadísticas y la persistencia en `IndexedDB` ocurren localmente en tu sesión. Tus runas, monstruos e identificadores de cuenta jamás se transmiten a servidores de terceros.
- **Protección Estricta en Git (`.gitignore`):** El archivo [`.gitignore`](file:///home/johan/VM_Personal/sw_optimizer/.gitignore) está configurado para bloquear cualquier exportación personal de SWEX en la raíz (`/*.json`) o dentro del directorio privado `local_data/`, así como cachés temporales (`.cache/`). Únicamente se versionan en el repositorio los catálogos públicos y anonimizados [`src/data/monster_map.json`](file:///home/johan/VM_Personal/sw_optimizer/src/data/monster_map.json) y [`src/data/demo_account.json`](file:///home/johan/VM_Personal/sw_optimizer/src/data/demo_account.json).
