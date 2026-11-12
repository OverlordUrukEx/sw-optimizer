"""Modular UI components in Spanish (es-LA / es) for Onboarding Empty State, Demo Account Loader, Tooltips, and HelpGuideModal."""

from __future__ import annotations

import hashlib
from pathlib import Path

import streamlit as st

from src.i18n import (
    ES_DICT,
    HELP_STEP_1_SWEX_MD,
    HELP_STEP_2_STATS_MD,
    HELP_STEP_3_OPTIMIZER_MD,
    STAT_TOOLTIPS_ES,
    TOOLTIPS_ES,
)
from src.models import AccountProfile
from src.monster_data_service import MonsterDataService
from src.parser import parse_swex_json

DEMO_ACCOUNT_PATH = Path(__file__).resolve().parent / "data" / "demo_account.json"

# Centralized technical UI tooltips in Spanish (imported from src.i18n)
TOOLTIPS: dict[str, str] = TOOLTIPS_ES


class HelpGuideModal:
    """
    Structured 3-step User Help & Documentation guide in Spanish covering:
    1) Exportación con SWEX
    2) Mapeo de Estadísticas (`CON * 15`), Runas Antiguas (Ancient) y Grinds (`base + grind`)
    3) Uso del Optimizador de Builds y Speed Tuning
    """

    STEP_1_SWEX_MD = HELP_STEP_1_SWEX_MD
    STEP_2_STATS_MD = HELP_STEP_2_STATS_MD
    STEP_3_OPTIMIZER_MD = HELP_STEP_3_OPTIMIZER_MD

    @classmethod
    def render_body(cls) -> None:
        """Renders the tabbed 3-step documentation content in Spanish."""
        tab1, tab2, tab3 = st.tabs(
            [
                "1️⃣ Exportación con SWEX",
                "2️⃣ Estadísticas, Runas Antiguas y Grinds",
                "3️⃣ Uso del Optimizador",
            ]
        )
        with tab1:
            st.markdown(cls.STEP_1_SWEX_MD)
        with tab2:
            st.markdown(cls.STEP_2_STATS_MD)
        with tab3:
            st.markdown(cls.STEP_3_OPTIMIZER_MD)

        st.divider()
        st.markdown("#### 💡 Glosario Rápido de Estadísticas y Términos Competitivos")
        for stat_abbr, stat_desc in STAT_TOOLTIPS_ES.items():
            st.markdown(f"- **{stat_abbr}:** {stat_desc}")
        for key, label in [
            ("damage_multiplier", "Multiplicador de Daño"),
            ("include_equipped_runes", "Incluir runas equipadas"),
            ("broken_sets", "Permitir Sets Rotos (Broken)"),
            ("intangible_wildcard", "Runa Comodín Intangible"),
        ]:
            st.markdown(f"- **{label}:** {TOOLTIPS[key]}")


@st.dialog("📖 Guía de Uso — SW-OptiPy", width="large")
def open_help_guide_dialog() -> None:
    """Opens the Streamlit modal dialog containing the Spanish HelpGuideModal content."""
    HelpGuideModal.render_body()


def load_demo_account_profile(
    monster_service: MonsterDataService | None = None,
    demo_path: Path = DEMO_ACCOUNT_PATH,
) -> AccountProfile:
    """Loads `src/data/demo_account.json` into an AccountProfile."""
    service = monster_service or MonsterDataService.get_instance()
    if not demo_path.exists():
        from scripts.generate_demo_account import generate_demo_account_file

        generate_demo_account_file(output_path=demo_path)
    return parse_swex_json(demo_path, bestiary=service, fetch_remote_bestiary=False)


def activate_account_profile(
    profile: AccountProfile,
    is_demo: bool = False,
    file_signature: str = "demo",
) -> None:
    """Stores the active AccountProfile in Streamlit session_state and resets build caches."""
    st.session_state.profile = profile
    st.session_state.is_demo_mode = is_demo
    st.session_state.loaded_file_sig = file_signature
    st.session_state.last_opt_result = None
    st.session_state.last_team_opt_results = None
    st.session_state.locked_builds_pve = {}
    st.session_state.locked_builds_rta = {}


def clear_account_state() -> None:
    """Clears the currently loaded account from session_state to return to the Onboarding Hero."""
    st.session_state.profile = None
    st.session_state.is_demo_mode = False
    st.session_state.loaded_file_sig = None
    st.session_state.last_opt_result = None
    st.session_state.last_team_opt_results = None
    st.session_state.locked_builds_pve = {}
    st.session_state.locked_builds_rta = {}


