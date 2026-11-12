# ⚡ SW-Optimizer (`SW-OptiPy`) — Optimizador de Builds, Runas y Speed Tuning para Summoners War

**SW-Optimizer** (`SW-OptiPy`) es una herramienta web de alto rendimiento totalmente en español (`es-LA` / `es`) diseñada para la comunidad competitiva de **Summoners War: Sky Arena**. Permite analizar inventarios completos de runas y artefactos, calcular la **Eficiencia de Barion**, optimizar builds mediante **Branch & Bound acelerado con NumPy y Numba JIT**, y simular **Speed Tuning** exacto por ticks tanto para contenido **PVE / Siege / Arena (`tick = 0.07`)** como para **RTA / World Arena (`tick = 0.015`)**.

---

## ✨ Características Principales (Features)

- **Resolución Instantánea del Bestiario en Tiempo $O(1)$ (API v2 de SWARFARM):**
  - Identificación automática de nombres oficiales, elementos (`💧 Agua`, `🔥 Fuego`, `🌪️ Viento`, `✨ Luz`, `🌑 Oscuridad`), estrellas base e íconos de avatar mediante un mapa estático precompilado (`src/data/monster_map.json`) sincronizado con la API v2 de **SWARFARM**.
  - Soporte completo para monstruos con **Second Awakening (2A)** (ej. *Icaru*, *Spectra*, *Kro*, *Raoq*, *Belladeon*) y resolución de nombres personalizados de **Homúnculos** (`homunculus_name`).
  - Cero llamadas HTTP $N+1$ al importar tu cuenta y respaldo automático offline para unidades nuevas no mapeadas (`Unknown Monster (#ID) - [Element]`).

- **Parser Estricto del Paquete `HubUserLogin` (SWEX):**
  - **Cálculo Exacto de HP Base:** Conversión automática del atributo de constitución crudo de Com2uS mediante la fórmula oficial $\text{HP Base} = \text{CON} \times 15$.
  - **Soporte Completo para Runas Antiguas (Ancient Runes 6★):** Detección nativa de runas con `class = 16` (**Runa Antigua / Ancient**), respetando sus valores iniciales superiores en las tablas de eficiencia.
  - **Suma Automática de Encantamientos y Grinds (`base + grind`):** Cada sub-estadística (`sec_eff`) evalúa su valor efectivo real sumando el valor base más la piedra de afilar ($\text{valor\_efectivo} = \text{base\_val} + \text{grind\_val}$).
  - **Separación Independiente PVE vs RTA:** Mapeo aislado entre el equipamiento normal (`unit_list["runes"]` + `runes`) y el equipamiento de World Arena (`world_arena_rune_equip_list`), con bloqueo de builds independiente por modo.

- **Modo Demo Interactivo (`Probar Cuenta Demo`):**
  - Prueba inmediata con un solo clic utilizando una cuenta real sanitizada (`src/data/demo_account.json` — `Demo_Summoner`), equipada con monstruos 6★, unidades 2A, Homúnculo y 78 runas listas para optimizar sin necesidad de subir archivos propios.

- **Guía de Usuario Integrada (`HelpGuideModal`):**
  - Modal interactivo de 3 pasos dentro de la aplicación (**Guía de Uso**) que explica la exportación con SWEX, las fórmulas matemáticas de estadísticas/grinds/runas antiguas y el uso del optimizador, acompañado de un glosario competitivo con tooltips en español (`HP`, `ATK`, `DEF`, `SPD`, `CR / Tasa Crít.`, `CD / Daño Crít.`, `RES`, `ACC`, `EHP`).

- **Optimización de Memoria y Rendimiento:**
  - El parser y el generador de cuentas descartan todos los nodos innecesarios del JSON de exportación (`quest_active`, `scenario_list`, `friend_list`, `helper_list`, `building_list`, etc.), procesando únicamente `wizard_info`, `unit_list`, `runes`, `artifacts` y mapas de equipamiento RTA en memoria local.
  - Motor combinatorio **Branch & Bound** con poda temprana en los Slots 2 / 4 / 6 y soporte para runa comodín **Intangible (`set_id = 25`)** y **Sets Rotos (Broken Sets)**.

---

## 📥 Cómo Obtener tu Archivo JSON (Guía Rápida de SWEX)

Para cargar tu propia cuenta en **SW-Optimizer**, necesitas exportar tu perfil usando **Summoners War Exporter (SWEX)**:

