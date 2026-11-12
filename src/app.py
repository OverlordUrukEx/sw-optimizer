"""Streamlit Web UI in Spanish (es-LA / es) for SW-OptiPy featuring Onboarding Empty State, Demo Mode, HelpGuideModal, and O(1) Bestiary."""

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
    ES_DICT,
    RUNE_SET_LABELS_ES,
    STAT_TOOLTIPS_ES,
    get_element_badge_es,
    normalize_element_to_en,
    translate_element_es,
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
from src.ui_components import (
    TOOLTIPS,
    activate_account_profile,
    clear_account_state,
    load_demo_account_profile,
    open_help_guide_dialog,
    render_empty_state_hero,
    render_top_navbar,
)

ALL_ELEMENTS: list[str] = ["Agua", "Fuego", "Viento", "Luz", "Oscuridad"]


def get_element_badge(element: str) -> str:
    """Returns a formatted Spanish Element badge (e.g., '🔥 Fuego', '🌪️ Viento')."""
    return get_element_badge_es(element)


def format_monster_label(monster: Monster) -> str:
    """Formats a monster option label with resolved Name, Spanish Element badge, and Stars."""
    badge = get_element_badge(monster.element)
    stars = f"{monster.base_stars}★"
    return f"{monster.name} — {badge} ({stars})"


def filter_monsters(
    monsters: Iterable[Monster],
    search_query: str = "",
    elements: Iterable[str] | None = None,
) -> list[Monster]:
    """Filters and sorts monsters by name substring (or ID) and selected elements (supports both ES and EN)."""
    query = search_query.strip().lower()
    allowed_elements_en = (
        {normalize_element_to_en(e) for e in elements} if elements else set()
    )

    matched: list[Monster] = []
    for monster in monsters:
        mon_element_en = normalize_element_to_en(monster.element)
        mon_element_es = translate_element_es(monster.element)
        if allowed_elements_en and mon_element_en not in allowed_elements_en:
            continue
        if query:
            searchable = (
                f"{monster.name.lower()} "
                f"{monster.element.lower()} "
                f"{mon_element_es.lower()} "
                f"{monster.unit_master_id}"
            )
            if query not in searchable:
                continue
        matched.append(monster)

    return sorted(matched, key=lambda m: (m.name.lower(), m.unit_id))


