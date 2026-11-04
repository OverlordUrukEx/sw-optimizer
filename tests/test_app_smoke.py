"""Prueba de humo para los componentes de la interfaz Streamlit (src/app.py)."""

from __future__ import annotations

from pathlib import Path

from src.app import _build_runes_dataframe
from src.parser import BestiaryCache, parse_swex_json
from src.sample_generator import generate_sample_swex_dict


def test_app_runes_dataframe_builder(tmp_path: Path) -> None:
    """Verifica que el constructor de DataFrame de Polars para el Dashboard funcione sin errores."""
    cache = BestiaryCache(tmp_path / "cache.sqlite")
    profile = parse_swex_json(generate_sample_swex_dict(seed=42), bestiary=cache)
    df = _build_runes_dataframe(profile)
    assert len(df) == 144
    assert "Eficiencia (%)" in df.columns
    assert "Equipada PVE" in df.columns
    assert "Equipada RTA" in df.columns

