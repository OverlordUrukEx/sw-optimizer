"""Modular UI components for Onboarding Empty State, Demo Account Loader, Tooltips, and HelpGuideModal."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import streamlit as st

from src.models import AccountProfile
from src.monster_data_service import MonsterDataService
from src.parser import parse_swex_json

DEMO_ACCOUNT_PATH = Path(__file__).resolve().parent / "data" / "demo_account.json"

# Centralized technical UI tooltips (DRY)
TOOLTIPS: dict[str, str] = {
    "effective_hp": (
        "Effective HP (EHP): Measures true tankiness combining Total HP and Total DEF using "
        "EHP = Total_HP * (1140 + Total_DEF * 3.5) / 1000."
    ),
    "damage_multiplier": (
        "Damage Multiplier: Expected average critical damage score computed as "
        "Total_ATK * (1 + (CRate% / 100) * (CDmg% / 100))."
    ),
    "include_equipped_runes": (
        "Include Equipped Runes: When enabled, runes currently equipped on other monsters "
        "(except locked runes) are included in the optimization pool."
    ),
    "broken_sets": (
        "Broken Sets: Any remaining rune slots not required by your selected 4-piece or 2-piece sets "
        "can be filled with high-stat individual runes from any set (or completed via an Intangible rune)."
    ),
    "intangible_wildcard": (
        "Intangible Set (ID 25): A 1-piece wildcard rune that automatically replaces 1 missing piece "
        "of any incomplete 4-piece or 2-piece set (max 1 active per build)."
    ),
    "simulate_plus15": (
        "Simulate +15 Runes: Evaluates runes below +15 using official 6★ +15 maximum main stat values "
        "(e.g. SPD +42, HP%/ATK%/DEF% +63%, CDmg +80%)."
    ),
    "focus_pruning": (
        "Focus Pruning: Pre-ranks runes in each slot by relevant substat weights before permutation "
        "to evaluate top candidate builds in milliseconds."
    ),
    "barion_efficiency": (
        "Barion Efficiency Formula: ((1.0 + sum(effective_substat / max_6star_roll)) / 2.8) * 100, "
        "including Grindstone bonuses and innate stats."
    ),
}


class HelpGuideModal:
    """
    Structured 3-step User Help & Documentation guide covering SWEX data extraction,
    Summoners War domain math (CON * 15, Grinds, Ancient Runes), and running optimizations.
    """

    STEP_1_SWEX_MD = """
### Step 1: Extracting Your Data (SWEX)
To import your own Summoners War account into **SW-OptiPy**, export your account JSON using **Summoners War Exporter (SWEX)**:

1. **Download & Launch SWEX:** Open *Summoners War Exporter* on your PC/Mac and start the built-in proxy server.
2. **Connect Your Device / Emulator:** Configure your mobile device or emulator Wi-Fi proxy to point to the IP and port shown in SWEX (with HTTPS certificate enabled).
3. **Log into Summoners War:** As the game loads the `HubUserLogin` packet, SWEX automatically captures and saves a file named `<WizardName>-<WizardID>.json`.
4. **Upload Here:** Drag and drop that `.json` file into the upload zone—your monsters, runes, and artifacts are parsed locally in $O(1)$ time with zero external API calls per unit.
"""

    STEP_2_STATS_MD = """
### Step 2: Understanding Stats & Runes
**SW-OptiPy** applies exact Summoners War domain mathematics:

- **Base HP (`CON * 15`):** In raw SWEX JSON files, monster constitution is stored as `con`. The parser automatically computes $\\text{Base HP} = \\text{con} \\times 15$ at Level 40.
- **Grindstone & Gem Bonuses (`base + grind`):** Every rune substat array `[stat_id, base_val, gemmed, grind_val]` is evaluated using its true effective value ($\\text{base\\_val} + \\text{grind\\_val}$).
- **Ancient Runes (`6★ Ancient`):** Runes with `class = 16` are identified as **6★ Ancient** runes, preserving their higher initial rolls in **Barion Efficiency** calculations.
- **Effective HP (EHP):** Tankiness is scored via $\\text{EHP} = \\frac{\\text{Total HP} \\times (1140 + \\text{Total DEF} \\times 3.5)}{1000}$.
"""

    STEP_3_OPTIMIZER_MD = """
