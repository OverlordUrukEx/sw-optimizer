# Especificación Técnica: Optimizador de Runas y Equipos para Summoners War (SW-OptiPy)

## 1. Objetivo del Proyecto
Desarrollar una aplicación web local en Python (interfaz amigable en Streamlit o FastAPI + UI moderna) que importe el archivo `.json` generado por SWEX (Summoners War Exporter) y permita analizar runas, optimizar builds individuales y realizar Speed Tuning de equipos completos para PVE (Cairos/Raid), PVP (Siege/WGB/Arena) y RTA (World Arena).

## 2. Reglas de Dominio y Parseo del JSON (SWEX)
- **Monstruos (`unit_list`)**:
  - `unit_id`: ID único de la instancia del monstruo en la cuenta.
  - `unit_master_id`: ID de especie de Com2uS. Debe sincronizarse y cachearse localmente en un archivo SQLite/JSON consultando la API de SWARFARM (`https://swarfarm.com/api/v2/monsters/` buscando por `com2us_id`) para obtener nombre, elemento, despertar, skills e iconos.
  - **Regla crítica de HP Base**: En el JSON, el campo `con` debe multiplicarse por 15 (`base_hp = con * 15`). `atk`, `def`, `spd`, `critical_rate`, `critical_damage`, `resist`, `accuracy` se leen directamente.
- **Separación de Inventarios (PVE/PVP vs RTA)**:
  - **Modo Normal (PVE/Siege/Arena)**: Las runas disponibles son la unión de `json["runes"]` (inventario) + las listas `unit["runes"]` dentro de cada elemento de `json["unit_list"]`.
  - **Modo RTA**: Las runas equipadas en RTA se mapean mediante `json["world_arena_rune_equip_list"]` (`rune_id` -> `occupied_id`). El optimizador debe permitir alternar entre el inventario PVE y el inventario RTA sin mezclar sus bloqueos.
- **Estructura de Runa**:
  - `rune_id`, `slot_no` (1-6), `set_id`, `class` (6 = 6★, 16 = 6★ Ancient), `upgrade_curr` (0-15).
  - `pri_eff`: `[stat_id, val]` (permite simular subida a +15 si `upgrade_curr < 15` usando las tablas oficiales de main stat 6★).
  - `prefix_eff`: `[stat_id, val]` (innata).
  - `sec_eff`: lista de `[stat_id, base_val, gemmed, grind_val]`. Valor efectivo = `base_val + grind_val`.
- **Mapeo de `stat_id`**:
  - 1: HP flat, 2: HP%, 3: ATK flat, 4: ATK%, 5: DEF flat, 6: DEF%, 8: SPD, 9: CRate%, 10: CDmg%, 11: RES%, 12: ACC%.
- **Mapeo de `set_id` y tamaños de set**:
  - Sets de 2 piezas: 1: Energy (+15% HP), 2: Guard (+15% DEF), 4: Blade (+12% CR), 6: Focus (+20% ACC), 7: Endure (+20% RES), 14: Nemesis, 15: Will, 16: Shield, 17: Revenge, 18: Destroy, 19: Fight (+8% ATK aliado), 20: Determination (+8% DEF aliado), 21: Enhance (+8% HP aliado), 22: Accuracy (+10% ACC aliado), 23: Tolerance (+10% RES aliado).
  - Sets de 4 piezas: 3: Swift (+25% SPD), 5: Rage (+40% CDmg), 8: Fatal (+35% ATK), 10: Despair, 11: Vampire, 13: Violent, 24: Seal.
  - Set de 1 pieza comodín: 25: Intangible (puede sustituir 1 pieza faltante de cualquier set de 2 o 4 piezas, máximo 1 activa).

## 3. Fórmulas Matemáticas Exactas
1. **Eficiencia de Runa (Barion Formula)**:
   `Eficiencia = ((1.0 + sum(val_efectivo / max_roll_6star)) / 2.8) * 100`
   Max rolls (5 rolls 6★): HP%/ATK%/DEF%/ACC%/RES% = 40 | SPD/CRate = 30 | CDmg = 35 | HP flat = 1875 | ATK/DEF flat = 100.
2. **Estadísticas Finales de Monstruo**:
   - `Total_HP = Base_HP + round(Base_HP * (Sum_HP% / 100)) + Sum_HP_Flat` (ídem para ATK y DEF).
   - `Combat_SPD = Base_SPD + Rune_SPD + ceil(Base_SPD * (Sky_Totem_0.15 + Leader_Skill_SPD + Swift_Bonus_0.25))`
   - `Effective_HP (EHP) = Total_HP * (1140 + (Total_DEF * 3.5)) / 1000`
3. **Motor de Optimización Combinatoria (`optimizer.py`)**:
   - Implementar poda por pesos (*Focus Stats*) por slot antes de permutar.
   - Evaluar primero combinaciones de slots (2, 4, 6) para validar compatibilidad de `set_id` (incluyendo lógica de runa Intangible `25`) y poda temprana (*Branch & Bound*) contra restricciones mínimas (`min_spd`, `min_cr`, `min_acc`, `min_hp`).
   - Acelerar el bucle de evaluación con `NumPy` / `Numba` para evaluar cientos de miles de builds por segundo.
   - Permitir "Bloquear Runas/Builds" para optimizar equipos de hasta 5-10 monstruos en orden de turno (*Speed Tuning*), retirando del pool las runas asignadas al monstruo anterior.

## 4. Arquitectura Modular Requerida
- `src/models.py`: Modelos Pydantic/Dataclasses para Runa, Artefacto, Monstruo y Perfil.
- `src/parser.py`: Lector del JSON de SWEX y sincronizador de Bestiario con SWARFARM.
- `src/calculator.py`: Cálculo de eficiencia, simulación de runas a +15, EHP y Speed Tuning (ticks PVE 0.07 y RTA 0.015).
- `src/optimizer.py`: Motor Branch & Bound vectorizado con Numba/NumPy.
- `src/app.py`: Interfaz gráfica web en Streamlit (con pestañas: Dashboard de Runas, Optimizador General/PVE, Builder RTA con Speed Tuning y Gestor de Builds Bloqueadas).
- `tests/`: Pruebas unitarias en `pytest` para validar fórmulas de eficiencia, set Intangible y Speed Tuning.
