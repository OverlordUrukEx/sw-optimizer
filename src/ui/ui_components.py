"""Modular UI components localized in Spanish (es-LA / es) for Onboarding, Demo Loader, Tooltips, and HelpGuideModal."""

from __future__ import annotations

import hashlib
from pathlib import Path

import streamlit as st

from src.domain.models import AccountProfile
from src.i18n import ES_LOCALE, TOOLTIPS_ES
from src.services.account_storage_service import AccountStorageService
from src.services.monster_data_service import MonsterDataService
from src.services.parser import parse_swex_json

DEMO_ACCOUNT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "demo_account.json"
)

# Export centralized Spanish tooltips dictionary
TOOLTIPS: dict[str, str] = TOOLTIPS_ES


class HelpGuideModal:
    """
    Structured 3-step User Help & Documentation guide in Spanish covering SWEX data extraction,
    Summoners War domain math (CON * 15, Grinds, Ancient Runes), and running optimizations.
    """

    STEP_1_SWEX_MD: str = ES_LOCALE["help_modal"]["step_1_markdown"]
    STEP_2_STATS_MD: str = ES_LOCALE["help_modal"]["step_2_markdown"]
    STEP_3_OPTIMIZER_MD: str = ES_LOCALE["help_modal"]["step_3_markdown"]

    @classmethod
    def render_body(cls) -> None:
        """Renders the tabbed 3-step documentation content in Spanish."""
        modal_i18n = ES_LOCALE["help_modal"]
        tab1, tab2, tab3 = st.tabs(
            [
                modal_i18n["tab_1"],
                modal_i18n["tab_2"],
                modal_i18n["tab_3"],
            ]
        )
        with tab1:
            st.markdown(cls.STEP_1_SWEX_MD)
        with tab2:
            st.markdown(cls.STEP_2_STATS_MD)
        with tab3:
            st.markdown(cls.STEP_3_OPTIMIZER_MD)

        st.divider()
        st.markdown(modal_i18n["glossary_title"])
        for key, label in [
            ("effective_hp", "EHP (Vida Efectiva)"),
            ("damage_multiplier", "Multiplicador de Daño"),
            ("include_equipped_runes", "Incluir runas equipadas"),
            ("broken_sets", "Permitir Sets Rotos (Broken)"),
            ("intangible_wildcard", "Runa Intangible (Comodín)"),
        ]:
            st.markdown(f"- **{label}:** {TOOLTIPS[key]}")


@st.dialog(ES_LOCALE["help_modal"]["dialog_title"], width="large")
def open_help_guide_dialog() -> None:
    """Opens the Streamlit modal dialog containing the HelpGuideModal content."""
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
    storage_service: AccountStorageService | None = None,
    persist: bool = True,
) -> None:
    """Stores the active AccountProfile in session_state and persists it via AccountStorageService."""
    st.session_state.profile = profile
    st.session_state.is_demo_mode = is_demo
    st.session_state.loaded_file_sig = file_signature
    st.session_state.last_opt_result = None
    st.session_state.last_team_opt_results = None
    st.session_state.locked_builds_pve = {}
    st.session_state.locked_builds_rta = {}
    st.session_state.indexeddb_clear_pending = False

    if persist:
        svc = (
            storage_service
            or st.session_state.get("storage_service")
            or AccountStorageService.get_instance()
        )
        svc.save_account(
            profile=profile,
            is_demo_mode=is_demo,
            file_signature=file_signature,
        )


def clear_account_state(
    storage_service: AccountStorageService | None = None,
) -> None:
    """Clears the currently loaded account from session_state and purges persisted IndexedDB/snapshot state."""
    st.session_state.profile = None
    st.session_state.is_demo_mode = False
    st.session_state.loaded_file_sig = None
    st.session_state.last_opt_result = None
    st.session_state.last_team_opt_results = None
    st.session_state.locked_builds_pve = {}
    st.session_state.locked_builds_rta = {}
    st.session_state.indexeddb_clear_pending = True

    svc = (
        storage_service
        or st.session_state.get("storage_service")
        or AccountStorageService.get_instance()
    )
    svc.clear_account()


