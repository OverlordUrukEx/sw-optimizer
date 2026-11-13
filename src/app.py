"""Streamlit Web UI for SW-OptiPy fully localized in Spanish (es-LA / es) with competitive Summoners War terminology."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any, Iterable, Literal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl
import streamlit as st
import streamlit.components.v1 as components

from src.calculator import (
    PVE_TICK_SIZE,
    RTA_TICK_SIZE,
    SpeedTuneMember,
    calculate_monster_stats,
    calculate_rune_efficiency,
    simulate_speed_tuning,
)
from src.i18n import (
    ELEMENT_NAMES_ES,
    ES_LOCALE,
    get_element_badge_es,
    translate_element,
)
from src.models import (
    AccountProfile,
    Monster,
    NAME_TO_SET_ID,
    SET_ID_MAP,
    STAT_ID_MAP,
)
from src.monster_data_service import MonsterDataService
from src.optimizer import (
    OptimizationConstraints,
    OptimizedBuild,
    TeamOptimizationRequestMember,
    optimize_monster_builds,
    optimize_team_speed_tuning,
)
from src.parser import parse_swex_json
from src.services.storage import AccountStorageService
from src.ui_components import (
    TOOLTIPS,
    activate_account_profile,
    load_demo_account_profile,
    render_empty_state_hero,
    render_top_navbar,
)
from src.workers import OptimizerProgressUpdate, OptimizerWorker

ALL_ELEMENTS: list[str] = ["Water", "Fire", "Wind", "Light", "Dark"]

# Competitive stat labels with Spanish descriptions
COMPETITIVE_STAT_LABELS: dict[int, str] = {
    1: "HP Flat (Vida Plana)",
    2: "HP% (Vida %)",
    3: "ATK Flat (Ataque Plano)",
    4: "ATK% (Ataque %)",
    5: "DEF Flat (Defensa Plana)",
    6: "DEF% (Defensa %)",
    8: "SPD (Velocidad)",
    9: "CR / Tasa Crít. (%)",
    10: "CD / Daño Crít. (%)",
    11: "RES (Resistencia %)",
    12: "ACC (Precisión %)",
}


def get_element_badge(element: str) -> str:
    """Returns a formatted Spanish Element badge (e.g., '🔥 Fuego', '🌪️ Viento')."""
    return get_element_badge_es(element)


def format_monster_label(monster: Monster) -> str:
    """Formats a monster option label with untouched Monster Name, Spanish Element badge, and Stars."""
    badge = get_element_badge_es(monster.element)
    stars = f"{monster.base_stars}★"
    return f"{monster.name} — {badge} ({stars})"


def _normalize_element_filter(elements: Iterable[str] | None) -> set[str]:
    """Normalizes English ('Water') or Spanish ('Agua') element filter strings to internal keys."""
    if not elements:
        return set()
    reverse_es = {v.lower(): k for k, v in ELEMENT_NAMES_ES.items()}
    normalized: set[str] = set()
    for elem in elements:
        clean = elem.strip()
        low = clean.lower()
        if low in reverse_es:
            normalized.add(reverse_es[low])
        else:
            normalized.add(clean.capitalize())
    return normalized


def filter_monsters(
    monsters: Iterable[Monster],
    search_query: str = "",
    elements: Iterable[str] | None = None,
) -> list[Monster]:
    """Filters and sorts monsters by name substring (or ID/Spanish element) and selected elements."""
    query = search_query.strip().lower()
    allowed_elements = _normalize_element_filter(elements)

    matched: list[Monster] = []
    for monster in monsters:
        if allowed_elements and monster.element.capitalize() not in allowed_elements:
            continue
        if query:
            esp_el = translate_element(monster.element).lower()
            searchable = (
                f"{monster.name.lower()} {monster.element.lower()} "
                f"{esp_el} {monster.unit_master_id}"
            )
            if query not in searchable:
                continue
        matched.append(monster)

    return sorted(matched, key=lambda m: (m.name.lower(), m.unit_id))


def render_monster_card(monster: Monster, subtitle: str = "") -> None:
    """Renders a visual monster card with SWARFARM avatar icon, untouched Name, and Spanish Element badge."""
    badge = get_element_badge_es(monster.element)
    stars_str = "★" * max(1, min(6, monster.base_stars))
    sub_html = (
        f"<div style='font-size:0.82rem;color:#9ca3af;margin-top:2px;'>{subtitle}</div>"
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;
                    border-radius:10px;background:rgba(38,39,48,0.65);
                    border:1px solid rgba(250,250,250,0.12);margin-bottom:10px;">
            <img src="{monster.icon_url}" alt="{monster.name}"
                 style="width:52px;height:52px;border-radius:10px;object-fit:cover;
                        border:2px solid rgba(240,185,11,0.65);background:#1f2937;" />
            <div style="line-height:1.25;">
                <div style="font-weight:700;font-size:1.02rem;color:#f9fafb;">
                    {monster.name}
                    <span style="font-size:0.82rem;color:#fbbf24;margin-left:6px;">{stars_str}</span>
                </div>
                <div style="font-size:0.85rem;color:#d1d5db;margin-top:2px;">
                    <span style="padding:2px 8px;border-radius:999px;background:rgba(255,255,255,0.08);">
                        {badge}
                    </span>
                    <span style="margin-left:8px;color:#9ca3af;" title="HP Base = CON * 15">
                        HP {monster.base_hp} · ATK {monster.atk} · DEF {monster.def_} · SPD {monster.spd}
                    </span>
                </div>
                {sub_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def inject_browser_monster_cache(service: MonsterDataService) -> None:
    """Synchronizes monster_map metadata and active account inventory into asynchronous browser IndexedDB (`SWOptimizerDB`)."""
    profile: AccountProfile | None = st.session_state.get("profile")
    is_demo = bool(st.session_state.get("is_demo_mode", False))
    file_sig = str(st.session_state.get("loaded_file_sig") or "")
    clear_pending = bool(st.session_state.get("indexeddb_clear_pending", False))
    bridge_html = AccountStorageService.build_indexeddb_bridge_html(
        monster_service=service,
        profile=profile,
        is_demo_mode=is_demo,
        file_signature=file_sig,
        clear_account_store=clear_pending,
    )
    if clear_pending:
        st.session_state.indexeddb_clear_pending = False
    components.html(bridge_html, height=0, width=0)


def _init_session_state() -> None:
    if "monster_service" not in st.session_state:
        st.session_state.monster_service = MonsterDataService.get_instance()
    if "storage_service" not in st.session_state:
        st.session_state.storage_service = AccountStorageService.get_instance()
    if "optimizer_worker" not in st.session_state:
        st.session_state.optimizer_worker = OptimizerWorker()
    if "profile" not in st.session_state:
        restored = st.session_state.storage_service.restore_account()
        if restored is not None:
            st.session_state.profile = restored.profile
            st.session_state.is_demo_mode = restored.is_demo_mode
            st.session_state.loaded_file_sig = restored.file_signature
        else:
            st.session_state.profile = None
    if "is_demo_mode" not in st.session_state:
        st.session_state.is_demo_mode = False
    if "loaded_file_sig" not in st.session_state:
        st.session_state.loaded_file_sig = None
    if "indexeddb_clear_pending" not in st.session_state:
        st.session_state.indexeddb_clear_pending = False
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


def build_monsters_dataframe(
    profile: AccountProfile,
    search_query: str = "",
    selected_elements: list[str] | None = None,
) -> pl.DataFrame:
    """Builds a Polars DataFrame of monsters with Avatar URL, resolved Name, Spanish Element badge, and Base Stats."""
    filtered = filter_monsters(
        profile.monsters.values(),
        search_query=search_query,
        elements=selected_elements,
    )
    tbl_i18n = ES_LOCALE["tables"]
    rows: list[dict[str, Any]] = []
    for m in filtered:
        badge = get_element_badge_es(m.element)
        rows.append(
            {
                "Avatar": m.icon_url,
                "Monstruo": m.name,
                "Element": badge,
                tbl_i18n["element"]: badge,
                tbl_i18n["stars"]: f"{m.base_stars}★",
                tbl_i18n["level"]: m.unit_level,
                "HP Base": m.base_hp,
                "ATK Base": m.atk,
                "DEF Base": m.def_,
                "SPD Base": m.spd,
                "Runas PVE": len(m.runes),
                "Runas RTA": len(m.rta_runes),
                "Artefactos": len(m.artifacts),
            }
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)


def _build_runes_dataframe(profile: AccountProfile) -> pl.DataFrame:
    """Builds the Polars DataFrame for the Rune Dashboard in Spanish with competitive terminology."""
    tbl_i18n = ES_LOCALE["tables"]
    rows: list[dict[str, Any]] = []
    for r in profile.runes.values():
        if r.occupied_id in profile.monsters:
            m_pve = profile.monsters[r.occupied_id]
            pve_owner = f"{m_pve.name} ({get_element_badge_es(m_pve.element)})"
            owner_icon = m_pve.icon_url
        else:
            pve_owner = tbl_i18n["free_inventory"]
            owner_icon = ""

        if r.rta_occupied_id in profile.monsters:
            m_rta = profile.monsters[r.rta_occupied_id]
            rta_owner = f"{m_rta.name} ({get_element_badge_es(m_rta.element)})"
        else:
            rta_owner = tbl_i18n["free_rta_inventory"]

        grade_str = (
            f"{r.stars}★ {tbl_i18n['ancient_rune']}"
            if r.is_ancient
            else f"{r.stars}★ {tbl_i18n['normal_rune']}"
        )

        rows.append(
            {
                "Rune ID": r.rune_id,
                "Owner Icon": owner_icon,
                tbl_i18n["equipped_on"]: pve_owner,
                "Equipada PVE": pve_owner,
                "Equipada RTA": rta_owner,
                "Slot": r.slot_no,
                "Set": r.set_name,
                tbl_i18n["stars"]: grade_str,
                tbl_i18n["level"]: f"+{r.upgrade_curr}",
                "Main Stat": f"{STAT_ID_MAP.get(r.main_stat_id, '')} +{r.main_stat_val}",
                "Innata": (
                    f"{STAT_ID_MAP.get(r.innate_stat_id, '')} +{r.innate_stat_val}"
                    if r.innate_stat_id > 0
                    else "-"
                ),
                "SPD": r.get_stat_total(8),
                "CR / Tasa Crít.": r.get_stat_total(9),
                "CD / Daño Crít.": r.get_stat_total(10),
                "HP%": r.get_stat_total(2),
                "ATK%": r.get_stat_total(4),
                "DEF%": r.get_stat_total(6),
                "ACC": r.get_stat_total(12),
                "RES": r.get_stat_total(11),
                "Eficiencia (%)": calculate_rune_efficiency(r, use_grinds=True),
                "Efic. Base (%)": calculate_rune_efficiency(r, use_grinds=False),
                "Bloqueada PVE": r.rune_id in profile.locked_runes_pve,
                "Bloqueada RTA": r.rune_id in profile.locked_runes_rta,
            }
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort("Eficiencia (%)", descending=True)


def render_sidebar() -> tuple[AccountProfile | None, Literal["pve", "rta"], float, float]:
    nav_i18n = ES_LOCALE["navbar"]
    st.sidebar.title("⚡ SW-OptiPy")
    st.sidebar.caption(ES_LOCALE["app"]["subtitle"])

    monster_service: MonsterDataService = st.session_state.monster_service

    uploaded = st.sidebar.file_uploader(
        nav_i18n["upload_json"],
        type=["json"],
        key="sidebar_swex_uploader",
        help="Sube el archivo .json exportado por Summoners War Exporter (SWEX). Cero llamadas N+1.",
    )

    if uploaded is not None:
        raw_bytes = uploaded.getvalue()
        file_hash = hashlib.sha256(raw_bytes).hexdigest()
        if st.session_state.get("loaded_file_sig") != file_hash:
            try:
                parsed = parse_swex_json(
                    raw_bytes, bestiary=monster_service, fetch_remote_bestiary=False
                )
                activate_account_profile(parsed, is_demo=False, file_signature=file_hash)
                st.sidebar.success(f"Cuenta cargada: {parsed.wizard_name}")
            except Exception as exc:
                st.sidebar.error(f"Archivo JSON de SWEX inválido: {exc}")

    if st.sidebar.button(
        f"🎮 {nav_i18n['try_demo']}",
        use_container_width=True,
        help="Carga src/data/demo_account.json (Demo_Summoner) de forma inmediata.",
    ):
        demo_prof = load_demo_account_profile(monster_service=monster_service)
        activate_account_profile(demo_prof, is_demo=True, file_signature="demo_account")
        st.rerun()

    if st.sidebar.button(
        "🔄 Sincronizar Bestiario (SWARFARM)",
        use_container_width=True,
        help="Sincroniza el catálogo completo de monstruos desde la API v2 de SWARFARM en src/data/monster_map.json.",
    ):
        try:
            count = monster_service.sync_from_swarfarm(force=True)
            st.sidebar.success(f"Se sincronizaron {count:,} monstruos en el mapa local.")
        except Exception as exc:
            st.sidebar.warning(
                f"Modo offline activo ({monster_service.size:,} monstruos): {exc}"
            )

    profile: AccountProfile | None = st.session_state.profile

    mode_label = st.sidebar.radio(
        "Modo de Inventario Activo",
        options=["Modo Normal (PVE / Siege / Arena)", "Modo RTA (World Arena)"],
        index=0 if st.session_state.inventory_mode == "pve" else 1,
        help="Alterna entre los inventarios y bloqueos independientes de PVE y RTA.",
    )
    mode: Literal["pve", "rta"] = "rta" if "RTA" in mode_label else "pve"
    st.session_state.inventory_mode = mode

    st.sidebar.divider()
    st.sidebar.subheader("Bonos Globales de Combate")
    sky_totem_pct = st.sidebar.slider(
        "Sky Totem SPD (%)",
        0,
        15,
        15,
        help="Bono del Tótem de Tribu del Cielo (+15% Base SPD al nivel máximo).",
    )
    leader_spd_pct = st.sidebar.selectbox(
        "Líder de SPD (%)",
        options=[0, 10, 15, 19, 21, 24, 28, 30, 33],
        index=0,
        help="Porcentaje de habilidad de líder de velocidad aplicado sobre el Base SPD.",
    )

    st.sidebar.divider()
    if profile is not None:
        st.sidebar.markdown(
            f"**Invocador:** `{profile.wizard_name}`  \n"
            f"**{nav_i18n['level']}:** `{profile.wizard_level}`  \n"
            f"**{nav_i18n['mana']}:** `{profile.wizard_mana:,}`  \n"
            f"**{nav_i18n['crystals']}:** `{profile.wizard_crystal:,}`  \n"
            f"**Monstruos:** `{len(profile.monsters)}` | **Runas:** `{len(profile.runes)}` | **Artefactos:** `{len(profile.artifacts)}`  \n"
            f"**Bloqueadas PVE:** `{len(profile.locked_runes_pve)}` | **RTA:** `{len(profile.locked_runes_rta)}`"
        )
    else:
        st.sidebar.caption(
            f"Bestiario O(1) listo (`{monster_service.size:,}` especies). Sin cuenta cargada."
        )

    return profile, mode, sky_totem_pct / 100.0, leader_spd_pct / 100.0


def render_tab_dashboard(profile: AccountProfile) -> None:
    tbl_i18n = ES_LOCALE["tables"]
    st.subheader(
        f"👾 {tbl_i18n['monsters']} ({len(profile.monsters)}) · "
        f"{tbl_i18n['runes']} ({len(profile.runes)}) · "
        f"{tbl_i18n['artifacts']} ({len(profile.artifacts)})"
    )
    mf1, mf2 = st.columns([2, 2])
    monster_search = mf1.text_input(
        f"🔍 {tbl_i18n['search_monster']}",
        value="",
        placeholder="Ej. Lushen, Verdehile, Kro, Lapis, Demo_Homu...",
        key="dashboard_monster_search",
    )
    monster_elements = mf2.multiselect(
        tbl_i18n["element"],
        options=ALL_ELEMENTS,
        default=[],
        format_func=get_element_badge_es,
        key="dashboard_monster_elements",
    )

    monsters_df = build_monsters_dataframe(
        profile, search_query=monster_search, selected_elements=monster_elements
    )
    if monsters_df.is_empty():
        st.info("Ningún monstruo coincide con el filtro de nombre o elemento actual.")
    else:
        display_cols = [c for c in monsters_df.columns if c != "Element"]
        st.dataframe(
            monsters_df.select(display_cols),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Avatar": st.column_config.ImageColumn("Avatar", width="small"),
                "HP Base": st.column_config.NumberColumn(
                    "HP Base", help=TOOLTIPS["hp"]
                ),
                "ATK Base": st.column_config.NumberColumn(
                    "ATK Base", help=TOOLTIPS["atk"]
                ),
                "DEF Base": st.column_config.NumberColumn(
                    "DEF Base", help=TOOLTIPS["def"]
                ),
                "SPD Base": st.column_config.NumberColumn(
                    "SPD Base", help=TOOLTIPS["spd"]
                ),
            },
        )

    st.divider()
    st.subheader(f"📊 Inventario de {tbl_i18n['runes']} (Fórmula de Eficiencia de Barion)")
    df = _build_runes_dataframe(profile)
    if df.is_empty():
        st.warning("No se encontraron runas en el perfil actual.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Total de {tbl_i18n['runes']}", len(df))
    c2.metric(
        "Eficiencia Media",
        f"{df['Eficiencia (%)'].mean():.2f}%",
        help=TOOLTIPS["barion_efficiency"],
    )
    c3.metric(
        "Runas >= 100% Efic.",
        int((df["Eficiencia (%)"] >= 100.0).sum()),
        help=TOOLTIPS["barion_efficiency"],
    )
    c4.metric("Runas >= 25 SPD", int((df["SPD"] >= 25).sum()), help=TOOLTIPS["spd"])

    f1, f2, f3 = st.columns(3)
    all_sets = sorted(df["Set"].unique().to_list())
    selected_sets = f1.multiselect("Filtrar por Set de Runa", options=all_sets, default=[])
    selected_slots = f2.multiselect(
        "Filtrar por Slot", options=[1, 2, 3, 4, 5, 6], default=[]
    )
    min_eff = f3.slider(
        "Eficiencia Mínima (%)",
        0.0,
        130.0,
        0.0,
        step=1.0,
        help=TOOLTIPS["barion_efficiency"],
    )

    filtered = df.filter(pl.col("Eficiencia (%)") >= min_eff)
    if selected_sets:
        filtered = filtered.filter(pl.col("Set").is_in(selected_sets))
    if selected_slots:
        filtered = filtered.filter(pl.col("Slot").is_in(selected_slots))

    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Owner Icon": st.column_config.ImageColumn(" Portador", width="small"),
            "Eficiencia (%)": st.column_config.NumberColumn(
                "Eficiencia (%)", help=TOOLTIPS["barion_efficiency"]
            ),
            "CR / Tasa Crít.": st.column_config.NumberColumn(
                "CR / Tasa Crít.", help=TOOLTIPS["cr"]
            ),
            "CD / Daño Crít.": st.column_config.NumberColumn(
                "CD / Daño Crít.", help=TOOLTIPS["cd"]
            ),
        },
    )


def render_tab_optimizer(
    profile: AccountProfile,
    mode: Literal["pve", "rta"],
    sky_totem: float,
    leader_spd: float,
) -> None:
    opt_i18n = ES_LOCALE["optimizer"]
    tbl_i18n = ES_LOCALE["tables"]
    stats_i18n = ES_LOCALE["stats"]

    st.subheader(
        f"🧮 {opt_i18n['panel_title']} — Branch & Bound ({'RTA' if mode == 'rta' else 'PVE / Normal'})"
    )

    col_left, col_right = st.columns([1, 2])
    with col_left:
        st.markdown(f"**{opt_i18n['select_monster']}**")
        opt_search = st.text_input(
            f"🔍 {tbl_i18n['search_monster']}",
            value="",
            placeholder="Escribe el nombre del monstruo...",
            key="opt_monster_search",
        )
        opt_elements = st.multiselect(
            tbl_i18n["element"],
            options=ALL_ELEMENTS,
            default=[],
            format_func=get_element_badge_es,
            key="opt_monster_elements",
        )
        filtered_monsters = filter_monsters(
            profile.monsters.values(),
            search_query=opt_search,
            elements=opt_elements,
        )
        if not filtered_monsters:
            st.warning("Ningún monstruo coincide con tu búsqueda o filtro de elemento.")
            return

        selected_monster = st.selectbox(
            opt_i18n["select_monster"],
            options=filtered_monsters,
            format_func=format_monster_label,
            key="opt_target_monster",
        )
        render_monster_card(selected_monster)

        set_names = [name for sid, name in sorted(SET_ID_MAP.items()) if sid != 25]
        req_set_names = st.multiselect(
            f"{opt_i18n['rune_sets']} (Violent, Swift, Will, Despair, Rage, Fatal, Blade, Intangible...)",
            options=set_names,
            default=[],
            help=f"{TOOLTIPS['broken_sets']} {TOOLTIPS['intangible_wildcard']}",
        )
        req_set_ids = [NAME_TO_SET_ID[n.lower()] for n in req_set_names]

        st.markdown(f"**{opt_i18n['main_stats_246']}**")
        stat_options = {
            f"{COMPETITIVE_STAT_LABELS.get(k, v)} ({k})": k
            for k, v in STAT_ID_MAP.items()
        }
        default_s2 = [
            lbl for lbl, sid in stat_options.items() if sid in (8, 4, 2, 6)
        ]
        default_s4 = [
            lbl for lbl, sid in stat_options.items() if sid in (10, 9, 2, 4, 6)
        ]
        default_s6 = [
            lbl for lbl, sid in stat_options.items() if sid in (4, 2, 6, 12)
        ]

        s2_names = st.multiselect(
            opt_i18n["slot_2_main"],
            options=list(stat_options.keys()),
            default=default_s2,
        )
        s4_names = st.multiselect(
            opt_i18n["slot_4_main"],
            options=list(stat_options.keys()),
            default=default_s4,
        )
        s6_names = st.multiselect(
            opt_i18n["slot_6_main"],
            options=list(stat_options.keys()),
            default=default_s6,
        )

        st.markdown(f"**{opt_i18n['min_stat_filters']}**")
        r1, r2 = st.columns(2)
        min_spd = r1.number_input(
            f"Min {stats_i18n['spd']}",
            min_value=0,
            max_value=400,
            value=130,
            help=TOOLTIPS["spd"],
        )
        max_spd = r2.number_input(
            f"Max {stats_i18n['spd']}",
            min_value=1,
            max_value=999,
            value=450,
            help=TOOLTIPS["spd"],
        )
        min_cr = r1.number_input(
            f"Min {stats_i18n['cr']} (%)",
            min_value=0,
            max_value=100,
            value=15,
            help=TOOLTIPS["cr"],
        )
        min_cdmg = r2.number_input(
            f"Min {stats_i18n['cd']} (%)",
            min_value=0,
            max_value=350,
            value=50,
            help=TOOLTIPS["cd"],
        )
        min_hp = r1.number_input(
            f"Min {stats_i18n['hp']}",
            min_value=0,
            max_value=100000,
            value=9000,
            step=500,
            help=TOOLTIPS["hp"],
        )
        min_atk = r2.number_input(
            f"Min {stats_i18n['atk']}",
            min_value=0,
            max_value=10000,
            value=500,
            step=100,
            help=TOOLTIPS["atk"],
        )
        min_acc = r1.number_input(
            f"Min {stats_i18n['acc']} (%)",
            min_value=0,
            max_value=100,
            value=0,
            help=TOOLTIPS["acc"],
        )
        min_res = r2.number_input(
            f"Min {stats_i18n['res']} (%)",
            min_value=0,
            max_value=100,
            value=15,
            help=TOOLTIPS["res"],
        )

        goal_labels = {
            "damage": "Daño Promedio (Damage Multiplier)",
            "ehp": "EHP (Vida Efectiva / Tanque)",
            "spd": "SPD (Velocidad Máxima)",
            "efficiency": "Eficiencia de Runa (Barion)",
            "atk": "ATK (Ataque Total)",
            "hp": "HP (Vida Total)",
            "def": "DEF (Defensa Total)",
        }
        opt_for = st.selectbox(
            opt_i18n["optimization_goal"],
            options=list(goal_labels.keys()),
            format_func=lambda k: goal_labels[k],
            index=0,
            help=f"{TOOLTIPS['damage_multiplier']} | {TOOLTIPS['effective_hp']}",
        )
        include_equipped = st.checkbox(
            opt_i18n["include_equipped_runes"],
            value=True,
            help=TOOLTIPS["include_equipped_runes"],
        )
        allow_broken = st.checkbox(
            opt_i18n["allow_broken_sets"],
            value=True,
            help=TOOLTIPS["broken_sets"],
        )
        sim_15 = st.checkbox(
            opt_i18n["simulate_plus15"],
            value=True,
            help=TOOLTIPS["simulate_plus15"],
        )
        max_per_slot = st.slider(
            "Profundidad por Slot (Focus Pruning)",
            8,
            35,
            18,
            help=TOOLTIPS["focus_pruning"],
        )

        run_btn = st.button(
            opt_i18n["calculate_builds"],
            type="primary",
            use_container_width=True,
        )

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
                min_cdmg=int(min_cdmg),
                min_acc=int(min_acc),
                min_res=int(min_res),
                min_hp=int(min_hp),
                min_atk=int(min_atk),
                simulate_plus15=sim_15,
                allow_broken_sets=allow_broken,
                sky_totem=sky_totem,
                leader_skill_spd=leader_spd,
                optimize_for=opt_for,  # type: ignore[arg-type]
                max_runes_per_slot=max_per_slot,
                top_k=10,
            )
            excluded_units = (
                None
                if include_equipped
                else {
                    uid
                    for uid in profile.monsters
                    if uid != selected_monster.unit_id
                }
            )
            pool = profile.get_available_runes(
                mode=mode, excluded_unit_ids=excluded_units
            )
            progress_bar = st.progress(0.0, text="Iniciando worker de optimización Branch & Bound...")
            worker: OptimizerWorker = st.session_state.get(
                "optimizer_worker", OptimizerWorker()
            )

            def _on_opt_progress(update: OptimizerProgressUpdate) -> None:
                progress_bar.progress(
                    min(1.0, max(0.0, update.progress_ratio)),
                    text=update.stage_label,
                )

            res = worker.run_monster_optimization(
                monster=selected_monster,
                available_runes=pool,
                constraints=cfg,
                on_progress=_on_opt_progress,
            )
            progress_bar.empty()
            st.session_state.last_opt_result = res

        opt_res = st.session_state.last_opt_result
        if opt_res is not None:
            target_mon = profile.monsters.get(opt_res.unit_id, selected_monster)
            render_monster_card(
                target_mon,
                subtitle=(
                    f"{opt_i18n['results_found']}: {len(opt_res.builds)} | "
                    f"Builds evaluadas: {opt_res.evaluated_builds:,} | "
                    f"Ramas (2,4,6) podadas: {opt_res.pruned_triplets_246:,}/{opt_res.total_triplets_246:,} | "
                    f"Tiempo: {opt_res.elapsed_ms:.2f} ms"
                ),
            )
            if not opt_res.builds:
                st.warning(
                    "Ninguna combinación de runas cumplió todos los filtros. Reduce los mínimos o activa 'Incluir runas equipadas' / 'Permitir Sets Rotos (Broken)'."
                )
            else:
                st.markdown(f"#### 🏆 {opt_i18n['results_found']} ({len(opt_res.builds)})")
                build_rows = []
                for b in opt_res.builds:
                    s = b.stats
                    build_rows.append(
                        {
                            "Rank": b.rank,
                            "Avatar": target_mon.icon_url,
                            "Monstruo": target_mon.name,
                            tbl_i18n["element"]: get_element_badge_es(target_mon.element),
                            "Score": b.score,
                            "Sets de Runas": ", ".join(s.active_sets)
                            if s.active_sets
                            else "Broken (Set Roto)",
                            "Intangible ->": s.intangible_replaced_set or "-",
                            "SPD": s.combat_spd,
                            "SPD Runa": f"+{s.rune_spd}",
                            "HP": s.total_hp,
                            "ATK": s.total_atk,
                            "DEF": s.total_def,
                            "CR / Tasa Crít.": s.crate,
                            "CD / Daño Crít.": s.cdmg,
                            "ACC": s.acc,
                            "RES": s.res,
                            "EHP": s.ehp,
                            "Efic. Media (%)": s.avg_efficiency,
                            "Runas (Slots 1-6)": str(b.rune_ids),
                        }
                    )
                st.dataframe(
                    pl.DataFrame(build_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Avatar": st.column_config.ImageColumn("Avatar", width="small"),
                        "Score": st.column_config.NumberColumn(
                            "Score", help=TOOLTIPS["damage_multiplier"]
                        ),
                        "EHP": st.column_config.NumberColumn(
                            "EHP", help=TOOLTIPS["effective_hp"]
                        ),
                        "Sets de Runas": st.column_config.TextColumn(
                            "Sets de Runas", help=TOOLTIPS["broken_sets"]
                        ),
                    },
                )

                chosen_rank = st.selectbox(
                    "Seleccionar Rank de Build para Bloquear Runas",
                    options=[b.rank for b in opt_res.builds],
                    index=0,
                )
                if st.button(f"🔒 Bloquear Build #{chosen_rank} en modo {mode.upper()}"):
                    chosen_build: OptimizedBuild = opt_res.builds[chosen_rank - 1]
                    target_set = (
                        profile.locked_runes_rta
                        if mode == "rta"
                        else profile.locked_runes_pve
                    )
                    target_dict = (
                        st.session_state.locked_builds_rta
                        if mode == "rta"
                        else st.session_state.locked_builds_pve
                    )
                    for rid in chosen_build.rune_ids:
                        target_set.add(rid)
                    target_dict[opt_res.unit_id] = chosen_build
                    storage_svc: AccountStorageService = st.session_state.get(
                        "storage_service", AccountStorageService.get_instance()
                    )
                    storage_svc.save_account(
                        profile=profile,
                        is_demo_mode=bool(st.session_state.get("is_demo_mode", False)),
                        file_signature=str(st.session_state.get("loaded_file_sig") or "custom"),
                    )
                    st.success(
                        f"Se bloquearon las runas {chosen_build.rune_ids} para {target_mon.name} ({get_element_badge_es(target_mon.element)}) en modo {mode.upper()}."
                    )


def render_tab_speed_tuning(
    profile: AccountProfile,
    mode: Literal["pve", "rta"],
    sky_totem: float,
    leader_spd: float,
) -> None:
    tbl_i18n = ES_LOCALE["tables"]
    tick_val = RTA_TICK_SIZE if mode == "rta" else PVE_TICK_SIZE
    st.subheader(
        f"⏱️ Builder de Equipos y Speed Tuning (Modo {mode.upper()} — Tick = {tick_val})"
    )

    f_col1, f_col2 = st.columns([2, 2])
    st_search = f_col1.text_input(
        f"🔍 {tbl_i18n['search_monster']}",
        value="",
        placeholder="Buscar monstruo para el equipo...",
        key="st_monster_search",
    )
    st_elements = f_col2.multiselect(
        tbl_i18n["element"],
        options=ALL_ELEMENTS,
        default=[],
        format_func=get_element_badge_es,
        key="st_monster_elements",
    )

    filtered_pool = filter_monsters(
        profile.monsters.values(), search_query=st_search, elements=st_elements
    )
    all_monsters_sorted = filter_monsters(profile.monsters.values())

    option_map = {m.unit_id: m for m in filtered_pool}
    for m in all_monsters_sorted:
        option_map.setdefault(m.unit_id, m)
    selectable_monsters = list(option_map.values())

    preferred_names = ["Spectra", "Loren", "Kro", "Bernard", "Galleon", "Lushen"]
    default_team = [
        m for name in preferred_names for m in selectable_monsters if m.name == name
    ]
    if len(default_team) < 3:
        default_team = selectable_monsters[:3]

    selected_team = st.multiselect(
        "Seleccionar Monstruos del Equipo (en el orden de turno deseado 1 ➔ N)",
        options=selectable_monsters,
        default=default_team[:3],
        format_func=format_monster_label,
        max_selections=6,
    )

    if not selected_team:
        st.info("Selecciona al menos 2 monstruos para simular y optimizar el Speed Tuning.")
        return

    sim_members: list[SpeedTuneMember] = []
    team_opt_reqs: list[TeamOptimizationRequestMember] = []

    cols = st.columns(len(selected_team))
    for idx, mon in enumerate(selected_team):
        equipped = profile.get_equipped_runes(mon.unit_id, mode=mode)
        curr_stats = calculate_monster_stats(
            mon, equipped, sky_totem=sky_totem, leader_skill_spd=leader_spd
        )
        with cols[idx]:
            render_monster_card(mon, subtitle=f"Turno #{idx + 1}")
            r_spd = st.number_input(
                f"SPD de Runas (#{idx + 1})",
                min_value=0,
                max_value=260,
                value=curr_stats.rune_spd if curr_stats.rune_spd > 0 else 120 - idx * 15,
                key=f"st_rspd_{idx}_{mon.unit_id}",
            )
            swift_on = st.checkbox(
                "Set Swift Activo",
                value=("Swift" in curr_stats.active_sets or idx == 0),
                key=f"st_swift_{idx}_{mon.unit_id}",
            )
            atb_boost = st.number_input(
                "Boost ATB Aliado (%)",
                min_value=0.0,
                max_value=100.0,
                value=30.0 if idx == 0 and "Bernard" in mon.name else 0.0,
                step=5.0,
                key=f"st_boost_{idx}_{mon.unit_id}",
            )
            spd_buff = st.checkbox(
                "Aplica Buff de SPD (+30%)",
                value=(idx == 0 and "Bernard" in mon.name),
                key=f"st_spdbuff_{idx}_{mon.unit_id}",
            )
            role_goal = st.selectbox(
                "Objetivo de Build",
                options=["spd", "damage", "ehp", "efficiency"],
                index=0 if idx < len(selected_team) - 1 else 1,
                key=f"st_goal_{idx}_{mon.unit_id}",
                help=f"{TOOLTIPS['damage_multiplier']} | {TOOLTIPS['effective_hp']}",
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
            f"✅ Speed Tuning Perfecto ({mode.upper()} tick={report.tick_size}): "
            f"Secuencia de turnos: {' ➔ '.join(report.turn_sequence)}"
        )
    else:
        st.error(
            f"⚠️ Desajuste de Speed Tuning ({mode.upper()} tick={report.tick_size}): "
            f"Secuencia real: {' ➔ '.join(report.turn_sequence)}"
        )

    tune_rows = []
    for m in report.members:
        mon_obj = profile.monsters.get(m.unit_id)
        tune_rows.append(
            {
                "Turno Esperado": m.expected_turn_order,
                "Avatar": mon_obj.icon_url if mon_obj else "",
                "Monstruo": m.name,
                tbl_i18n["element"]: get_element_badge_es(mon_obj.element)
                if mon_obj
                else "❓ Desconocido",
                "SPD de Combate": m.combat_spd,
                "Tick 1er Turno": m.first_turn_tick,
                "Turno Real": m.actual_turn_order,
                "Min SPD Combate Req.": m.min_combat_spd_required,
                "Min SPD Runa Req.": f"+{m.min_rune_spd_required}",
                "Estado": "✅ Sincronizado" if m.is_tuned else "❌ Cortado / Desordenado",
            }
        )
    st.dataframe(
        pl.DataFrame(tune_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Avatar": st.column_config.ImageColumn("Avatar", width="small"),
        },
    )

    if st.button(
        f"⚡ Calcular Builds y Bloquear Equipo Completo en Orden de Turno ({mode.upper()})",
        type="primary",
    ):
        team_progress = st.progress(0.0, text="Iniciando optimización secuencial de equipo en worker...")
        worker: OptimizerWorker = st.session_state.get(
            "optimizer_worker", OptimizerWorker()
        )

        def _on_team_progress(update: OptimizerProgressUpdate) -> None:
            team_progress.progress(
                min(1.0, max(0.0, update.progress_ratio)),
                text=update.stage_label,
            )

        team_results = worker.run_team_optimization(
            profile=profile,
            team_requests=team_opt_reqs,
            mode=mode,
            lock_winning_builds=True,
            on_progress=_on_team_progress,
        )
        team_progress.empty()
        st.session_state.last_team_opt_results = team_results
        target_dict = (
            st.session_state.locked_builds_rta
            if mode == "rta"
            else st.session_state.locked_builds_pve
        )
        for res in team_results:
            if res.builds:
                target_dict[res.unit_id] = res.builds[0]
        storage_svc: AccountStorageService = st.session_state.get(
            "storage_service", AccountStorageService.get_instance()
        )
        storage_svc.save_account(
            profile=profile,
            is_demo_mode=bool(st.session_state.get("is_demo_mode", False)),
            file_signature=str(st.session_state.get("loaded_file_sig") or "custom"),
        )

    if st.session_state.last_team_opt_results:
        st.markdown(f"#### 🏆 {ES_LOCALE['optimizer']['results_found']} por Turno")
        summary_rows = []
        for idx, res in enumerate(st.session_state.last_team_opt_results):
            if res.builds:
                b = res.builds[0]
                s = b.stats
                mon_obj = profile.monsters.get(res.unit_id)
                summary_rows.append(
                    {
                        "Turno #": idx + 1,
                        "Avatar": mon_obj.icon_url if mon_obj else "",
                        "Monstruo": res.monster_name,
                        tbl_i18n["element"]: get_element_badge_es(mon_obj.element)
                        if mon_obj
                        else "❓ Desconocido",
                        "Sets de Runas": ", ".join(s.active_sets)
                        if s.active_sets
                        else "Broken (Set Roto)",
                        "SPD Combate": s.combat_spd,
                        "SPD Runa": f"+{s.rune_spd}",
                        "HP": s.total_hp,
                        "ATK": s.total_atk,
                        "CR / Tasa Crít.": s.crate,
                        "CD / Daño Crít.": s.cdmg,
                        "ACC": s.acc,
                        "EHP": s.ehp,
                        "Runas Asignadas": str(b.rune_ids),
                    }
                )
        if summary_rows:
            st.dataframe(
                pl.DataFrame(summary_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Avatar": st.column_config.ImageColumn("Avatar", width="small"),
                },
            )


def render_tab_locked_builds(profile: AccountProfile) -> None:
    st.subheader("🔒 Gestor de Runas y Builds Bloqueadas (PVE vs RTA Independientes)")

    col_pve, col_rta = st.columns(2)
    with col_pve:
        st.markdown(
            f"### Modo Normal (PVE / Siege) — `{len(profile.locked_runes_pve)}` runas bloqueadas"
        )
        if st.button("🔓 Desbloquear todas las runas PVE"):
            profile.locked_runes_pve.clear()
            st.session_state.locked_builds_pve.clear()
            st.session_state.storage_service.save_account(
                profile=profile,
                is_demo_mode=bool(st.session_state.get("is_demo_mode", False)),
                file_signature=str(st.session_state.get("loaded_file_sig") or "custom"),
            )
            st.rerun()

        if st.session_state.locked_builds_pve:
            for uid, b in list(st.session_state.locked_builds_pve.items()):
                mon = profile.monsters.get(uid)
                if mon:
                    render_monster_card(
                        mon,
                        subtitle=(
                            f"Sets: {', '.join(b.stats.active_sets) or 'Broken'} | "
                            f"SPD Combate: {b.stats.combat_spd} | "
                            f"EHP: {b.stats.ehp:,.0f} | "
                            f"Runas: {b.rune_ids}"
                        ),
                    )
        elif profile.locked_runes_pve:
            st.write("IDs de Runas Bloqueadas:", sorted(profile.locked_runes_pve))
        else:
            st.caption("No hay runas ni builds bloqueadas en modo PVE actualmente.")

    with col_rta:
        st.markdown(
            f"### Modo RTA (World Arena) — `{len(profile.locked_runes_rta)}` runas bloqueadas"
        )
        if st.button("🔓 Desbloquear todas las runas RTA"):
            profile.locked_runes_rta.clear()
            st.session_state.locked_builds_rta.clear()
            st.session_state.storage_service.save_account(
                profile=profile,
                is_demo_mode=bool(st.session_state.get("is_demo_mode", False)),
                file_signature=str(st.session_state.get("loaded_file_sig") or "custom"),
            )
            st.rerun()

        if st.session_state.locked_builds_rta:
            for uid, b in list(st.session_state.locked_builds_rta.items()):
                mon = profile.monsters.get(uid)
                if mon:
                    render_monster_card(
                        mon,
                        subtitle=(
                            f"Sets: {', '.join(b.stats.active_sets) or 'Broken'} | "
                            f"SPD Combate: {b.stats.combat_spd} | "
                            f"EHP: {b.stats.ehp:,.0f} | "
                            f"Runas: {b.rune_ids}"
                        ),
                    )
        elif profile.locked_runes_rta:
            st.write("IDs de Runas Bloqueadas:", sorted(profile.locked_runes_rta))
        else:
            st.caption("No hay runas ni builds bloqueadas en modo RTA actualmente.")


def main() -> None:
    st.set_page_config(
        page_title=ES_LOCALE["app"]["title"],
        page_icon="⚡",
        layout="wide",
    )
    _init_session_state()
    inject_browser_monster_cache(st.session_state.monster_service)
    profile, mode, sky_totem, leader_spd = render_sidebar()

    render_top_navbar(
        profile, is_demo_mode=bool(st.session_state.get("is_demo_mode", False))
    )
    st.divider()

    if profile is None:
        render_empty_state_hero(st.session_state.monster_service)
        return

    tabs_i18n = ES_LOCALE["tabs"]
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            tabs_i18n["dashboard"],
            tabs_i18n["optimizer"],
            tabs_i18n["speed_tuning"],
            tabs_i18n["locked_builds"],
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
