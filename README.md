# ⚡ SW-OptiPy — Optimizador de Runas y Speed Tuning para Summoners War

**SW-OptiPy** es una aplicación web local en Python diseñada para importar el archivo `.json` generado por **SWEX (Summoners War Exporter)**, analizar la eficiencia del inventario de runas, optimizar builds individuales mediante **Branch & Bound vectorizado con NumPy y Numba JIT**, y realizar **Speed Tuning** exacto por ticks tanto para contenido **PVE / Siege / Arena (`tick = 0.07`)** como para **RTA / World Arena (`tick = 0.015`)**.

---

## 🏗️ Arquitectura del Proyecto

```text
sw_optimizer/
├── SPEC.md                  # Especificación técnica y reglas de dominio oficiales
├── pyproject.toml           # Configuración de dependencias (uv) y pytest
├── sample_swex.json         # Archivo de exportación SWEX de prueba realista (autigenerado)
├── src/
│   ├── models.py            # Modelos Pydantic (Rune, Artifact, Monster, AccountProfile) y tablas 6★
│   ├── parser.py            # Lector JSON de SWEX y sincronizador de Bestiario con SWARFARM + caché SQLite
│   ├── calculator.py        # Fórmulas exactas: Eficiencia de Barion, +15, Set Intangible (25), EHP y Ticks
│   ├── optimizer.py         # Motor combinatorio Branch & Bound acelerado con NumPy y Numba (@njit)
│   ├── sample_generator.py  # Generador determinista de perfiles SWEX de demostración
│   └── app.py               # Interfaz gráfica interactiva en Streamlit (4 pestañas)
└── tests/
    ├── test_models_and_parser.py
    ├── test_calculator.py
    ├── test_optimizer.py
    └── test_app_smoke.py
```

---

## 📐 Reglas de Dominio y Fórmulas Matemáticas Implementadas

1. **Regla de HP Base de Monstruos (`unit_list`)**:
   $$\text{Base\_HP} = \text{con} \times 15$$
2. **Separación de Inventarios (PVE/PVP vs RTA)**:
   - **Modo Normal (PVE / Siege / Arena)**: Unión de `json["runes"]` (inventario) y `unit["runes"]` de cada monstruo en `unit_list`.
   - **Modo RTA (World Arena)**: Mapeo independiente mediante `json["world_arena_rune_equip_list"]` (`rune_id -> occupied_id`), permitiendo bloquear runas y builds en PVE y RTA sin mezclar sus bloqueos.
3. **Eficiencia de Runa (Fórmula de Barion)**:
   $$\text{Eficiencia (\%)} = \left(\frac{1.0 + \sum \frac{\text{val\_efectivo}}{\text{max\_roll\_6star}}}{2.8}\right) \times 100$$
4. **Estadísticas Finales y Effective HP (EHP)**:
   - $\text{Total\_HP} = \text{Base\_HP} + \text{round}\left(\text{Base\_HP} \times \frac{\sum \text{HP\%}}{100}\right) + \sum \text{HP\_Flat}$ (ídem para `ATK` y `DEF`).
   - $\text{Combat\_SPD} = \text{Base\_SPD} + \text{Rune\_SPD} + \lceil \text{Base\_SPD} \times (\text{Sky\_Totem}_{0.15} + \text{Leader\_SPD} + \text{Swift}_{0.25}) \rceil$.
   - $\text{EHP} = \frac{\text{Total\_HP} \times (1140 + \text{Total\_DEF} \times 3.5)}{1000}$.
5. **Runa Comodín Intangible (`set_id = 25`)**:
   - Puede sustituir **1 pieza faltante** de cualquier set de 2 o 4 piezas (máximo 1 activa por monstruo), priorizando sets requeridos o sets de 4 piezas incompletos (`3/4`).
6. **Speed Tuning por Ticks**:
   - **PVE / Siege / Arena**: incremento de barra de ataque de `0.07 * Combat_SPD` por tick.
   - **RTA (World Arena)**: incremento de barra de ataque de `0.015 * Combat_SPD` por tick.

---

## 🚀 Instalación y Ejecución

### 1. Ejecutar las pruebas unitarias
```bash
uv run pytest -v
```

### 2. Iniciar la aplicación web en Streamlit
```bash
uv run streamlit run src/app.py
```

### 3. Regenerar el archivo de prueba `sample_swex.json` (opcional)
```bash
uv run python src/sample_generator.py
```