1. **Descarga e Inicia SWEX:** Descarga la última versión de [Summoners War Exporter](https://github.com/Xzandro/sw-exporter) para Windows, macOS o Linux y haz clic en **Start Proxy**.
2. **Configura el Certificado HTTPS y el Proxy:** Instala el certificado CA de SWEX en tu dispositivo móvil o emulador de Android (MuMu Player, BlueStacks, Nox) y configura el proxy Wi-Fi apuntando a la dirección IP local y puerto indicados por SWEX.
3. **Inicia Sesión en Summoners War:** Abre el juego. Cuando el cliente reciba el paquete `HubUserLogin`, SWEX generará automáticamente un archivo llamado `<TuNombre>-<TuWizardID>.json` en su carpeta de salida.
4. **Sube el Archivo a SW-Optimizer:** Haz clic en **Cargar JSON** o arrastra el archivo `.json` directamente a la zona de carga de la aplicación.

---

## 🛠️ Instalación y Despliegue Local (Para Desarrolladores)

### Requisitos Previos
- **Git**
- **Python 3.14+** y gestor de paquetes **[uv](https://docs.astral.sh/uv/)** (o entorno Node.js / npm si integras el diccionario `src/i18n/es.ts` en un frontend híbrido).

### 1. Clonar el Repositorio
```bash
git clone https://github.com/OverlordUrukEx/sw-optimizer.git
cd sw-optimizer
```

### 2. Instalar Dependencias
Con **uv** (entorno principal en Python / Streamlit):
```bash
uv sync
```
*(Si trabajas en un entorno JavaScript/TypeScript híbrido: `npm install`).*

### 3. Sincronizar el Bestiario Local (`sync_monsters`)
El repositorio ya incluye `src/data/monster_map.json` precompilado con más de 2,100 monstruos. Para actualizar el catálogo desde la API v2 de **SWARFARM**:
```bash
uv run python scripts/sync_monsters.py --force
```

### 4. Iniciar la Aplicación en Modo Desarrollo y Compilación
Para levantar la interfaz web interactiva en **Streamlit**:
```bash
uv run streamlit run src/app.py
```
*(En entornos Node/Frontend equivalentes: `npm run dev` para servidor de desarrollo y `npm run build` para compilación de producción).*

### 5. Ejecutar la Suite de Pruebas Automatizadas (Linter & Tests)
```bash
uv run pytest -v
```

---

## 🔒 Privacidad y Seguridad

- **Procesamiento 100% Local:** Todo el análisis de tu archivo `.json` de SWEX, la resolución de monstruos en tiempo $O(1)$ y el cálculo combinatorio de builds se ejecutan localmente en tu sesión/navegador. Tus datos nunca se envían a servidores de terceros.
- **Protección de Exportaciones Personales (`.gitignore`):** Los archivos de exportación reales de cuentas personales (como `<WizardName>-<WizardID>.json`) están estrictamente excluidos del control de versiones mediante `.gitignore`. Únicamente se versionan en el repositorio el mapa público del bestiario (`src/data/monster_map.json`) y la cuenta de demostración anonimizada (`src/data/demo_account.json`).

---

## 📂 Estructura del Proyecto

```text
sw_optimizer/
├── README.md                        # Documentación principal en español
├── SPEC.md                          # Especificación matemática y reglas de dominio
├── pyproject.toml                   # Configuración del proyecto, dependencias y pytest
├── scripts/
│   ├── sync_monsters.py             # Script CLI de sincronización masiva con SWARFARM v2 API
│   └── generate_demo_account.py     # Sanitizador y generador de src/data/demo_account.json
├── src/
│   ├── i18n/
│   │   ├── es.json                  # Diccionario centralizado de traducción al español (es-LA / es)
│   │   ├── es.py                    # Módulo Python de internacionalización, glosario y ayuda
│   │   └── es.ts                    # Definiciones TypeScript equivalentes para el diccionario es-LA
│   ├── data/
│   │   ├── monster_map.json         # Mapa estático O(1) de monstruos (SWARFARM)
│   │   └── demo_account.json        # Cuenta demo sanitizada (< 150 KB, Demo_Summoner)
│   ├── models.py                    # Modelos Pydantic (Monster, Rune, Artifact, AccountProfile)
│   ├── monster_data_service.py      # Servicio O(1) de resolución de monstruos, íconos y elementos
│   ├── parser.py                    # Parser estricto del paquete HubUserLogin (SWEX)
│   ├── calculator.py                # Fórmulas de Eficiencia de Barion, +15, Intangible, EHP y Ticks
│   ├── optimizer.py                 # Motor Branch & Bound vectorizado con NumPy y Numba (@njit)
│   ├── ui_components.py             # Navbar, Estado Vacío (Onboarding), Modo Demo y HelpGuideModal
│   └── app.py                       # Interfaz web principal en Streamlit (localizada al español)
└── tests/                           # Suite de pruebas unitarias y de integración (pytest)
```