### Step 3: Running an Optimization
1. **Pick a Monster:** Search by name or filter by Element (`💧 Water`, `🔥 Fire`, `🌪️ Wind`, `✨ Light`, `🌑 Dark`) in the **General / PVE Optimizer** or **RTA Speed Tuning** tab.
2. **Select Rune Sets & Broken Sets:** Choose required 4-piece (`Violent`, `Swift`, `Rage`, `Despair`, `Fatal`) or 2-piece (`Will`, `Blade`, `Energy`, `Nemesis`, `Fight`) sets. Unassigned slots automatically allow **Broken Sets**, and **Intangible (`set_id = 25`)** runes automatically act as a 1-piece wildcard.
3. **Filter Slots 2 / 4 / 6 & Thresholds:** Restrict Main Stats on Slots 2, 4, and 6 (e.g., `SPD / CDmg% / ATK%`) and set hard minimum thresholds (`Min SPD`, `Min CR%`, `Min ACC%`, `Min HP`, `Min ATK`).
4. **Optimize & Lock Builds:** Click **Run Optimization (Numba JIT)** to evaluate permutations via Branch & Bound, then click **Lock Build** to reserve those 6 runes in PVE or RTA mode.
"""

    @classmethod
    def render_body(cls) -> None:
        """Renders the tabbed 3-step documentation content."""
        tab1, tab2, tab3 = st.tabs(
            [
                "1️⃣ Extracting Data (SWEX)",
                "2️⃣ Stats, Grinds & Ancient Runes",
                "3️⃣ Running an Optimization",
            ]
        )
        with tab1:
            st.markdown(cls.STEP_1_SWEX_MD)
        with tab2:
            st.markdown(cls.STEP_2_STATS_MD)
        with tab3:
            st.markdown(cls.STEP_3_OPTIMIZER_MD)

        st.divider()
        st.markdown("#### 💡 Quick Reference Glossary")
        for key, label in [
            ("effective_hp", "Effective HP (EHP)"),
            ("damage_multiplier", "Damage Multiplier"),
            ("include_equipped_runes", "Include Equipped Runes"),
            ("broken_sets", "Broken Sets"),
            ("intangible_wildcard", "Intangible Wildcard Rune"),
        ]:
            st.markdown(f"- **{label}:** {TOOLTIPS[key]}")


@st.dialog("📖 How to Use SW-OptiPy — User Guide", width="large")
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
    Renders the persistent top navigation bar featuring:
    - App branding
    - Active `wizard_name` badge (and Demo Mode indicator)
    - 'Clear / Switch Account' button
    - 'How to Use' button opening `HelpGuideModal`
    """
    nav_cols = st.columns([3.2, 2.8, 1.5, 1.5])
    with nav_cols[0]:
        st.markdown(
            "<div style='font-size:1.35rem;font-weight:800;letter-spacing:-0.02em;'>"
            "⚡ SW-OptiPy <span style='font-size:0.85rem;font-weight:500;color:#9ca3af;'>"
            "| Summoners War Rune & Speed Tuning Optimizer</span></div>",
            unsafe_allow_html=True,
        )

    with nav_cols[1]:
        if profile is not None:
            badge_bg = "rgba(245, 158, 11, 0.18)" if is_demo_mode else "rgba(16, 185, 129, 0.18)"
            badge_border = "#f59e0b" if is_demo_mode else "#10b981"
            mode_tag = "🧪 DEMO ACCOUNT" if is_demo_mode else "✅ ACTIVE ACCOUNT"
            st.markdown(
                f"<div style='display:inline-flex;align-items:center;gap:8px;padding:6px 12px;"
                f"border-radius:999px;background:{badge_bg};border:1px solid {badge_border};"
                f"font-size:0.85rem;font-weight:600;'>"
                f"<span>{mode_tag}:</span> <code style='color:#fff;'>{profile.wizard_name}</code> "
                f"<span style='color:#9ca3af;'>({len(profile.monsters)} units · {len(profile.runes)} runes)</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='padding:6px 12px;color:#9ca3af;font-size:0.85rem;'>"
                "No account loaded — Upload a SWEX JSON or try the Demo Account below"
                "</div>",
                unsafe_allow_html=True,
            )

    with nav_cols[2]:
        if profile is not None:
            if st.button(
                "🔄 Clear / Switch Account",
                use_container_width=True,
                help="Unload the current account profile and return to the import screen.",
            ):
                clear_account_state()
                st.rerun()

    with nav_cols[3]:
        if st.button(
            "📖 How to Use",
            use_container_width=True,
            help="Open the step-by-step guide on SWEX export, rune math, and optimization.",
        ):
            open_help_guide_dialog()

    if is_demo_mode and profile is not None:
        st.info(
            f"🧪 **Demo Mode Active (`{profile.wizard_name}`):** You are exploring a sanitized demo account "
            f"with **{len(profile.monsters)} monsters** (including 6★, 2A, and Homunculus) and **{len(profile.runes)} runes**. "
            "Click **Clear / Switch Account** in the top bar anytime to upload your own SWEX JSON."
        )