def render_top_navbar(
    profile: AccountProfile | None,
    is_demo_mode: bool = False,
) -> None:
    """
    Renders the persistent top navigation bar in Spanish featuring:
    - App branding
    - Active `wizard_name` badge + Nivel, Maná, Cristales
    - 'Cambiar Cuenta / Limpiar' button
    - 'Guía de Uso' button opening `HelpGuideModal`
    """
    nav_i18n = ES_LOCALE["navbar"]
    nav_cols = st.columns([2.8, 3.6, 1.4, 1.2])

    with nav_cols[0]:
        st.markdown(
            f"<div style='font-size:1.3rem;font-weight:800;letter-spacing:-0.02em;'>"
            f"⚡ SW-OptiPy <span style='font-size:0.82rem;font-weight:500;color:#9ca3af;'>"
            f"| {ES_LOCALE['app']['subtitle']}</span></div>",
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
            mode_tag = nav_i18n["demo_badge"] if is_demo_mode else nav_i18n["active_badge"]
            st.markdown(
                f"<div style='display:inline-flex;flex-wrap:wrap;align-items:center;gap:8px;padding:6px 12px;"
                f"border-radius:999px;background:{badge_bg};border:1px solid {badge_border};"
                f"font-size:0.82rem;font-weight:600;'>"
                f"<span>{mode_tag}:</span> <code style='color:#fff;'>{profile.wizard_name}</code> "
                f"<span style='color:#d1d5db;'>"
                f"{nav_i18n['level']} {profile.wizard_level} · "
                f"💎 {nav_i18n['crystals']}: {profile.wizard_crystal:,} · "
                f"🪙 {nav_i18n['mana']}: {profile.wizard_mana:,}"
                f"</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='padding:6px 12px;color:#9ca3af;font-size:0.85rem;'>"
                f"{nav_i18n['no_account_loaded']}"
                f"</div>",
                unsafe_allow_html=True,
            )

    with nav_cols[2]:
        if profile is not None:
            if st.button(
                f"🔄 {nav_i18n['clear_switch_account']}",
                use_container_width=True,
                help="Cerrar la cuenta actual y volver a la pantalla de inicio para cargar otro archivo JSON.",
            ):
                clear_account_state()
                st.rerun()

    with nav_cols[3]:
        if st.button(
            f"📖 {nav_i18n['help_guide']}",
            use_container_width=True,
            help="Abrir la guía paso a paso sobre exportación SWEX, estadísticas y uso del optimizador.",
        ):
            open_help_guide_dialog()

    if is_demo_mode and profile is not None:
        st.info(
            nav_i18n["demo_banner"].format(
                wizard_name=profile.wizard_name,
                unit_count=len(profile.monsters),
                rune_count=len(profile.runes),
            )
        )


def render_empty_state_hero(monster_service: MonsterDataService) -> None:
    """
    Renders the interactive Onboarding Hero / Empty State in Spanish when no account JSON is loaded:
    - Primary Drag & Drop JSON Upload Zone ('Cargar JSON')
    - Prominent 'Probar Cuenta Demo' button
    - Quick 3-step overview cards
    """
    ob = ES_LOCALE["onboarding"]
    st.markdown(
        f"""
        <div style="text-align:center;padding:28px 20px 18px 20px;border-radius:16px;
                    background:linear-gradient(135deg, rgba(30,41,59,0.85), rgba(15,23,42,0.92));
                    border:1px solid rgba(240,185,11,0.3);margin-bottom:22px;">
            <h1 style="margin:0;font-size:2.1rem;color:#f8fafc;">
                {ob['welcome_title']}
            </h1>
            <p style="font-size:1.05rem;color:#cbd5e1;max-width:740px;margin:10px auto 0 auto;">
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
            ob["dropzone_label"],
            type=["json"],
            key="hero_swex_uploader",
            help=ob["dropzone_help"],
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
                st.error(f"Error al procesar el archivo JSON de SWEX: {exc}")

    with col_demo:
        st.markdown(f"### {ob['demo_section_title']}")
        st.caption(ob["demo_section_caption"])
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        if st.button(
            ob["try_demo_button"],
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
            ob["read_guide_button"],
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
