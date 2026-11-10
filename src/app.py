"""Streamlit Web UI for SW-OptiPy featuring Onboarding Empty State, Demo Mode, HelpGuideModal, and O(1) Bestiary."""

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
from src.models import (
    AccountProfile,
    Monster,
    NAME_TO_SET_ID,
    SET_ID_MAP,
    STAT_ID_MAP,
)
from src.monster_data_service import (
    ELEMENT_BADGE_MAP,
    MonsterDataService,
)
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
    render_empty_state_hero,
    render_top_navbar,
)

ALL_ELEMENTS: list[str] = ["Water", "Fire", "Wind", "Light", "Dark"]


def get_element_badge(element: str) -> str:
    """Returns a formatted Element badge (e.g., '🔥 Fire')."""
    return ELEMENT_BADGE_MAP.get(element, f"❓ {element}")


def format_monster_label(monster: Monster) -> str:
    """Formats a monster option label with resolved Name, Element badge, and Stars."""
    badge = get_element_badge(monster.element)
    stars = f"{monster.base_stars}★"
    return f"{monster.name} — {badge} ({stars})"


def filter_monsters(
    monsters: Iterable[Monster],
    search_query: str = "",
    elements: Iterable[str] | None = None,
) -> list[Monster]:
    """Filters and sorts monsters by name substring (or ID) and selected elements."""
    query = search_query.strip().lower()
    allowed_elements = {e.capitalize() for e in elements} if elements else set()

    matched: list[Monster] = []
    for monster in monsters:
        if allowed_elements and monster.element.capitalize() not in allowed_elements:
            continue
        if query:
            searchable = f"{monster.name.lower()} {monster.element.lower()} {monster.unit_master_id}"
            if query not in searchable:
                continue
        matched.append(monster)

    return sorted(matched, key=lambda m: (m.name.lower(), m.unit_id))


def render_monster_card(monster: Monster, subtitle: str = "") -> None:
    """Renders a visual monster card with SWARFARM avatar icon, resolved name, and element badge."""
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
    """Builds a Polars DataFrame of monsters with Avatar URL, resolved Name, Element badge, and Base Stats."""
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
                "Monster": m.name,
                "Element": get_element_badge(m.element),
                "Stars": f"{m.base_stars}★",
                "Level": m.unit_level,
                "Base HP": m.base_hp,
                "Base ATK": m.atk,
                "Base DEF": m.def_,
                "Base SPD": m.spd,
                "PVE Runes": len(m.runes),
                "RTA Runes": len(m.rta_runes),
            }
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows)


def _build_runes_dataframe(profile: AccountProfile) -> pl.DataFrame:
    """Builds the Polars DataFrame for the Rune Dashboard with resolved Monster names and Element badges."""
    rows: list[dict[str, Any]] = []
    for r in profile.runes.values():
        if r.occupied_id in profile.monsters:
            m_pve = profile.monsters[r.occupied_id]
            pve_owner = f"{m_pve.name} ({get_element_badge(m_pve.element)})"
            owner_icon = m_pve.icon_url
        else:
            pve_owner = "Inventory"
            owner_icon = ""

        if r.rta_occupied_id in profile.monsters:
            m_rta = profile.monsters[r.rta_occupied_id]
            rta_owner = f"{m_rta.name} ({get_element_badge(m_rta.element)})"
        else:
            rta_owner = "RTA Inventory"

        rows.append(
            {
                "Rune ID": r.rune_id,
                "Owner Icon": owner_icon,
                "Equipada PVE": pve_owner,
                "Equipada RTA": rta_owner,
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
                "Bloqueada PVE": r.rune_id in profile.locked_runes_pve,
                "Bloqueada RTA": r.rune_id in profile.locked_runes_rta,
            }
        )
    if not rows:
        return pl.DataFrame()
    return pl.DataFrame(rows).sort("Eficiencia (%)", descending=True)