def render_top_navbar(
    profile: AccountProfile | None,
    is_demo_mode: bool = False,
) -> None:
    """
    Renders the persistent top navigation bar in Spanish featuring:
    - App branding (`SW-OptiPy`)
    - Active `wizard_name` badge and account resources (`Nivel`, `Maná`, `Cristales`)
    - Quick action buttons: `Probar Cuenta Demo` (when empty), `Cambiar Cuenta / Limpiar`, and `Guía de Uso`
    """
    nav_dict = ES_DICT["navbar"]
    app_dict = ES_DICT["app"]
    nav_cols = st.columns([3.0, 3.2, 1.5, 1.3])

    with nav_cols[0]:
        st.markdown(
            f"<div style='font-size:1.35rem;font-weight:800;letter-spacing:-0.02em;'>"
            f"{app_dict['title']} <span style='font-size:0.85rem;font-weight:500;color:#9ca3af;'>"
            f"| {app_dict['subtitle']}</span></div>",
            unsafe_allow_html=True,
        )

    with nav_cols[1]:
        if profile is not None:
            badge_bg = (
                "rgba(245, 158, 11, 0.18)"
                if is_demo_mode
                else "rgba(16, 185, 129, 0.18)"
            )
            badge_border = "#f59e0b" if is_demo_mode else "#10b981"
            mode_tag = (
                nav_dict["demo_badge"] if is_demo_mode else nav_dict["active_badge"]
            )
            st.markdown(
                f"<div style='display:inline-flex;flex-wrap:wrap;align-items:center;gap:8px;padding:6px 12px;"
                f"border-radius:999px;background:{badge_bg};border:1px solid {badge_border};"
                f"font-size:0.83rem;font-weight:600;'>"
                f"<span>{mode_tag}:</span> <code style='color:#fff;'>{profile.wizard_name}</code> "
                f"<span style='color:#e5e7eb;'>· {nav_dict['level']}: <b>{profile.wizard_level}</b></span> "
                f"<span style='color:#60a5fa;'>· {nav_dict['mana']}: <b>{profile.wizard_mana:,}</b></span> "
                f"<span style='color:#f472b6;'>· {nav_dict['crystals']}: <b>{profile.wizard_crystal:,}</b></span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='padding:6px 12px;color:#9ca3af;font-size:0.85rem;'>"
                f"{nav_dict['no_account']}"
                f"</div>",
                unsafe_allow_html=True,
            )

    with nav_cols[2]:
        if profile is not None:
            if st.button(
                f"🔄 {nav_dict['switch_or_clear']}",
                use_container_width=True,
                help="Descarga la cuenta actual de la memoria y regresa a la pantalla inicial.",
            ):
                clear_account_state()
                st.rerun()
        else:
            if st.button(
                f"🎮 {nav_dict['try_demo']}",
                use_container_width=True,
                key="navbar_try_demo_btn",
                help="Carga inmediatamente la cuenta de demostración sanitizada (Demo_Summoner).",
            ):
                demo_prof = load_demo_account_profile()
                activate_account_profile(
                    demo_prof, is_demo=True, file_signature="demo_account"
                )
                st.rerun()

    with nav_cols[3]:
        if st.button(
            f"📖 {nav_dict['help_guide']}",
            use_container_width=True,
            help="Abre la guía paso a paso sobre exportación con SWEX, Runas Antiguas/Grinds y uso del Optimizador.",
        ):
            open_help_guide_dialog()

    if is_demo_mode and profile is not None:
        st.info(
            nav_dict["demo_banner"].format(
                wizard_name=profile.wizard_name,
                monsters=len(profile.monsters),
                runes=len(profile.runes),
            )
        )


def render_empty_state_hero(monster_service: MonsterDataService) -> None:
    """
    Renders the interactive Onboarding Hero / Empty State in Spanish when no account JSON is loaded:
    - Primary Drag & Drop JSON Upload Zone (`Cargar JSON`)
    - Prominent `Probar Cuenta Demo` CTA button
    - Quick 3-step feature highlights
    """
    ob = ES_DICT["onboarding"]
    st.markdown(
        f"""
        <div style="text-align:center;padding:28px 20px 18px 20px;border-radius:16px;
                    background:linear-gradient(135deg, rgba(30,41,59,0.85), rgba(15,23,42,0.92));
                    border:1px solid rgba(240,185,11,0.3);margin-bottom:22px;">
            <h1 style="margin:0;font-size:2.1rem;color:#f8fafc;">
                {ob['welcome_title']}
            </h1>
            <p style="font-size:1.05rem;color:#cbd5e1;max-width:760px;margin:10px auto 0 auto;">
                {ob['welcome_subtitle']}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_upload, col_demo = st.columns([1.4, 1.0], gap="large")

    with col_upload:
        st.markdown(f"### {ob['upload_section_title']}")
        st.caption(ob["upload_section_caption"])
        uploaded_file = st.file_uploader(
            ob["upload_dropzone_label"],
            type=["json"],
            key="hero_swex_uploader",
            help=ob["upload_dropzone_help"],
        )
        if uploaded_file is not None:
            raw_bytes = uploaded_file.getvalue()
            sig = hashlib.sha256(raw_bytes).hexdigest()
            try:
                parsed_profile = parse_swex_json(
                    raw_bytes, bestiary=monster_service, fetch_remote_bestiary=False
                )
                activate_account_profile(
                    parsed_profile, is_demo=False, file_signature=sig
                )
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo procesar el archivo JSON de SWEX: {exc}")

    with col_demo:
        st.markdown(f"### {ob['demo_section_title']}")
        st.caption(ob["demo_section_caption"])
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        if st.button(
            f"{ob['try_demo_cta']} (Demo_Summoner)",
            type="primary",
            use_container_width=True,
            help=ob["try_demo_help"],
        ):
            demo_profile = load_demo_account_profile(monster_service=monster_service)
            activate_account_profile(
                demo_profile, is_demo=True, file_signature="demo_account"
            )
            st.rerun()

        if st.button(
            ob["open_guide_cta"],
            use_container_width=True,
        ):
            open_help_guide_dialog()

    st.divider()
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown(f"**{ob['feature_1_title']}**  \n{ob['feature_1_desc']}")
    with s2:
        st.markdown(f"**{ob['feature_2_title']}**  \n{ob['feature_2_desc']}")
    with s3:
        st.markdown(f"**{ob['feature_3_title']}**  \n{ob['feature_3_desc']}")
