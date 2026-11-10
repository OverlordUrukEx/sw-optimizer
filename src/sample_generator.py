"""Generador de un archivo sample_swex.json realista para pruebas y demostración."""

from __future__ import annotations

import json
from pathlib import Path
import random
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models import MAIN_STAT_MAX_6STAR


def _make_rune(
    rune_id: int,
    slot_no: int,
    set_id: int,
    main_stat_id: int,
    upgrade_curr: int = 15,
    is_ancient: bool = False,
    innate: tuple[int, int] = (0, 0),
    subs: list[list[int]] | None = None,
    occupied_id: int = 0,
) -> dict[str, Any]:
    max_val = MAIN_STAT_MAX_6STAR[main_stat_id]
    main_val = max_val if upgrade_curr == 15 else int(round(max_val * 0.72))
    return {
        "rune_id": rune_id,
        "occupied_id": occupied_id,
        "slot_no": slot_no,
        "upgrade_curr": upgrade_curr,
        "class": 16 if is_ancient else 6,
        "set_id": set_id,
        "upgrade_limit": 15,
        "pri_eff": [main_stat_id, main_val],
        "prefix_eff": [innate[0], innate[1]],
        "sec_eff": subs or [],
    }


def generate_sample_swex_dict(seed: int = 42) -> dict[str, Any]:
    """Genera un diccionario con estructura idéntica a una exportación real de SWEX."""
    rng = random.Random(seed)

    monsters_spec = [
        # (unit_id, unit_master_id, con, atk, def, spd, cr, cd, res, acc)
        (1001, 13413, 615, 900, 461, 103, 15, 50, 15, 0),   # Lushen (base_hp = 9225)
        (1002, 14712, 659, 812, 505, 99, 15, 50, 15, 0),    # Verdehile (base_hp = 9885)
        (1003, 19314, 626, 681, 516, 102, 15, 50, 15, 0),   # Loren (base_hp = 9390)
        (1004, 19114, 681, 670, 461, 103, 15, 50, 15, 0),   # Fran (base_hp = 10215)
        (1005, 11035, 659, 834, 637, 108, 15, 50, 15, 0),   # Kro 2A (base_hp = 9885)
        (1006, 11532, 725, 670, 692, 126, 15, 50, 15, 0),   # Spectra 2A (base_hp = 10875)
        (1007, 11533, 758, 538, 758, 111, 15, 50, 15, 0),   # Bernard 2A (base_hp = 11370)
        (1008, 19411, 779, 714, 593, 108, 15, 50, 15, 0),   # Galleon (base_hp = 11685)
        (1009, 18913, 790, 725, 637, 96, 15, 50, 15, 0),    # Tiana (base_hp = 11850)
        (1010, 15713, 725, 801, 615, 100, 15, 50, 15, 25),  # Seara (base_hp = 10875)
        (1011, 25313, 736, 790, 648, 101, 15, 50, 15, 0),   # Oliver (base_hp = 11040)
        (1012, 24511, 714, 834, 615, 102, 15, 50, 15, 0),   # Moore (base_hp = 10710)
    ]

    unit_list: list[dict[str, Any]] = []
    rune_id_counter = 50001
    artifact_id_counter = 90001
    rta_rune_equip_list: list[dict[str, int]] = []
    rta_artifact_equip_list: list[dict[str, int]] = []

    # Asignar builds PVE iniciales a los primeros 6 monstruos
    preset_sets_per_unit = {
        1001: [5, 5, 5, 5, 4, 25],   # Lushen: 4 Rage + 1 Blade + 1 Intangible (completa Blade!)
        1002: [13, 13, 13, 13, 17, 17],  # Verdehile: Violent + Revenge
        1003: [3, 3, 3, 3, 6, 6],    # Loren: Swift + Focus
        1004: [13, 13, 13, 13, 15, 15],  # Fran: Violent + Will
        1005: [5, 5, 5, 5, 4, 4],    # Kro 2A: Rage + Blade
        1007: [3, 3, 3, 3, 15, 15],  # Bernard 2A: Swift + Will
    }

    slot_main_templates = {
        1001: {1: 3, 2: 4, 3: 5, 4: 10, 5: 1, 6: 4},  # Lushen ATK/CD/ATK
        1002: {1: 3, 2: 4, 3: 5, 4: 9, 5: 1, 6: 2},   # Verde ATK/CR/HP
        1003: {1: 3, 2: 8, 3: 5, 4: 2, 5: 1, 6: 12},  # Loren SPD/HP/ACC
        1004: {1: 3, 2: 8, 3: 5, 4: 2, 5: 1, 6: 2},   # Fran SPD/HP/HP
        1005: {1: 3, 2: 4, 3: 5, 4: 10, 5: 1, 6: 4},  # Kro ATK/CD/ATK
        1007: {1: 3, 2: 8, 3: 5, 4: 2, 5: 1, 6: 6},   # Bernard SPD/HP/DEF
    }

    for uid, master_id, con, atk, def_, spd, cr, cd, res, acc in monsters_spec:
        unit_runes: list[dict[str, Any]] = []
        unit_artifacts: list[dict[str, Any]] = []

        if uid in preset_sets_per_unit:
            sets = preset_sets_per_unit[uid]
            mains = slot_main_templates[uid]
            for slot in range(1, 7):
                spd_roll = 24 if uid == 1007 else rng.randint(10, 20)
                cr_roll = 18 if uid in (1001, 1002, 1005) else rng.randint(6, 12)
                subs = [
                    [8, spd_roll, 0, 4],       # SPD + grind
                    [9, cr_roll, 0, 0],        # CRate%
                    [2, rng.randint(12, 22), 0, 7],  # HP% + grind
                    [4, rng.randint(12, 24), 1, 8],  # ATK% gemmed + grind
                ]
                # Filtrar sub duplicada con main_stat
                main_id = mains[slot]
                subs = [s for s in subs if s[0] != main_id]
                if len(subs) < 4:
                    subs.append([10, 15, 0, 0] if main_id != 10 else [6, 14, 0, 6])

                rune_dict = _make_rune(
                    rune_id=rune_id_counter,
                    slot_no=slot,
                    set_id=sets[slot - 1],
                    main_stat_id=main_id,
                    upgrade_curr=15 if slot != 5 else 12,  # Slot 5 a +12 para probar simulación +15
                    is_ancient=(slot == 6 and uid == 1001),
                    innate=(12, 7) if slot % 2 == 0 else (0, 0),
                    subs=subs,
                    occupied_id=uid,
                )
                unit_runes.append(rune_dict)
                rune_id_counter += 1

            # 2 Artefactos por monstruo equipado
            art1 = {
                "rid": artifact_id_counter,
                "occupied_id": uid,
                "slot": 1,
                "type": 1,
                "pri_eff": [100, 1500],  # +1500 HP
                "sec_eff": [[204, 12.0], [205, 8.0]],
            }
            artifact_id_counter += 1
            art2 = {
                "rid": artifact_id_counter,
                "occupied_id": uid,
                "slot": 2,
                "type": 2,
                "pri_eff": [101, 100],   # +100 ATK
                "sec_eff": [[220, 14.0], [222, 6.0]],
            }
            artifact_id_counter += 1
            unit_artifacts.extend([art1, art2])

        unit_list.append(
            {
                "unit_id": uid,
                "unit_master_id": master_id,
                "unit_level": 40,
                "class": 6,
                "con": con,
                "atk": atk,
                "def": def_,
                "spd": spd,
                "critical_rate": cr,
                "critical_damage": cd,
                "resist": res,
                "accuracy": acc,
                "runes": unit_runes,
                "artifacts": unit_artifacts,
            }
        )

    # Generar pool de 108 runas en inventario desequipado (18 por cada slot 1..6)
    inventory_runes: list[dict[str, Any]] = []
    candidate_sets = [3, 13, 5, 8, 10, 15, 4, 1, 2, 6, 17, 19, 25]
    slot2_mains = [8, 2, 4, 6]
    slot4_mains = [10, 9, 2, 4, 6]
    slot6_mains = [2, 4, 6, 12, 11]

    for slot in range(1, 7):
        for idx in range(18):
            set_id = candidate_sets[idx % len(candidate_sets)]
            if slot == 1:
                main_id = 3
            elif slot == 2:
                main_id = slot2_mains[idx % len(slot2_mains)]
            elif slot == 3:
                main_id = 5
            elif slot == 4:
                main_id = slot4_mains[idx % len(slot4_mains)]
            elif slot == 5:
                main_id = 1
            else:
                main_id = slot6_mains[idx % len(slot6_mains)]

            sub_pool = [
                [8, rng.randint(8, 24), 0, rng.randint(3, 5)],
                [9, rng.randint(6, 18), 0, 0],
                [10, rng.randint(7, 20), 0, 0],
                [2, rng.randint(10, 25), 0, rng.randint(5, 9)],
                [4, rng.randint(10, 25), 0, rng.randint(5, 9)],
                [6, rng.randint(10, 22), 0, rng.randint(5, 8)],
                [12, rng.randint(8, 20), 0, 0],
                [11, rng.randint(8, 18), 0, 0],
            ]
            valid_subs = [s for s in sub_pool if s[0] != main_id]
            chosen_subs = rng.sample(valid_subs, 4)

            rune_dict = _make_rune(
                rune_id=rune_id_counter,
                slot_no=slot,
                set_id=set_id,
                main_stat_id=main_id,
                upgrade_curr=15 if idx % 4 != 0 else 12,
                is_ancient=(idx % 7 == 0 and set_id != 25),
                innate=(11, 6) if idx % 3 == 0 and main_id != 11 else (0, 0),
                subs=chosen_subs,
                occupied_id=0,
            )
            inventory_runes.append(rune_dict)
            rune_id_counter += 1

    # Asignar builds RTA separadas para Oliver (1011), Moore (1012), Tiana (1009) y Seara (1010)
    # usando runas tanto del inventario como runas que en PVE están en otros monstruos
    rta_units = [1011, 1012, 1009, 1010]
    by_slot: dict[int, list[int]] = {s: [] for s in range(1, 7)}
    for r in inventory_runes:
        by_slot[r["slot_no"]].append(r["rune_id"])

    for u_idx, rta_uid in enumerate(rta_units):
        for slot in range(1, 7):
            chosen_rid = by_slot[slot][u_idx]
            rta_rune_equip_list.append({"rune_id": chosen_rid, "occupied_id": rta_uid})

    return {
        "wizard_info": {
            "wizard_id": 884422,
            "wizard_name": "KratosSW",
            "wizard_mana": 45000000,
            "wizard_crystal": 3250,
        },
        "unit_list": unit_list,
        "runes": inventory_runes,
        "artifacts": [],
        "world_arena_rune_equip_list": rta_rune_equip_list,
        "world_arena_artifact_equip_list": rta_artifact_equip_list,
    }


def ensure_sample_swex_file(output_path: str | Path = "sample_swex.json") -> Path:
    """Crea sample_swex.json si aún no existe y devuelve la ruta."""
    path = Path(output_path)
    if not path.exists():
        payload = generate_sample_swex_dict()
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    out = ensure_sample_swex_file("sample_swex.json")
    print(f"Archivo de prueba generado en: {out.resolve()}")