def render_sidebar() -> tuple[AccountProfile | None, Literal["pve", "rta"], float, float]:
    st.sidebar.title("⚡ SW-OptiPy")
    st.sidebar.caption("Rune & Speed Tuning Optimizer (PVE / Siege / RTA)")

    monster_service: MonsterDataService = st.session_state.monster_service

    uploaded = st.sidebar.file_uploader(
        "Import SWEX JSON",
        type=["json"],
        key="sidebar_swex_uploader",
        help="Upload the .json file exported by Summoners War Exporter (SWEX). Zero N+1 API calls.",
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
                st.sidebar.success(f"Loaded account: {parsed.wizard_name}")
            except Exception as exc:
                st.sidebar.error(f"Invalid SWEX JSON file: {exc}")

    if st.sidebar.button(
        "🎮 Load Demo Account",
        use_container_width=True,
        help="Load src/data/demo_account.json (Demo_Summoner) into state.",
    ):
        demo_prof = load_demo_account_profile(monster_service=monster_service)
        activate_account_profile(demo_prof, is_demo=True, file_signature="demo_account")
        st.rerun()

    if st.sidebar.button(
        "🔄 Refresh SWARFARM Bestiary Map",
        use_container_width=True,
        help="Sync all monsters from SWARFARM v2 API into src/data/monster_map.json.",
    ):
        try:
            count = monster_service.sync_from_swarfarm(force=True)
            st.sidebar.success(f"Synced {count:,} monsters into local map.")
        except Exception as exc:
            st.sidebar.warning(
                f"Offline fallback active ({monster_service.size:,} monsters): {exc}"
            )

    profile: AccountProfile | None = st.session_state.profile

    mode_label = st.sidebar.radio(
        "Active Inventory Mode",
        options=["Normal Mode (PVE / Siege / Arena)", "RTA Mode (World Arena)"],
        index=0 if st.session_state.inventory_mode == "pve" else 1,
        help="Switch between PVE and RTA equipment & rune lock pools independently.",
    )
    mode: Literal["pve", "rta"] = "rta" if "RTA" in mode_label else "pve"
    st.session_state.inventory_mode = mode

    st.sidebar.divider()
    st.sidebar.subheader("Global Combat Bonuses")
    sky_totem_pct = st.sidebar.slider(
        "Sky Totem SPD (%)",
        0,
        15,
        15,
        help="In-game Sky Tribe Totem bonus (+15% Base SPD at max level).",
    )
    leader_spd_pct = st.sidebar.selectbox(
        "SPD Leader Skill (%)",
        options=[0, 10, 15, 19, 21, 24, 28, 30, 33],
        index=0,
        help="Team Leader Skill speed bonus percentage applied to Base SPD.",
    )

    st.sidebar.divider()
    if profile is not None:
        st.sidebar.markdown(
            f"**Summoner:** `{profile.wizard_name}`  \n"
            f"**Monsters:** `{len(profile.monsters)}`  \n"
            f"**Total Runes:** `{len(profile.runes)}`  \n"
            f"**Bestiary Map (O(1)):** `{monster_service.size:,}` species  \n"
            f"**Locked PVE:** `{len(profile.locked_runes_pve)}` | **RTA:** `{len(profile.locked_runes_rta)}`"
        )
    else:
        st.sidebar.caption(
            f"Bestiary Map ready (`{monster_service.size:,}` species). No account loaded."
        )

    return profile, mode, sky_totem_pct / 100.0, leader_spd_pct / 100.0


def render_tab_dashboard(profile: AccountProfile) -> None:
    st.subheader("👾 Monster Box & Bestiary Explorer")
    mf1, mf2 = st.columns([2, 2])
    monster_search = mf1.text_input(
        "🔍 Search Monster by Name",
        value="",
        placeholder="e.g. Lapis, Abigail, Icaru, Spectra, Demo_Homu...",
        key="dashboard_monster_search",
    )
    monster_elements = mf2.multiselect(
        "Filter by Element",
        options=ALL_ELEMENTS,
        default=[],
        format_func=get_element_badge,
        key="dashboard_monster_elements",
    )

    monsters_df = build_monsters_dataframe(
        profile, search_query=monster_search, selected_elements=monster_elements
    )
    if monsters_df.is_empty():
        st.info("No monsters match the current name/element filter.")
    else:
        st.dataframe(
            monsters_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Avatar": st.column_config.ImageColumn("Avatar", width="small"),
                "Base HP": st.column_config.NumberColumn(
                    "Base HP", help="Calculated automatically as CON * 15."
                ),
            },
        )

    st.divider()
    st.subheader("📊 Rune Inventory Dashboard (Barion Efficiency Formula)")
    df = _build_runes_dataframe(profile)
    if df.is_empty():
        st.warning("No runes found in the current profile.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Runes", len(df))
    c2.metric(
        "Mean Efficiency",
        f"{df['Eficiencia (%)'].mean():.2f}%",
        help=TOOLTIPS["barion_efficiency"],
    )
    c3.metric(
        "Runes >= 100% Eff.",
        int((df["Eficiencia (%)"] >= 100.0).sum()),
        help=TOOLTIPS["barion_efficiency"],
    )
    c4.metric("Runes >= 25 SPD", int((df["SPD"] >= 25).sum()))

    f1, f2, f3 = st.columns(3)
    all_sets = sorted(df["Set"].unique().to_list())
    selected_sets = f1.multiselect("Filter by Set", options=all_sets, default=[])
    selected_slots = f2.multiselect(
        "Filter by Slot", options=[1, 2, 3, 4, 5, 6], default=[]
    )
    min_eff = f3.slider(
        "Minimum Efficiency (%)",
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
            "Owner Icon": st.column_config.ImageColumn("Owner", width="small"),
            "Eficiencia (%)": st.column_config.NumberColumn(
                "Eficiencia (%)", help=TOOLTIPS["barion_efficiency"]
            ),
        },
    )