def render_empty_state_hero(monster_service: MonsterDataService) -> None:
    """
    Renders the interactive Onboarding Hero / Empty State when no account JSON is loaded:
    - Primary Drag & Drop JSON Upload Zone
    - Prominent 'Try Demo Account' button
    - Quick 3-step overview cards
    """
    st.markdown(
        """
        <div style="text-align:center;padding:28px 20px 18px 20px;border-radius:16px;
                    background:linear-gradient(135deg, rgba(30,41,59,0.85), rgba(15,23,42,0.92));
                    border:1px solid rgba(240,185,11,0.3);margin-bottom:22px;">
            <h1 style="margin:0;font-size:2.1rem;color:#f8fafc;">
                ⚡ Welcome to SW-OptiPy
            </h1>
            <p style="font-size:1.05rem;color:#cbd5e1;max-width:720px;margin:10px auto 0 auto;">
                High-performance Summoners War Rune & Artifact Optimizer powered by
                <b>NumPy / Numba JIT Branch & Bound</b> and <b>O(1) SWARFARM Bestiary Resolution</b>.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_upload, col_demo = st.columns([1.4, 1.0], gap="large")

    with col_upload:
        st.markdown("### 📂 1. Import Your SWEX Account JSON")
        st.caption(
            "Drag and drop your `.json` file generated by **Summoners War Exporter (SWEX)**. "
            "Parsed 100% locally in memory."
        )
        uploaded_file = st.file_uploader(
            "Drag & Drop SWEX JSON File",
            type=["json"],
            key="hero_swex_uploader",
            help="Upload your <WizardName>-<WizardID>.json file exported from SWEX.",
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
                st.error(f"Could not parse SWEX JSON file: {exc}")

    with col_demo:
        st.markdown("### 🎮 2. Instant Demo Experience")
        st.caption(
            "Don't have your SWEX JSON file handy? Load our curated **Demo_Summoner** account "
            "(8 diverse 6★/2A/Homunculus units + 78 runes) with a single click."
        )
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        if st.button(
            "🚀 Try Demo Account (Demo_Summoner)",
            type="primary",
            use_container_width=True,
            help="Load src/data/demo_account.json into state immediately.",
        ):
            demo_profile = load_demo_account_profile(monster_service=monster_service)
            activate_account_profile(
                demo_profile, is_demo=True, file_signature="demo_account"
            )
            st.rerun()

        if st.button(
            "📖 Read the 3-Step Quickstart Guide",
            use_container_width=True,
        ):
            open_help_guide_dialog()

    st.divider()
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown(
            "**1️⃣ Export with SWEX**  \nCapture your `HubUserLogin` JSON via Summoners War Exporter or click **Try Demo Account** above."
        )
    with s2:
        st.markdown(
            "**2️⃣ Inspect Runes & Monsters**  \nAutomatic `CON * 15` Base HP, `base + grind` effective values, `6★ Ancient` support, and Barion Efficiency."
        )
    with s3:
        st.markdown(
            "**3️⃣ Optimize & Speed Tune**  \nFilter Sets (Violent, Swift, Will, Intangible) and Slots 2/4/6, set stat minimums, and tune PVE (`0.07`) or RTA (`0.015`) ticks."
        )
