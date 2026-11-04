"""Interfaz gráfica web en Streamlit para SW-OptiPy (Optimizador de Runas y Equipos)."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Literal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl
import streamlit as st

from src.calculator import (
    PVE_TICK_SIZE,
    RTA_TICK_SIZE,
    SpeedTuneMember,
    calculate_monster_stats,
    calculate_rune_efficiency,
    simulate_speed_tuning,
)
from src.models import (
    AccountProfile,
    NAME_TO_SET_ID,
    SET_ID_MAP,
    STAT_ID_MAP,
)
from src.optimizer import (
    OptimizationConstraints,
    OptimizedBuild,
    TeamOptimizationRequestMember,
    optimize_monster_builds,
    optimize_team_speed_tuning,
)
from src.parser import BestiaryCache, parse_swex_json
from src.sample_generator import ensure_sample_swex_file


def _init_session_state() -> None:
    if "profile" not in st.session_state:
        sample_path = ensure_sample_swex_file("sample_swex.json")
        cache = BestiaryCache()
        st.session_state.profile = parse_swex_json(sample_path, bestiary=cache)
    if "inventory_mode" not in st.session_state:
        st.session_state.inventory_mode = "pve"
    if "last_opt_result" not in st.session_state:
        st.session_state.last_opt_result = None
    if "last_team_opt_results" not in st.session_state:
        st.session_state.last_team_opt_results = None
    if "locked_builds_pve" not in st.session_state:
        st.session_state.locked_builds_pve = {}
    if "locked_builds_rta" not in st.session_state:
        st.session_state.locked_builds_rta = {}


def _build_runes_dataframe(profile: AccountProfile) -> pl.DataFrame:
    rows: list[dict[str, Any]] = []
    for r in profile.runes.values():
        pve_owner = (
            profile.monsters[r.occupied_id].name
            if r.occupied_id in profile.monsters
            else "Inventario"
        )
        rta_owner = (
            profile.monsters[r.rta_occupied_id].name
            if r.rta_occupied_id in profile.monsters
            else "Inventario RTA"
        )
        rows.append(
            {
                "Rune ID": r.rune_id,
                "Slot": r.slot_no,
                "Set": r.set_name,
                "Grado": f"{r.stars}★ {'Ancient' if r.is_ancient else 'Normal'}",
                "Nivel": f"+{r.upgrade_curr}",
                "Main Stat": f"{STAT_ID_MAP.get(r.main_stat_id, '')} +{r.main_stat_val}",
                "Innate": (
                    f"{STAT_ID_MAP.get(r.innate_stat_id, '')} +{r.innate_stat_val}"
                    if r.innate_stat_id > 0
                    else "-"
                ),
                "SPD": r.get_stat_total(8),
                "CRate%": r.get_stat_total(9),
                "CDmg%": r.get_stat_total(10),
                "HP%": r.get_stat_total(2),
                "ATK%": r.get_stat_total(4),
                "DEF%": r.get_stat_total(6),
                "ACC%": r.get_stat_total(12),
                "RES%": r.get_stat_total(11),
                "Eficiencia (%)": calculate_rune_efficiency(r, use_grinds=True),
                "Efic. Base (%)": calculate_rune_efficiency(r, use_grinds=False),
                "Equipada PVE": pve_owner,
                "Equipada RTA": rta_owner,
                "Bloqueada PVE": r.rune_id in profile.locked_runes_pve,
                "Bloqueada RTA": r.rune_id in profile.locked_runes_rta,
            }
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort("Eficiencia (%)", descending=True)


def render_sidebar() -> tuple[AccountProfile, Literal["pve", "rta"], float, float]:
    st.sidebar.title("⚡ SW-OptiPy")
    st.sidebar.caption("Optimizador de Runas y Speed Tuning (PVE / Siege / RTA)")

    uploaded = st.sidebar.file_uploader(
        "Importar JSON de SWEX",
        type=["json"],
        help="Sube el archivo .json exportado por Summoners War Exporter (SWEX).",
    )
    sync_remote = st.sidebar.checkbox(
        "Sincronizar nuevos IDs con SWARFARM API", value=False
    )

    if uploaded is not None:
        raw_bytes = uploaded.getvalue()
        file_sig = f"{uploaded.name}:{len(raw_bytes)}"
        if st.session_state.get("loaded_file_sig") != file_sig:
            cache = BestiaryCache()
            st.session_state.profile = parse_swex_json(
                raw_bytes, bestiary=cache, fetch_remote_bestiary=sync_remote
            )
            st.session_state.loaded_file_sig = file_sig
            st.sidebar.success(f"Perfil cargado: {st.session_state.profile.wizard_name}")

    profile: AccountProfile = st.session_state.profile

    mode_label = st.sidebar.radio(
        "Modo de Inventario Activo",
        options=["Modo Normal (PVE / Siege / Arena)", "Modo RTA (World Arena)"],
        index=0 if st.session_state.inventory_mode == "pve" else 1,
    )
    mode: Literal["pve", "rta"] = "rta" if "RTA" in mode_label else "pve"
    st.session_state.inventory_mode = mode

    st.sidebar.divider()
    st.sidebar.subheader("Bonos Globales de Combate")
    sky_totem_pct = st.sidebar.slider("Sky Totem SPD (%)", 0, 15, 15)
    leader_spd_pct = st.sidebar.selectbox(
        "Líder de Velocidad (%)",
        options=[0, 10, 15, 19, 21, 24, 28, 30, 33],
        index=0,
    )

    st.sidebar.divider()
    st.sidebar.markdown(
        f"**Invocador:** `{profile.wizard_name}`  \n"
        f"**Monstruos:** `{len(profile.monsters)}`  \n"
        f"**Runas Totales:** `{len(profile.runes)}`  \n"
        f"**Bloqueadas PVE:** `{len(profile.locked_runes_pve)}`  \n"
        f"**Bloqueadas RTA:** `{len(profile.locked_runes_rta)}`"
    )

    return profile, mode, sky_totem_pct / 100.0, leader_spd_pct / 100.0


def render_tab_dashboard(profile: AccountProfile) -> None:
    st.subheader("📊 Dashboard y Analizador de Runas (Fórmula de Barion)")
    df = _build_runes_dataframe(profile)
    if df.is_empty():
        st.warning("No se encontraron runas en el perfil actual.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total de Runas", len(df))
    c2.metric("Eficiencia Media", f"{df['Eficiencia (%)'].mean():.2f}%")
    c3.metric("Runas >= 100% Efic.", int((df["Eficiencia (%)"] >= 100.0).sum()))
    c4.metric("Runas >= 25 SPD", int((df["SPD"] >= 25).sum()))

    f1, f2, f3 = st.columns(3)
    all_sets = sorted(df["Set"].unique().to_list())
    selected_sets = f1.multiselect("Filtrar por Set", options=all_sets, default=[])
    selected_slots = f2.multiselect("Filtrar por Slot", options=[1, 2, 3, 4, 5, 6], default=[])
    min_eff = f3.slider("Eficiencia Mínima (%)", 0.0, 130.0, 0.0, step=1.0)

    filtered = df.filter(pl.col("Eficiencia (%)") >= min_eff)
    if selected_sets:
        filtered = filtered.filter(pl.col("Set").is_in(selected_sets))
    if selected_slots:
        filtered = filtered.filter(pl.col("Slot").is_in(selected_slots))

    st.dataframe(filtered, use_container_width=True, hide_index=True)


def render_tab_optimizer(
    profile: AccountProfile,
    mode: Literal["pve", "rta"],
    sky_totem: float,
    leader_spd: float,
) -> None:
    st.subheader(
        f"🧮 Optimizador Combinatorio Branch & Bound ({'RTA' if mode == 'rta' else 'PVE / Normal'})"
    )
    monsters_list = sorted(profile.monsters.values(), key=lambda m: m.name)
    monster_map = {f"{m.name} (#{m.unit_id} - {m.element})": m for m in monsters_list}

    col_left, col_right = st.columns([1, 2])
    with col_left:
        selected_label = st.selectbox("Monstruo a Optimizar", options=list(monster_map.keys()))
        monster = monster_map[selected_label]

        st.caption(
            f"**Base Stats (Lv.40):** HP `{monster.base_hp}` (`con={monster.con}*15`) | "
            f"ATK `{monster.atk}` | DEF `{monster.def_}` | SPD `{monster.spd}`"
        )

        set_names = [name for sid, name in sorted(SET_ID_MAP.items()) if sid != 25]
        req_set_names = st.multiselect(
            "Sets Requeridos (Intangible se usa automáticamente como comodín)",
            options=set_names,
            default=["Rage", "Blade"] if monster.name == "Lushen" else ["Swift"],
        )
        req_set_ids = [NAME_TO_SET_ID[n.lower()] for n in req_set_names]

        stat_options = {f"{v} ({k})": k for k, v in STAT_ID_MAP.items()}
        s2_names = st.multiselect(
            "Main Stat Slot 2",
            options=list(stat_options.keys()),
            default=["SPD (8)", "ATK% (4)"],
        )
        s4_names = st.multiselect(
            "Main Stat Slot 4",
            options=list(stat_options.keys()),
            default=["CDmg% (10)", "CRate% (9)", "HP% (2)"],
        )
        s6_names = st.multiselect(
            "Main Stat Slot 6",
            options=list(stat_options.keys()),
            default=["ATK% (4)", "HP% (2)", "ACC% (12)"],
        )

        st.markdown("**Restricciones Mínimas (Branch & Bound)**")
        r1, r2 = st.columns(2)
        min_spd = r1.number_input("Min Combat SPD", min_value=0, max_value=400, value=160)
        max_spd = r2.number_input("Max Combat SPD", min_value=1, max_value=999, value=450)
        min_cr = r1.number_input("Min CRate (%)", min_value=0, max_value=100, value=15)
        min_acc = r2.number_input("Min ACC (%)", min_value=0, max_value=100, value=0)
        min_hp = r1.number_input("Min Total HP", min_value=0, max_value=100000, value=10000, step=500)
        min_atk = r2.number_input("Min Total ATK", min_value=0, max_value=10000, value=500, step=100)

        opt_for = st.selectbox(
            "Objetivo a Maximizar",
            options=["damage", "spd", "ehp", "efficiency", "atk", "hp", "def"],
            index=0,
        )
        sim_15 = st.checkbox("Simular runas a +15 (Tablas 6★)", value=True)
        max_per_slot = st.slider("Profundidad por Slot (Focus Pruning)", 8, 35, 18)

        run_btn = st.button("🚀 Ejecutar Optimización (Numba JIT)", type="primary", use_container_width=True)

    with col_right:
        if run_btn:
            cfg = OptimizationConstraints(
                required_sets=req_set_ids,
                slot2_main_stats=[stat_options[x] for x in s2_names],
                slot4_main_stats=[stat_options[x] for x in s4_names],
                slot6_main_stats=[stat_options[x] for x in s6_names],
                min_spd=int(min_spd),
                max_spd=int(max_spd),
                min_cr=int(min_cr),
                min_acc=int(min_acc),
                min_hp=int(min_hp),
                min_atk=int(min_atk),
                simulate_plus15=sim_15,
                sky_totem=sky_totem,
                leader_skill_spd=leader_spd,
                optimize_for=opt_for,  # type: ignore[arg-type]
                max_runes_per_slot=max_per_slot,
                top_k=10,
            )
            pool = profile.get_available_runes(mode=mode)
            res = optimize_monster_builds(monster=monster, available_runes=pool, constraints=cfg)
            st.session_state.last_opt_result = res

        opt_res = st.session_state.last_opt_result
        if opt_res is not None:
            st.info(
                f"Monstruo: **{opt_res.monster_name}** | Builds evaluadas: `{opt_res.evaluated_builds:,}` | "
                f"Ramas (2,4,6) podadas: `{opt_res.pruned_triplets_246:,}/{opt_res.total_triplets_246:,}` | "
                f"Tiempo: `{opt_res.elapsed_ms:.2f} ms`"
            )
            if not opt_res.builds:
                st.warning("Ninguna combinación cumplió todas las restricciones. Reduce los mínimos o amplía el Focus Pruning.")
            else:
                build_rows = []
                for b in opt_res.builds:
                    s = b.stats
                    build_rows.append(
                        {
                            "Rank": b.rank,
                            "Score": b.score,
                            "Sets": ", ".join(s.active_sets),
                            "Intangible ->": s.intangible_replaced_set or "-",
                            "Combat SPD": s.combat_spd,
                            "Rune SPD": f"+{s.rune_spd}",
                            "HP": s.total_hp,
                            "ATK": s.total_atk,
                            "DEF": s.total_def,
                            "CR%": s.crate,
                            "CD%": s.cdmg,
                            "ACC%": s.acc,
                            "RES%": s.res,
                            "EHP": s.ehp,
                            "Efic. Media (%)": s.avg_efficiency,
                            "Runas (Slots 1-6)": str(b.rune_ids),
                        }
                    )
                st.dataframe(pl.DataFrame(build_rows), use_container_width=True, hide_index=True)

                chosen_rank = st.selectbox(
                    "Seleccionar Rank para Bloquear Runas",
                    options=[b.rank for b in opt_res.builds],
                    index=0,
                )
                if st.button(f"🔒 Bloquear Build #{chosen_rank} en modo {mode.upper()}"):
                    chosen_build: OptimizedBuild = opt_res.builds[chosen_rank - 1]
                    target_set = (
                        profile.locked_runes_rta if mode == "rta" else profile.locked_runes_pve
                    )
                    target_dict = (
                        st.session_state.locked_builds_rta
                        if mode == "rta"
                        else st.session_state.locked_builds_pve
                    )
                    for rid in chosen_build.rune_ids:
                        target_set.add(rid)
                    target_dict[opt_res.unit_id] = chosen_build
                    st.success(
                        f"Se bloquearon las 6 runas {chosen_build.rune_ids} para {opt_res.monster_name} en modo {mode.upper()}."
                    )


def render_tab_speed_tuning(
    profile: AccountProfile,
    mode: Literal["pve", "rta"],
    sky_totem: float,
    leader_spd: float,
) -> None:
    tick_val = RTA_TICK_SIZE if mode == "rta" else PVE_TICK_SIZE
    st.subheader(
        f"⏱️ Builder de Equipos y Speed Tuning (Modo {mode.upper()} - Tick = {tick_val})"
    )
    st.markdown(
        "Configura el orden exacto de turno de tu equipo (hasta 5 monstruos). "
        "Puedes simular los ticks actuales o ejecutar la **Optimización Secuencial con Bloqueo de Runas**."
    )

    monsters_list = sorted(profile.monsters.values(), key=lambda m: m.name)
    name_to_mon = {m.name: m for m in monsters_list}
    mon_names = list(name_to_mon.keys())

    default_team = ["Bernard (11013)", "Galleon", "Lushen"]
    default_picks = [n for n in ["Griffon (Bernard) 2A", "Galleon", "Lushen", "Loren"] if n in name_to_mon]

    selected_team_names = st.multiselect(
        "Selecciona los Monstruos del Equipo (en el orden de turno deseado 1 -> N)",
        options=mon_names,
        default=default_picks[:3] if len(default_picks) >= 3 else mon_names[:3],
        max_selections=6,
    )

    if not selected_team_names:
        st.info("Selecciona al menos 2 monstruos para analizar y optimizar su Speed Tuning.")
        return

    sim_members: list[SpeedTuneMember] = []
    team_opt_reqs: list[TeamOptimizationRequestMember] = []

    cols = st.columns(len(selected_team_names))
    for idx, m_name in enumerate(selected_team_names):
        mon = name_to_mon[m_name]
        equipped = profile.get_equipped_runes(mon.unit_id, mode=mode)
        curr_stats = calculate_monster_stats(
            mon, equipped, sky_totem=sky_totem, leader_skill_spd=leader_spd
        )
        with cols[idx]:
            st.markdown(f"**#{idx + 1}: {mon.name}**")
            st.caption(f"Base SPD: `{mon.spd}`")
            r_spd = st.number_input(
                f"Rune SPD (#{idx + 1})",
                min_value=0,
                max_value=260,
                value=curr_stats.rune_spd if curr_stats.rune_spd > 0 else 120 - idx * 15,
                key=f"st_rspd_{idx}",
            )
            swift_on = st.checkbox(
                "Set Swift Activo",
                value=("Swift" in curr_stats.active_sets or idx == 0),
                key=f"st_swift_{idx}",
            )
            atb_boost = st.number_input(
                "Boost ATB Aliado (%)",
                min_value=0.0,
                max_value=100.0,
                value=30.0 if idx == 0 else 0.0,
                step=5.0,
                key=f"st_boost_{idx}",
            )
            spd_buff = st.checkbox(
                "Aplica Buff SPD (+30%)",
                value=(idx == 0 and "Bernard" in mon.name),
                key=f"st_spdbuff_{idx}",
            )
            role_goal = st.selectbox(
                "Objetivo Optimizador",
                options=["spd", "damage", "ehp", "efficiency"],
                index=0 if idx < len(selected_team_names) - 1 else 1,
                key=f"st_goal_{idx}",
            )

            sim_members.append(
                SpeedTuneMember(
                    unit_id=mon.unit_id,
                    name=mon.name,
                    base_spd=mon.spd,
                    rune_spd=int(r_spd),
                    swift_active=swift_on,
                    atb_boost_pct=float(atb_boost),
                    spd_buff_turns=2 if spd_buff else 0,
                )
            )
            team_opt_reqs.append(
                TeamOptimizationRequestMember(
                    monster=mon,
                    constraints=OptimizationConstraints(
                        required_sets=[3] if swift_on else [],
                        optimize_for=role_goal,  # type: ignore[arg-type]
                        sky_totem=sky_totem,
                        leader_skill_spd=leader_spd,
                        max_runes_per_slot=15,
                        top_k=3,
                    ),
                    atb_boost_pct=float(atb_boost),
                    spd_buff_turns=2 if spd_buff else 0,
                )
            )

    report = simulate_speed_tuning(
        sim_members, mode=mode, sky_totem=sky_totem, leader_skill_spd=leader_spd
    )

    if report.is_perfectly_tuned:
        st.success(
            f"✅ Speed Tuning Válido ({mode.upper()} tick={report.tick_size}): "
            f"Orden de turno real: {' ➔ '.join(report.turn_sequence)}"
        )
    else:
        st.error(
            f"⚠️ Desajuste en Speed Tuning ({mode.upper()} tick={report.tick_size}): "
            f"Orden real: {' ➔ '.join(report.turn_sequence)}"
        )

    tune_rows = [
        {
            "Orden Esperado": m.expected_turn_order,
            "Monstruo": m.name,
            "Combat SPD Actual": m.combat_spd,
            "Tick 1er Turno": m.first_turn_tick,
            "Orden Real": m.actual_turn_order,
            "Min Combat SPD Req.": m.min_combat_spd_required,
            "Min Rune SPD Req.": f"+{m.min_rune_spd_required}",
            "Estado": "✅ OK" if m.is_tuned else "❌ Cortado / Desordenado",
        }
        for m in report.members
    ]
    st.dataframe(pl.DataFrame(tune_rows), use_container_width=True, hide_index=True)

    if st.button(
        f"⚡ Optimizar y Bloquear Equipo Completo en Orden de Turno ({mode.upper()})",
        type="primary",
    ):
        team_results = optimize_team_speed_tuning(
            profile=profile,
            team_requests=team_opt_reqs,
            mode=mode,
            lock_winning_builds=True,
        )
        st.session_state.last_team_opt_results = team_results
        target_dict = (
            st.session_state.locked_builds_rta
            if mode == "rta"
            else st.session_state.locked_builds_pve
        )
        for res in team_results:
            if res.builds:
                target_dict[res.unit_id] = res.builds[0]

    if st.session_state.last_team_opt_results:
        st.markdown("#### Resultados de la Optimización Secuencial del Equipo")
        summary_rows = []
        for idx, res in enumerate(st.session_state.last_team_opt_results):
            if res.builds:
                b = res.builds[0]
                s = b.stats
                summary_rows.append(
                    {
                        "Turno #": idx + 1,
                        "Monstruo": res.monster_name,
                        "Sets Activos": ", ".join(s.active_sets),
                        "Combat SPD": s.combat_spd,
                        "Rune SPD": f"+{s.rune_spd}",
                        "Total HP": s.total_hp,
                        "Total ATK": s.total_atk,
                        "CRate%": s.crate,
                        "CDmg%": s.cdmg,
                        "ACC%": s.acc,
                        "Runas Asignadas": str(b.rune_ids),
                    }
                )
        if summary_rows:
            st.dataframe(pl.DataFrame(summary_rows), use_container_width=True, hide_index=True)


def render_tab_locked_builds(profile: AccountProfile) -> None:
    st.subheader("🔒 Gestor de Runas y Builds Bloqueadas (PVE vs RTA independientes)")

    col_pve, col_rta = st.columns(2)
    with col_pve:
        st.markdown(f"### Modo Normal (PVE / Siege) — `{len(profile.locked_runes_pve)}` runas bloqueadas")
        if st.button("🔓 Desbloquear todas las runas PVE"):
            profile.locked_runes_pve.clear()
            st.session_state.locked_builds_pve.clear()
            st.rerun()

        if st.session_state.locked_builds_pve:
            for uid, b in list(st.session_state.locked_builds_pve.items()):
                mon_name = profile.monsters[uid].name if uid in profile.monsters else f"Unit #{uid}"
                st.markdown(
                    f"- **{mon_name}**: `{', '.join(b.stats.active_sets)}` | "
                    f"Combat SPD `{b.stats.combat_spd}` | HP `{b.stats.total_hp}` | "
                    f"ATK `{b.stats.total_atk}` | Runas: `{b.rune_ids}`"
                )
        elif profile.locked_runes_pve:
            st.write("IDs de runas bloqueadas:", sorted(profile.locked_runes_pve))
        else:
            st.caption("No hay runas ni builds bloqueadas en PVE actualmente.")

    with col_rta:
        st.markdown(f"### Modo RTA (World Arena) — `{len(profile.locked_runes_rta)}` runas bloqueadas")
        if st.button("🔓 Desbloquear todas las runas RTA"):
            profile.locked_runes_rta.clear()
            st.session_state.locked_builds_rta.clear()
            st.rerun()

        if st.session_state.locked_builds_rta:
            for uid, b in list(st.session_state.locked_builds_rta.items()):
                mon_name = profile.monsters[uid].name if uid in profile.monsters else f"Unit #{uid}"
                st.markdown(
                    f"- **{mon_name}**: `{', '.join(b.stats.active_sets)}` | "
                    f"Combat SPD `{b.stats.combat_spd}` | HP `{b.stats.total_hp}` | "
                    f"ATK `{b.stats.total_atk}` | Runas: `{b.rune_ids}`"
                )
        elif profile.locked_runes_rta:
            st.write("IDs de runas bloqueadas:", sorted(profile.locked_runes_rta))
        else:
            st.caption("No hay runas ni builds bloqueadas en RTA actualmente.")


def main() -> None:
    st.set_page_config(
        page_title="SW-OptiPy | Summoners War Optimizer",
        page_icon="⚡",
        layout="wide",
    )
    _init_session_state()
    profile, mode, sky_totem, leader_spd = render_sidebar()

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📊 Dashboard de Runas",
            "🧮 Optimizador General / PVE",
            "⏱️ Builder RTA & Speed Tuning",
            "🔒 Gestor de Builds Bloqueadas",
        ]
    )

    with tab1:
        render_tab_dashboard(profile)
    with tab2:
        render_tab_optimizer(profile, mode, sky_totem, leader_spd)
    with tab3:
        render_tab_speed_tuning(profile, mode, sky_totem, leader_spd)
    with tab4:
        render_tab_locked_builds(profile)


if __name__ == "__main__":
    main()