def render_tab_optimizer(
    profile: AccountProfile,
    mode: Literal["pve", "rta"],
    sky_totem: float,
    leader_spd: float,
) -> None:
    st.subheader(
        f"🧮 Branch & Bound Combinatorial Optimizer ({'RTA' if mode == 'rta' else 'PVE / Normal'})"
    )

    col_left, col_right = st.columns([1, 2])
    with col_left:
        st.markdown("**Filter & Select Monster**")
        opt_search = st.text_input(
            "🔍 Search Monster by Name",
            value="",
            placeholder="Type monster name...",
            key="opt_monster_search",
        )
        opt_elements = st.multiselect(
            "Element Filter",
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
            st.warning("No monsters match your search/element filter.")
            return

        selected_monster = st.selectbox(
            "Target Monster",
            options=filtered_monsters,
            format_func=format_monster_label,
            key="opt_target_monster",
        )
        render_monster_card(selected_monster)

        set_names = [name for sid, name in sorted(SET_ID_MAP.items()) if sid != 25]
        req_set_names = st.multiselect(
            "Required Sets (Broken Sets allowed on remaining slots)",
            options=set_names,
            default=[],
            help=f"{TOOLTIPS['broken_sets']} {TOOLTIPS['intangible_wildcard']}",
        )
        req_set_ids = [NAME_TO_SET_ID[n.lower()] for n in req_set_names]

        stat_options = {f"{v} ({k})": k for k, v in STAT_ID_MAP.items()}
        s2_names = st.multiselect(
            "Slot 2 Main Stat",
            options=list(stat_options.keys()),
            default=["SPD (8)", "ATK% (4)", "HP% (2)", "DEF% (6)"],
        )
        s4_names = st.multiselect(
            "Slot 4 Main Stat",
            options=list(stat_options.keys()),
            default=["CDmg% (10)", "CRate% (9)", "HP% (2)", "ATK% (4)", "DEF% (6)"],
        )
        s6_names = st.multiselect(
            "Slot 6 Main Stat",
            options=list(stat_options.keys()),
            default=["ATK% (4)", "HP% (2)", "DEF% (6)", "ACC% (12)"],
        )

        st.markdown("**Minimum Constraints (Branch & Bound)**")
        r1, r2 = st.columns(2)
        min_spd = r1.number_input("Min Combat SPD", min_value=0, max_value=400, value=130)
        max_spd = r2.number_input("Max Combat SPD", min_value=1, max_value=999, value=450)
        min_cr = r1.number_input("Min CRate (%)", min_value=0, max_value=100, value=15)
        min_acc = r2.number_input("Min ACC (%)", min_value=0, max_value=100, value=0)
        min_hp = r1.number_input(
            "Min Total HP", min_value=0, max_value=100000, value=9000, step=500
        )
        min_atk = r2.number_input(
            "Min Total ATK", min_value=0, max_value=10000, value=500, step=100
        )

        opt_for = st.selectbox(
            "Optimization Goal (Damage Multiplier / Effective HP / SPD)",
            options=["damage", "ehp", "spd", "efficiency", "atk", "hp", "def"],
            index=0,
            help=f"{TOOLTIPS['damage_multiplier']} | {TOOLTIPS['effective_hp']}",
        )
        include_equipped = st.checkbox(
            "Include Equipped Runes",
            value=True,
            help=TOOLTIPS["include_equipped_runes"],
        )
        sim_15 = st.checkbox(
            "Simulate +15 Runes (6★ Tables)",
            value=True,
            help=TOOLTIPS["simulate_plus15"],
        )
        max_per_slot = st.slider(
            "Slot Depth (Focus Pruning)",
            8,
            35,
            18,
            help=TOOLTIPS["focus_pruning"],
        )

        run_btn = st.button(
            "🚀 Run Optimization (Numba JIT)",
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
                    f"Evaluated: {opt_res.evaluated_builds:,} builds | "
                    f"Pruned (2,4,6): {opt_res.pruned_triplets_246:,}/{opt_res.total_triplets_246:,} | "
                    f"Elapsed: {opt_res.elapsed_ms:.2f} ms"
                ),
            )
            if not opt_res.builds:
                st.warning(
                    "No rune combination satisfied all constraints. Lower minimum thresholds or enable 'Include Equipped Runes'."
                )
            else:
                build_rows = []
                for b in opt_res.builds:
                    s = b.stats
                    build_rows.append(
                        {
                            "Rank": b.rank,
                            "Avatar": target_mon.icon_url,
                            "Monster": target_mon.name,
                            "Element": get_element_badge(target_mon.element),
                            "Score": b.score,
                            "Sets": ", ".join(s.active_sets) if s.active_sets else "Broken Set",
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
                            "Mean Eff. (%)": s.avg_efficiency,
                            "Runes (Slots 1-6)": str(b.rune_ids),
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
                        "Sets": st.column_config.TextColumn(
                            "Sets", help=TOOLTIPS["broken_sets"]
                        ),
                    },
                )

                chosen_rank = st.selectbox(
                    "Select Build Rank to Lock Runes",
                    options=[b.rank for b in opt_res.builds],
                    index=0,
                )
                if st.button(f"🔒 Lock Build #{chosen_rank} in {mode.upper()} Mode"):
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
                        f"Locked runes {chosen_build.rune_ids} for {target_mon.name} ({get_element_badge(target_mon.element)}) in {mode.upper()} mode."
                    )