def render_monster_card(monster: Monster, subtitle: str = "") -> None:
    """Renders a visual monster card with SWARFARM avatar icon, resolved name, and Spanish element badge."""
    badge = get_element_badge(monster.element)
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
                    <span style="margin-left:8px;color:#9ca3af;">
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
    """Synchronizes monster_map metadata Version & Timestamp into browser localStorage."""
    version = service.version
    updated_at = int(service.updated_at or 0)
    total = service.size
    components.html(
        f"""
        <script>
        (function() {{
            try {{
                const META_KEY = "sw_optimizer_monster_map_meta_v{version}";
                const existingRaw = window.localStorage.getItem(META_KEY);
                const nowSec = Math.floor(Date.now() / 1000);
                let needsUpdate = true;
                if (existingRaw) {{
                    const parsed = JSON.parse(existingRaw);
                    if (parsed && parsed.version === {version} && (nowSec - parsed.updated_at) < {service.ttl_seconds}) {{
                        needsUpdate = false;
                    }}
                }}
                if (needsUpdate) {{
                    window.localStorage.setItem(META_KEY, JSON.stringify({{
                        version: {version},
                        updated_at: {updated_at} || nowSec,
                        count: {total}
                    }}));
                }}
            }} catch (err) {{
                console.warn("Browser storage monster cache check skipped:", err);
            }}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _init_session_state() -> None:
    if "monster_service" not in st.session_state:
        st.session_state.monster_service = MonsterDataService.get_instance()
    if "profile" not in st.session_state:
        st.session_state.profile = None
    if "is_demo_mode" not in st.session_state:
        st.session_state.is_demo_mode = False
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
    """Builds a Polars DataFrame of monsters with Spanish columns and competitive stat abbreviations."""
    filtered = filter_monsters(
        profile.monsters.values(),
        search_query=search_query,
        elements=selected_elements,
    )
    rows: list[dict[str, Any]] = []
    for m in filtered:
        rows.append(
            {
                "Avatar": m.icon_url,
                "Monstruo": m.name,
                "Elemento": get_element_badge(m.element),
                "Estrellas": f"{m.base_stars}★",
                "Nivel": m.unit_level,
                "HP Base": m.base_hp,
                "ATK Base": m.atk,
                "DEF Base": m.def_,
                "SPD Base": m.spd,
                "Runas PVE": len(m.runes),
                "Runas RTA": len(m.rta_runes),
            }
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)


def _build_runes_dataframe(profile: AccountProfile) -> pl.DataFrame:
    """Builds the Polars DataFrame for the Rune Dashboard in Spanish."""
    tbl = ES_DICT["tables"]
    rows: list[dict[str, Any]] = []
    for r in profile.runes.values():
        if r.occupied_id in profile.monsters:
            m_pve = profile.monsters[r.occupied_id]
            pve_owner = f"{m_pve.name} ({get_element_badge(m_pve.element)})"
            owner_icon = m_pve.icon_url
        else:
            pve_owner = tbl["inventory_free"]
            owner_icon = ""

        if r.rta_occupied_id in profile.monsters:
            m_rta = profile.monsters[r.rta_occupied_id]
            rta_owner = f"{m_rta.name} ({get_element_badge(m_rta.element)})"
        else:
            rta_owner = tbl["inventory_rta_free"]

        grade_label = (
            f"{r.stars}★ {tbl['ancient_rune']}"
            if r.is_ancient
            else f"{r.stars}★ {tbl['normal_rune']}"
        )

        rows.append(
            {
                "Rune ID": r.rune_id,
                "Owner Icon": owner_icon,
                "Equipada en": pve_owner,
                "Equipada PVE": pve_owner,
                "Equipada RTA": rta_owner,
                "Slot": r.slot_no,
                "Set": r.set_name,
                "Estrellas": f"{r.stars}★",
                "Grado": grade_label,
                "Nivel": f"+{r.upgrade_curr}",
                "Main Stat": f"{STAT_ID_MAP.get(r.main_stat_id, '')} +{r.main_stat_val}",
                "Innate": (
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
                "ACC%": r.get_stat_total(12),
                "RES%": r.get_stat_total(11),
                "Eficiencia (%)": calculate_rune_efficiency(r, use_grinds=True),
                "Efic. Base (%)": calculate_rune_efficiency(r, use_grinds=False),
                "Bloqueada PVE": r.rune_id in profile.locked_runes_pve,
                "Bloqueada RTA": r.rune_id in profile.locked_runes_rta,
            }
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort("Eficiencia (%)", descending=True)


def _build_artifacts_dataframe(profile: AccountProfile) -> pl.DataFrame:
    """Builds the Polars DataFrame for the Artifacts table in Spanish."""
    tbl = ES_DICT["tables"]
    pri_stat_names = {1: "HP flat", 100: "HP flat", 3: "ATK flat", 101: "ATK flat", 5: "DEF flat", 102: "DEF flat"}
    rows: list[dict[str, Any]] = []
    for a in profile.artifacts.values():
        if a.occupied_id in profile.monsters:
            m_pve = profile.monsters[a.occupied_id]
            pve_owner = f"{m_pve.name} ({get_element_badge(m_pve.element)})"
        else:
            pve_owner = tbl["inventory_free"]

        if a.rta_occupied_id in profile.monsters:
            m_rta = profile.monsters[a.rta_occupied_id]
            rta_owner = f"{m_rta.name} ({get_element_badge(m_rta.element)})"
        else:
            rta_owner = tbl["inventory_rta_free"]

        pri_name = pri_stat_names.get(a.pri_eff[0], f"ID {a.pri_eff[0]}")
        rows.append(
            {
                "ID Artefacto": a.artifact_id,
                "Equipada en": pve_owner,
                "Equipada RTA": rta_owner,
                "Slot": "Atributo (Izq.)" if a.slot == 1 else "Arquetipo (Der.)",
                "Estrellas": f"{a.natural_rank}★",
                "Nivel": f"+{a.level}",
                "Main Stat": f"{pri_name} +{a.pri_eff[1]}",
                "Substats": len(a.sec_eff),
            }
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)


def render_sidebar() -> tuple[AccountProfile | None, Literal["pve", "rta"], float, float]:
    sb = ES_DICT["sidebar"]
    nav = ES_DICT["navbar"]
    st.sidebar.title(sb["title"])
    st.sidebar.caption(sb["caption"])

    monster_service: MonsterDataService = st.session_state.monster_service

    uploaded = st.sidebar.file_uploader(
        f"📂 {sb['upload_label']}",
        type=["json"],
        key="sidebar_swex_uploader",
        help=sb["upload_help"],
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
        sb["load_demo_btn"],
        use_container_width=True,
        help=sb["load_demo_help"],
    ):
        demo_prof = load_demo_account_profile(monster_service=monster_service)
        activate_account_profile(demo_prof, is_demo=True, file_signature="demo_account")
        st.rerun()

    if st.session_state.profile is not None:
        if st.sidebar.button(
            sb["clear_account_btn"],
            use_container_width=True,
            help=sb["clear_account_help"],
        ):
            clear_account_state()
            st.rerun()

    if st.sidebar.button(
        sb["help_guide_btn"],
        use_container_width=True,
        help=sb["help_guide_help"],
    ):
        open_help_guide_dialog()

    if st.sidebar.button(
        sb["sync_bestiary_btn"],
        use_container_width=True,
        help=sb["sync_bestiary_help"],
    ):
        try:
            count = monster_service.sync_from_swarfarm(force=True)
            st.sidebar.success(f"Sincronizados {count:,} monstruos en el mapa local.")
        except Exception as exc:
            st.sidebar.warning(
                f"Modo offline activo ({monster_service.size:,} monstruos): {exc}"
            )

    profile: AccountProfile | None = st.session_state.profile

    mode_label = st.sidebar.radio(
        sb["inventory_mode_label"],
        options=[sb["mode_pve"], sb["mode_rta"]],
        index=0 if st.session_state.inventory_mode == "pve" else 1,
        help=sb["inventory_mode_help"],
    )
    mode: Literal["pve", "rta"] = "rta" if "RTA" in mode_label else "pve"
    st.session_state.inventory_mode = mode

    st.sidebar.divider()
    st.sidebar.subheader(sb["combat_bonuses_header"])
    sky_totem_pct = st.sidebar.slider(
        sb["sky_totem_label"],
        0,
        15,
        15,
        help=sb["sky_totem_help"],
    )
    leader_spd_pct = st.sidebar.selectbox(
        sb["leader_spd_label"],
        options=[0, 10, 15, 19, 21, 24, 28, 30, 33],
        index=0,
        help=sb["leader_spd_help"],
    )

    st.sidebar.divider()
    if profile is not None:
        st.sidebar.markdown(
            f"**Invocador:** `{profile.wizard_name}`  \n"
            f"**{nav['level']}:** `{profile.wizard_level}`  \n"
            f"**{nav['mana']}:** `{profile.wizard_mana:,}`  \n"
            f"**{nav['crystals']}:** `{profile.wizard_crystal:,}`  \n"
            f"**Monstruos:** `{len(profile.monsters)}`  \n"
            f"**Runas:** `{len(profile.runes)}` | **Artefactos:** `{len(profile.artifacts)}`  \n"
            f"**Bestiario O(1):** `{monster_service.size:,}` especies  \n"
            f"**Bloqueadas PVE:** `{len(profile.locked_runes_pve)}` | **RTA:** `{len(profile.locked_runes_rta)}`"
        )
    else:
        st.sidebar.caption(
            f"Bestiario listo (`{monster_service.size:,}` especies). Ninguna cuenta cargada."
        )

    return profile, mode, sky_totem_pct / 100.0, leader_spd_pct / 100.0


def render_tab_dashboard(profile: AccountProfile) -> None:
    tbl = ES_DICT["tables"]
    sub_mon, sub_runes, sub_arts = st.tabs(
        [
            f"👾 {tbl['monsters']} ({len(profile.monsters)})",
            f"💎 {tbl['runes']} ({len(profile.runes)})",
            f"🏺 {tbl['artifacts']} ({len(profile.artifacts)})",
        ]
    )

    with sub_mon:
        st.subheader(f"👾 {tbl['monsters']} y Explorador de Bestiario")
        mf1, mf2 = st.columns([2, 2])
        monster_search = mf1.text_input(
            f"🔍 {tbl['search_monster']}",
            value="",
            placeholder=tbl["search_monster"],
            key="dashboard_monster_search",
        )
        monster_elements = mf2.multiselect(
            tbl["element"],
            options=ALL_ELEMENTS,
            default=[],
            format_func=get_element_badge,
            key="dashboard_monster_elements",
        )

        monsters_df = build_monsters_dataframe(
            profile, search_query=monster_search, selected_elements=monster_elements
        )
        if monsters_df.is_empty():
            st.info("Ningún monstruo coincide con el filtro de nombre o elemento actual.")
        else:
            st.dataframe(
                monsters_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Avatar": st.column_config.ImageColumn("Avatar", width="small"),
                    "HP Base": st.column_config.NumberColumn(
                        "HP Base", help=STAT_TOOLTIPS_ES["HP"]
                    ),
                    "ATK Base": st.column_config.NumberColumn(
                        "ATK Base", help=STAT_TOOLTIPS_ES["ATK"]
                    ),
                    "DEF Base": st.column_config.NumberColumn(
                        "DEF Base", help=STAT_TOOLTIPS_ES["DEF"]
                    ),
                    "SPD Base": st.column_config.NumberColumn(
                        "SPD Base", help=STAT_TOOLTIPS_ES["SPD"]
                    ),
                },
            )

    with sub_runes:
        st.subheader(f"💎 Inventario de {tbl['runes']} (Fórmula de Eficiencia de Barion)")
        df = _build_runes_dataframe(profile)
        if df.is_empty():
            st.warning("No se encontraron runas en el perfil actual.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total de Runas", len(df))
            c2.metric(
                "Eficiencia Promedio",
                f"{df['Eficiencia (%)'].mean():.2f}%",
                help=TOOLTIPS["barion_efficiency"],
            )
            c3.metric(
                "Runas >= 100% Efic.",
                int((df["Eficiencia (%)"] >= 100.0).sum()),
                help=TOOLTIPS["barion_efficiency"],
            )
            c4.metric(
                "Runas >= 25 SPD",
                int((df["SPD"] >= 25).sum()),
                help=STAT_TOOLTIPS_ES["SPD"],
            )

            f1, f2, f3 = st.columns(3)
            all_sets = sorted(df["Set"].unique().to_list())
            selected_sets = f1.multiselect("Sets de Runas", options=all_sets, default=[])
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
                    "Owner Icon": st.column_config.ImageColumn("Monstruo", width="small"),
                    "SPD": st.column_config.NumberColumn(
                        "SPD", help=STAT_TOOLTIPS_ES["SPD"]
                    ),
                    "CR / Tasa Crít.": st.column_config.NumberColumn(
                        "CR / Tasa Crít.", help=STAT_TOOLTIPS_ES["CR"]
                    ),
                    "CD / Daño Crít.": st.column_config.NumberColumn(
                        "CD / Daño Crít.", help=STAT_TOOLTIPS_ES["CD"]
                    ),
                    "HP%": st.column_config.NumberColumn(
                        "HP%", help=STAT_TOOLTIPS_ES["HP"]
                    ),
                    "ATK%": st.column_config.NumberColumn(
                        "ATK%", help=STAT_TOOLTIPS_ES["ATK"]
                    ),
                    "DEF%": st.column_config.NumberColumn(
                        "DEF%", help=STAT_TOOLTIPS_ES["DEF"]
                    ),
                    "ACC%": st.column_config.NumberColumn(
                        "ACC%", help=STAT_TOOLTIPS_ES["ACC"]
                    ),
                    "RES%": st.column_config.NumberColumn(
                        "RES%", help=STAT_TOOLTIPS_ES["RES"]
                    ),
                    "Eficiencia (%)": st.column_config.NumberColumn(
                        "Eficiencia (%)", help=TOOLTIPS["barion_efficiency"]
                    ),
                },
            )

    with sub_arts:
        st.subheader(f"🏺 Inventario de {tbl['artifacts']}")
        arts_df = _build_artifacts_dataframe(profile)
        if arts_df.is_empty():
            st.info("Esta cuenta no contiene artefactos registrados en el archivo JSON.")
        else:
            st.dataframe(arts_df, use_container_width=True, hide_index=True)


def render_tab_optimizer(
    profile: AccountProfile,
    mode: Literal["pve", "rta"],
    sky_totem: float,
    leader_spd: float,
) -> None:
    opt_dict = ES_DICT["optimizer"]
    tbl_dict = ES_DICT["tables"]
    st.subheader(
        f"🧮 {opt_dict['panel_title']} ({'Modo RTA' if mode == 'rta' else 'Modo PVE / Normal'})"
    )

    col_left, col_right = st.columns([1, 2])
    with col_left:
        st.markdown(f"**{opt_dict['select_monster']}**")
        opt_search = st.text_input(
            f"🔍 {tbl_dict['search_monster']}",
            value="",
            placeholder=tbl_dict["search_monster"],
            key="opt_monster_search",
        )
        opt_elements = st.multiselect(
            tbl_dict["element"],
            options=ALL_ELEMENTS,
            default=[],
            format_func=get_element_badge,
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
            opt_dict["select_monster"],
            options=filtered_monsters,
            format_func=format_monster_label,
            key="opt_target_monster",
        )
        render_monster_card(selected_monster)

        set_names = [name for sid, name in sorted(SET_ID_MAP.items()) if sid != 25]
        req_set_names = st.multiselect(
            opt_dict["rune_sets"],
            options=set_names,
            default=[],
            format_func=lambda s: RUNE_SET_LABELS_ES.get(s, s),
            help=f"{TOOLTIPS['broken_sets']} {TOOLTIPS['intangible_wildcard']}",
        )
        req_set_ids = [NAME_TO_SET_ID[n.lower()] for n in req_set_names]

        st.markdown(f"**{opt_dict['main_stats_246']}**")
        stat_options = {f"{v} ({k})": k for k, v in STAT_ID_MAP.items()}
        s2_names = st.multiselect(
            opt_dict["slot2_label"],
            options=list(stat_options.keys()),
            default=["SPD (8)", "ATK% (4)", "HP% (2)", "DEF% (6)"],
        )
        s4_names = st.multiselect(
            opt_dict["slot4_label"],
            options=list(stat_options.keys()),
            default=["CDmg% (10)", "CRate% (9)", "HP% (2)", "ATK% (4)", "DEF% (6)"],
        )
        s6_names = st.multiselect(
            opt_dict["slot6_label"],
            options=list(stat_options.keys()),
            default=["ATK% (4)", "HP% (2)", "DEF% (6)", "ACC% (12)"],
        )

        st.markdown(f"**{opt_dict['min_stats_filters']}**")
        r1, r2 = st.columns(2)
        min_spd = r1.number_input(
            "SPD Mín. (Velocidad)",
            min_value=0,
            max_value=400,
            value=130,
            help=STAT_TOOLTIPS_ES["SPD"],
        )
        max_spd = r2.number_input(
            "SPD Máx. (Velocidad)",
            min_value=1,
            max_value=999,
            value=450,
            help=STAT_TOOLTIPS_ES["SPD"],
        )
        min_cr = r1.number_input(
            "CR / Tasa Crít. Mín. (%)",
            min_value=0,
            max_value=100,
            value=15,
            help=STAT_TOOLTIPS_ES["CR"],
        )
        min_acc = r2.number_input(
            "ACC Mín. (Precisión %)",
            min_value=0,
            max_value=100,
            value=0,
            help=STAT_TOOLTIPS_ES["ACC"],
        )
        min_hp = r1.number_input(
            "HP Mín. (Vida Total)",
            min_value=0,
            max_value=100000,
            value=9000,
            step=500,
            help=STAT_TOOLTIPS_ES["HP"],
        )
        min_atk = r2.number_input(
            "ATK Mín. (Ataque Total)",
            min_value=0,
            max_value=10000,
            value=500,
            step=100,
            help=STAT_TOOLTIPS_ES["ATK"],
        )

        goal_labels = {
            "damage": "Daño Promedio (ATK + CR + CD)",
            "ehp": "EHP (Vida Efectiva / Tanque)",
            "spd": "SPD (Velocidad de Combate)",
            "efficiency": "Eficiencia de Barion (%)",
            "atk": "ATK (Ataque Total)",
            "hp": "HP (Vida Total)",
            "def": "DEF (Defensa Total)",
        }
        opt_for = st.selectbox(
            opt_dict["optimization_goal"],
            options=list(goal_labels.keys()),
            format_func=lambda k: goal_labels.get(k, k),
            index=0,
            help=f"{TOOLTIPS['damage_multiplier']} | {TOOLTIPS['effective_hp']}",
        )
        include_equipped = st.checkbox(
            opt_dict["include_equipped"],
            value=True,
            help=TOOLTIPS["include_equipped_runes"],
        )
        allow_broken = st.checkbox(
            opt_dict["allow_broken_sets"],
            value=True,
            help=TOOLTIPS["broken_sets"],
        )
        sim_15 = st.checkbox(
            opt_dict["simulate_plus15"],
            value=True,
            help=TOOLTIPS["simulate_plus15"],
        )
        max_per_slot = st.slider(
            opt_dict["slot_depth"],
            8,
            35,
            18,
            help=TOOLTIPS["focus_pruning"],
        )

        run_btn = st.button(
            f"🚀 {opt_dict['calculate_builds']}",
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
                min_acc=int(min_acc),
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
            res = optimize_monster_builds(
                monster=selected_monster, available_runes=pool, constraints=cfg
            )
            st.session_state.last_opt_result = res

        opt_res = st.session_state.last_opt_result
        if opt_res is not None:
            target_mon = profile.monsters.get(opt_res.unit_id, selected_monster)
            render_monster_card(
                target_mon,
                subtitle=(
                    f"{opt_dict['results_found']}: {len(opt_res.builds)} | "
                    f"Builds evaluadas: {opt_res.evaluated_builds:,} | "
                    f"Podadas (2,4,6): {opt_res.pruned_triplets_246:,}/{opt_res.total_triplets_246:,} | "
                    f"Tiempo: {opt_res.elapsed_ms:.2f} ms"
                ),
            )
            if not opt_res.builds:
                st.warning(opt_dict["no_results_warning"])
            else:
                st.markdown(
                    f"#### ✅ {opt_dict['results_found']}: `{len(opt_res.builds)}` builds óptimas"
                )
                build_rows = []
                for b in opt_res.builds:
                    s = b.stats
                    build_rows.append(
                        {
                            "Rank": b.rank,
                            "Avatar": target_mon.icon_url,
                            "Monstruo": target_mon.name,
                            "Elemento": get_element_badge(target_mon.element),
                            "Score": b.score,
                            "Sets de Runas": (
                                ", ".join(s.active_sets)
                                if s.active_sets
                                else "Set Roto (Broken)"
                            ),
                            "Intangible ->": s.intangible_replaced_set or "-",
                            "SPD": s.combat_spd,
                            "SPD Runas": f"+{s.rune_spd}",
                            "HP": s.total_hp,
                            "ATK": s.total_atk,
                            "DEF": s.total_def,
                            "CR / Tasa Crít.": s.crate,
                            "CD / Daño Crít.": s.cdmg,
                            "ACC": s.acc,
                            "RES": s.res,
                            "EHP": s.ehp,
                            "Eficiencia (%)": s.avg_efficiency,
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
                        "SPD": st.column_config.NumberColumn(
                            "SPD", help=STAT_TOOLTIPS_ES["SPD"]
                        ),
                        "HP": st.column_config.NumberColumn(
                            "HP", help=STAT_TOOLTIPS_ES["HP"]
                        ),
                        "ATK": st.column_config.NumberColumn(
                            "ATK", help=STAT_TOOLTIPS_ES["ATK"]
                        ),
                        "DEF": st.column_config.NumberColumn(
                            "DEF", help=STAT_TOOLTIPS_ES["DEF"]
                        ),
                        "CR / Tasa Crít.": st.column_config.NumberColumn(
                            "CR / Tasa Crít.", help=STAT_TOOLTIPS_ES["CR"]
                        ),
                        "CD / Daño Crít.": st.column_config.NumberColumn(
                            "CD / Daño Crít.", help=STAT_TOOLTIPS_ES["CD"]
                        ),
                        "ACC": st.column_config.NumberColumn(
                            "ACC", help=STAT_TOOLTIPS_ES["ACC"]
                        ),
                        "RES": st.column_config.NumberColumn(
                            "RES", help=STAT_TOOLTIPS_ES["RES"]
                        ),
                        "EHP": st.column_config.NumberColumn(
                            "EHP", help=STAT_TOOLTIPS_ES["EHP"]
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
                if st.button(f"🔒 Bloquear Build #{chosen_rank} en Modo {mode.upper()}"):
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
                    st.success(
                        f"Runas bloqueadas {chosen_build.rune_ids} para {target_mon.name} ({get_element_badge(target_mon.element)}) en modo {mode.upper()}."
                    )


def render_tab_speed_tuning(
    profile: AccountProfile,
    mode: Literal["pve", "rta"],
    sky_totem: float,
    leader_spd: float,
) -> None:
    tbl_dict = ES_DICT["tables"]
    tick_val = RTA_TICK_SIZE if mode == "rta" else PVE_TICK_SIZE
    st.subheader(
        f"⏱️ Constructor de Equipos y Speed Tuning (Modo {mode.upper()} — Tick = {tick_val})"
    )

    f_col1, f_col2 = st.columns([2, 2])
    st_search = f_col1.text_input(
        f"🔍 {tbl_dict['search_monster']}",
        value="",
        placeholder=tbl_dict["search_monster"],
        key="st_monster_search",
    )
    st_elements = f_col2.multiselect(
        tbl_dict["element"],
        options=ALL_ELEMENTS,
        default=[],
        format_func=get_element_badge,
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
        "Seleccionar Monstruos del Equipo (en orden de turno deseado 1 ➔ N)",
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
                help=STAT_TOOLTIPS_ES["SPD"],
            )
            swift_on = st.checkbox(
                "Set Swift Activo",
                value=("Swift" in curr_stats.active_sets or idx == 0),
                key=f"st_swift_{idx}_{mon.unit_id}",
            )
            atb_boost = st.number_input(
                "Boost de Barra Aliada (ATB %)",
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
                "Objetivo del Rol",
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
            f"⚠️ Desfase en Speed Tuning ({mode.upper()} tick={report.tick_size}): "
            f"Secuencia actual: {' ➔ '.join(report.turn_sequence)}"
        )

    tune_rows = []
    for m in report.members:
        mon_obj = profile.monsters.get(m.unit_id)
        tune_rows.append(
            {
                "Turno Esperado": m.expected_turn_order,
                "Avatar": mon_obj.icon_url if mon_obj else "",
                "Monstruo": m.name,
                "Elemento": get_element_badge(mon_obj.element) if mon_obj else "❓ Desconocido",
                "SPD Combate Actual": m.combat_spd,
                "Tick 1er Turno": m.first_turn_tick,
                "Turno Real": m.actual_turn_order,
                "SPD Combate Mín. Req.": m.min_combat_spd_required,
                "SPD Runas Mín. Req.": f"+{m.min_rune_spd_required}",
                "Estado": "✅ Sincronizado" if m.is_tuned else "❌ Cortado / Fuera de Orden",
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
        f"⚡ Calcular Builds y Bloquear Equipo Completo en Orden ({mode.upper()})",
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
        st.markdown("#### Resultados encontrados (Optimización Secuencial de Equipo)")
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
                        "Elemento": get_element_badge(mon_obj.element) if mon_obj else "❓ Desconocido",
                        "Sets de Runas": ", ".join(s.active_sets) if s.active_sets else "Set Roto (Broken)",
                        "SPD": s.combat_spd,
                        "SPD Runas": f"+{s.rune_spd}",
                        "HP": s.total_hp,
                        "ATK": s.total_atk,
                        "CR / Tasa Crít.": s.crate,
                        "CD / Daño Crít.": s.cdmg,
                        "ACC": s.acc,
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
        if st.button("🔓 Desbloquear Todas las Runas PVE"):
            profile.locked_runes_pve.clear()
            st.session_state.locked_builds_pve.clear()
            st.rerun()

        if st.session_state.locked_builds_pve:
            for uid, b in list(st.session_state.locked_builds_pve.items()):
                mon = profile.monsters.get(uid)
                if mon:
                    render_monster_card(
                        mon,
                        subtitle=(
                            f"Sets: {', '.join(b.stats.active_sets) or 'Set Roto (Broken)'} | "
                            f"SPD Combate: {b.stats.combat_spd} | "
                            f"Runas: {b.rune_ids}"
                        ),
                    )
        elif profile.locked_runes_pve:
            st.write("IDs de Runas Bloqueadas (PVE):", sorted(profile.locked_runes_pve))
        else:
            st.caption("No hay runas ni builds bloqueadas actualmente en modo PVE.")

    with col_rta:
        st.markdown(
            f"### Modo RTA (World Arena) — `{len(profile.locked_runes_rta)}` runas bloqueadas"
        )
        if st.button("🔓 Desbloquear Todas las Runas RTA"):
            profile.locked_runes_rta.clear()
            st.session_state.locked_builds_rta.clear()
            st.rerun()

        if st.session_state.locked_builds_rta:
            for uid, b in list(st.session_state.locked_builds_rta.items()):
                mon = profile.monsters.get(uid)
                if mon:
                    render_monster_card(
                        mon,
                        subtitle=(
                            f"Sets: {', '.join(b.stats.active_sets) or 'Set Roto (Broken)'} | "
                            f"SPD Combate: {b.stats.combat_spd} | "
                            f"Runas: {b.rune_ids}"
                        ),
                    )
        elif profile.locked_runes_rta:
            st.write("IDs de Runas Bloqueadas (RTA):", sorted(profile.locked_runes_rta))
        else:
            st.caption("No hay runas ni builds bloqueadas actualmente en modo RTA.")


def main() -> None:
    st.set_page_config(
        page_title=ES_DICT["app"]["page_title"],
        page_icon="⚡",
        layout="wide",
    )
    _init_session_state()
    inject_browser_monster_cache(st.session_state.monster_service)
    profile, mode, sky_totem, leader_spd = render_sidebar()

    render_top_navbar(profile, is_demo_mode=bool(st.session_state.get("is_demo_mode", False)))
    st.divider()

    if profile is None:
        render_empty_state_hero(st.session_state.monster_service)
        return

    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "📊 Monstruos, Runas y Artefactos",
            "🧮 Optimizador de Builds",
            "⏱️ Speed Tuning (PVE / RTA)",
            "🔒 Builds Bloqueadas",
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