def render_tab_speed_tuning(
    profile: AccountProfile,
    mode: Literal["pve", "rta"],
    sky_totem: float,
    leader_spd: float,
) -> None:
    tick_val = RTA_TICK_SIZE if mode == "rta" else PVE_TICK_SIZE
    st.subheader(
        f"⏱️ Team Builder & Speed Tuning ({mode.upper()} Mode — Tick = {tick_val})"
    )

    f_col1, f_col2 = st.columns([2, 2])
    st_search = f_col1.text_input(
        "🔍 Filter Available Monsters by Name",
        value="",
        placeholder="Search monster name...",
        key="st_monster_search",
    )
    st_elements = f_col2.multiselect(
        "Filter by Element",
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
        "Select Team Monsters (in desired turn order 1 ➔ N)",
        options=selectable_monsters,
        default=default_team[:3],
        format_func=format_monster_label,
        max_selections=6,
    )

    if not selected_team:
        st.info("Select at least 2 monsters to simulate and optimize Speed Tuning.")
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
            render_monster_card(mon, subtitle=f"Turn Slot #{idx + 1}")
            r_spd = st.number_input(
                f"Rune SPD (#{idx + 1})",
                min_value=0,
                max_value=260,
                value=curr_stats.rune_spd if curr_stats.rune_spd > 0 else 120 - idx * 15,
                key=f"st_rspd_{idx}_{mon.unit_id}",
            )
            swift_on = st.checkbox(
                "Swift Set Active",
                value=("Swift" in curr_stats.active_sets or idx == 0),
                key=f"st_swift_{idx}_{mon.unit_id}",
            )
            atb_boost = st.number_input(
                "Ally ATB Boost (%)",
                min_value=0.0,
                max_value=100.0,
                value=30.0 if idx == 0 and "Bernard" in mon.name else 0.0,
                step=5.0,
                key=f"st_boost_{idx}_{mon.unit_id}",
            )
            spd_buff = st.checkbox(
                "Applies SPD Buff (+30%)",
                value=(idx == 0 and "Bernard" in mon.name),
                key=f"st_spdbuff_{idx}_{mon.unit_id}",
            )
            role_goal = st.selectbox(
                "Optimizer Goal",
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
            f"✅ Valid Speed Tuning ({mode.upper()} tick={report.tick_size}): "
            f"Turn sequence: {' ➔ '.join(report.turn_sequence)}"
        )
    else:
        st.error(
            f"⚠️ Speed Tuning Mismatch ({mode.upper()} tick={report.tick_size}): "
            f"Actual sequence: {' ➔ '.join(report.turn_sequence)}"
        )

    tune_rows = []
    for m in report.members:
        mon_obj = profile.monsters.get(m.unit_id)
        tune_rows.append(
            {
                "Expected Turn": m.expected_turn_order,
                "Avatar": mon_obj.icon_url if mon_obj else "",
                "Monster": m.name,
                "Element": get_element_badge(mon_obj.element) if mon_obj else "❓ Unknown",
                "Current Combat SPD": m.combat_spd,
                "1st Turn Tick": m.first_turn_tick,
                "Actual Turn": m.actual_turn_order,
                "Min Combat SPD Req.": m.min_combat_spd_required,
                "Min Rune SPD Req.": f"+{m.min_rune_spd_required}",
                "Status": "✅ Tuned" if m.is_tuned else "❌ Cut / Out of Order",
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
        f"⚡ Optimize & Lock Full Team in Turn Order ({mode.upper()})",
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
        st.markdown("#### Sequential Team Optimization Results")
        summary_rows = []
        for idx, res in enumerate(st.session_state.last_team_opt_results):
            if res.builds:
                b = res.builds[0]
                s = b.stats
                mon_obj = profile.monsters.get(res.unit_id)
                summary_rows.append(
                    {
                        "Turn #": idx + 1,
                        "Avatar": mon_obj.icon_url if mon_obj else "",
                        "Monster": res.monster_name,
                        "Element": get_element_badge(mon_obj.element) if mon_obj else "❓ Unknown",
                        "Active Sets": ", ".join(s.active_sets) if s.active_sets else "Broken Set",
                        "Combat SPD": s.combat_spd,
                        "Rune SPD": f"+{s.rune_spd}",
                        "Total HP": s.total_hp,
                        "Total ATK": s.total_atk,
                        "CRate%": s.crate,
                        "CDmg%": s.cdmg,
                        "ACC%": s.acc,
                        "Assigned Runes": str(b.rune_ids),
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
    st.subheader("🔒 Locked Runes & Builds Manager (Independent PVE vs RTA)")

    col_pve, col_rta = st.columns(2)
    with col_pve:
        st.markdown(
            f"### Normal Mode (PVE / Siege) — `{len(profile.locked_runes_pve)}` locked runes"
        )
        if st.button("🔓 Unlock All PVE Runes"):
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
                            f"Sets: {', '.join(b.stats.active_sets) or 'Broken Set'} | "
                            f"Combat SPD: {b.stats.combat_spd} | "
                            f"Runes: {b.rune_ids}"
                        ),
                    )
        elif profile.locked_runes_pve:
            st.write("Locked Rune IDs:", sorted(profile.locked_runes_pve))
        else:
            st.caption("No runes or builds currently locked in PVE mode.")

    with col_rta:
        st.markdown(
            f"### RTA Mode (World Arena) — `{len(profile.locked_runes_rta)}` locked runes"
        )
        if st.button("🔓 Unlock All RTA Runes"):
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
                            f"Sets: {', '.join(b.stats.active_sets) or 'Broken Set'} | "
                            f"Combat SPD: {b.stats.combat_spd} | "
                            f"Runes: {b.rune_ids}"
                        ),
                    )
        elif profile.locked_runes_rta:
            st.write("Locked Rune IDs:", sorted(profile.locked_runes_rta))
        else:
            st.caption("No runes or builds currently locked in RTA mode.")


def main() -> None:
    st.set_page_config(
        page_title="SW-OptiPy | Summoners War Optimizer",
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
            "📊 Monster Box & Rune Dashboard",
            "🧮 General / PVE Optimizer",
            "⏱️ RTA Builder & Speed Tuning",
            "🔒 Locked Builds Manager",
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
