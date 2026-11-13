"""Domain models (Pydantic) for Summoners War monsters, runes, artifacts, and account profiles."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.constants import (
    MAIN_STAT_MAX_5STAR,
    MAIN_STAT_MAX_6STAR,
    MAX_ROLL_6STAR,
    NAME_TO_SET_ID,
    SET_ID_MAP,
    SET_SIZES,
    SET_STAT_BONUSES,
    STAT_ID_MAP,
    SwConstants,
)


class RuneSubstat(BaseModel):
    """Represents a rune substat: [stat_id, base_val, gemmed, grind_val]."""

    model_config = ConfigDict(populate_by_name=True)

    stat_id: int
    base_val: int
    gemmed: int = 0
    grind_val: int = 0

    @property
    def effective_val(self) -> int:
        """Effective value = base_val + grind_val."""
        return self.base_val + self.grind_val

    @property
    def stat_name(self) -> str:
        return STAT_ID_MAP.get(self.stat_id, f"Unknown({self.stat_id})")


class Rune(BaseModel):
    """Summoners War Rune model normalized from SWEX format."""

    model_config = ConfigDict(populate_by_name=True)

    rune_id: int
    slot_no: int = Field(ge=1, le=6)
    set_id: int
    rune_class: int = Field(default=6, alias="class")
    upgrade_curr: int = Field(default=15, ge=0, le=15)
    pri_eff: tuple[int, int]
    prefix_eff: tuple[int, int] = (0, 0)
    sec_eff: list[RuneSubstat] = Field(default_factory=list)
    occupied_id: int = 0
    rta_occupied_id: int = 0

    @model_validator(mode="before")
    @classmethod
    def _parse_raw_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        parsed = dict(data)
        prefix = parsed.get("prefix_eff")
        if not prefix or len(prefix) < 2:
            parsed["prefix_eff"] = (0, 0)
        raw_sec = parsed.get("sec_eff", [])
        norm_sec: list[Any] = []
        for item in raw_sec:
            if isinstance(item, (list, tuple)):
                stat_id = int(item[0]) if len(item) > 0 else 0
                base_val = int(item[1]) if len(item) > 1 else 0
                gemmed = int(item[2]) if len(item) > 2 else 0
                grind_val = int(item[3]) if len(item) > 3 else 0
                norm_sec.append(
                    {
                        "stat_id": stat_id,
                        "base_val": base_val,
                        "gemmed": gemmed,
                        "grind_val": grind_val,
                    }
                )
            else:
                norm_sec.append(item)
        parsed["sec_eff"] = norm_sec
        return parsed

    @property
    def is_ancient(self) -> bool:
        """True if the rune is an Ancient Rune (class >= 16 in SWEX)."""
        return self.rune_class >= 16

    @property
    def stars(self) -> int:
        """Star grade (1-6)."""
        return self.rune_class - 10 if self.rune_class > 10 else self.rune_class

    @property
    def set_name(self) -> str:
        return SET_ID_MAP.get(self.set_id, f"Unknown({self.set_id})")

    @property
    def main_stat_id(self) -> int:
        return self.pri_eff[0]

    @property
    def main_stat_val(self) -> int:
        return self.pri_eff[1]

    @property
    def innate_stat_id(self) -> int:
        return self.prefix_eff[0]

    @property
    def innate_stat_val(self) -> int:
        return self.prefix_eff[1]

    def get_main_stat_val(self, simulate_plus15: bool = False) -> int:
        """Returns main stat value, simulating +15 max value when requested."""
        if simulate_plus15 and self.upgrade_curr < 15:
            if self.stars == 6:
                return MAIN_STAT_MAX_6STAR.get(self.main_stat_id, self.main_stat_val)
            if self.stars == 5:
                return MAIN_STAT_MAX_5STAR.get(self.main_stat_id, self.main_stat_val)
        return self.main_stat_val

    def get_stat_total(self, stat_id: int, simulate_plus15: bool = False) -> int:
        """Total contribution of this rune to `stat_id` (main + innate + ground substats)."""
        total = 0
        if self.main_stat_id == stat_id:
            total += self.get_main_stat_val(simulate_plus15=simulate_plus15)
        if self.innate_stat_id == stat_id and self.innate_stat_val > 0:
            total += self.innate_stat_val
        for sub in self.sec_eff:
            if sub.stat_id == stat_id:
                total += sub.effective_val
        return total


class Artifact(BaseModel):
    """Summoners War Artifact model normalized from SWEX format."""

    model_config = ConfigDict(populate_by_name=True)

    artifact_id: int = Field(alias="rid", default=0)
    occupied_id: int = 0
    rta_occupied_id: int = 0
    slot: int = 1  # 1: Attribute, 2: Archetype
    type_: int = Field(default=1, alias="type")
    attribute: int = 0
    unit_style: int = 0
    natural_rank: int = 5
    rank: int = 15
    level: int = 15
    pri_eff: tuple[int, int] = (100, 0)  # 100: HP flat, 101: ATK flat, 102: DEF flat
    sec_eff: list[list[float | int]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_artifact_id(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        parsed = dict(data)
        if "artifact_id" in parsed and "rid" not in parsed:
            parsed["rid"] = parsed["artifact_id"]
        pri = parsed.get("pri_eff") or parsed.get("pri_effect")
        if isinstance(pri, (list, tuple)) and len(pri) >= 2:
            parsed["pri_eff"] = (int(pri[0]), int(pri[1]))
        else:
            parsed["pri_eff"] = (100, 0)
        if "sec_eff" not in parsed and "sec_effects" in parsed:
            parsed["sec_eff"] = parsed["sec_effects"]
        return parsed

    @property
    def flat_hp(self) -> int:
        return self.pri_eff[1] if self.pri_eff[0] in (1, 100) else 0

    @property
    def flat_atk(self) -> int:
        return self.pri_eff[1] if self.pri_eff[0] in (3, 101) else 0

    @property
    def flat_def(self) -> int:
        return self.pri_eff[1] if self.pri_eff[0] in (5, 102) else 0


class MonsterMasterData(BaseModel):
    """Monster species metadata cached locally from SWARFARM."""

    com2us_id: int
    name: str
    element: str = "Unknown"
    archetype: str = "Unknown"
    awaken_level: int = 1
    base_stars: int = 5
    image_filename: str = ""
    skills: list[int] = Field(default_factory=list)
    leader_skill: dict[str, Any] | None = None

    @property
    def icon_url(self) -> str:
        if self.image_filename:
            return f"https://swarfarm.com/static/herders/images/monsters/{self.image_filename}"
        return ""


class Monster(BaseModel):
    """Monster instance in the player's account (unit_list in SWEX)."""

    model_config = ConfigDict(populate_by_name=True)

    unit_id: int
    unit_master_id: int
    name: str = ""
    element: str = "Unknown"
    archetype: str = "Unknown"
    base_stars: int = 5
    awaken_level: int = 1
    image_filename: str = ""
    unit_level: int = 40
    unit_class: int = Field(default=6, alias="class")
    con: int
    base_hp: int = 0
    atk: int
    def_: int = Field(alias="def")
    spd: int
    critical_rate: int = 15
    critical_damage: int = 50
    resist: int = 15
    accuracy: int = 0
    runes: list[int] = Field(default_factory=list)
    rta_runes: list[int] = Field(default_factory=list)
    artifacts: list[int] = Field(default_factory=list)
    rta_artifacts: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _compute_base_hp(self) -> Monster:
        """Critical domain rule: base_hp = con * 15."""
        self.base_hp = self.con * 15
        if not self.name:
            self.name = f"Unknown Monster (#{self.unit_master_id}) - [{self.element}]"
        return self

    @property
    def icon_url(self) -> str:
        """Full SWARFARM static URL for the monster icon, or SVG placeholder if missing."""
        if self.image_filename:
            return f"https://swarfarm.com/static/herders/images/monsters/{self.image_filename}"
        return (
            "data:image/svg+xml;utf8,"
            "<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>"
            "<rect width='64' height='64' rx='12' fill='%23262730'/>"
            "<text x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' "
            "fill='%23f0b90b' font-family='sans-serif' font-size='24' font-weight='bold'>?</text>"
            "</svg>"
        )


class MonsterStats(BaseModel):
    """Calculated final monster statistics with an equipped build."""

    unit_id: int
    name: str
    base_hp: int
    base_atk: int
    base_def: int
    base_spd: int
    total_hp: int
    total_atk: int
    total_def: int
    rune_spd: int
    total_spd: int
    combat_spd: int
    crate: int
    cdmg: int
    res: int
    acc: int
    ehp: float
    active_sets: list[str] = Field(default_factory=list)
    intangible_replaced_set: str | None = None
    avg_efficiency: float = 0.0


class AccountProfile(BaseModel):
    """Complete player account profile imported from SWEX JSON."""

    wizard_id: int = 0
    wizard_name: str = "Summoner"
    wizard_level: int = 50
    wizard_mana: int = 0
    wizard_crystal: int = 0
    monsters: dict[int, Monster] = Field(default_factory=dict)
    runes: dict[int, Rune] = Field(default_factory=dict)
    artifacts: dict[int, Artifact] = Field(default_factory=dict)
    rta_rune_equip_map: dict[int, int] = Field(default_factory=dict)
    rta_artifact_equip_map: dict[int, int] = Field(default_factory=dict)
    locked_runes_pve: set[int] = Field(default_factory=set)
    locked_runes_rta: set[int] = Field(default_factory=set)

    def get_equipped_runes(
        self, unit_id: int, mode: Literal["pve", "rta"] = "pve"
    ) -> list[Rune]:
        """Returns equipped runes on `unit_id` for the selected mode (PVE or RTA)."""
        monster = self.monsters.get(unit_id)
        if not monster:
            return []
        rune_ids = monster.rta_runes if mode == "rta" else monster.runes
        return [self.runes[rid] for rid in rune_ids if rid in self.runes]

    def get_available_runes(
        self,
        mode: Literal["pve", "rta"] = "pve",
        excluded_rune_ids: set[int] | None = None,
        excluded_unit_ids: set[int] | None = None,
    ) -> list[Rune]:
        """Returns available runes for the selected mode respecting locked runes."""
        locked = set(self.locked_runes_rta if mode == "rta" else self.locked_runes_pve)
        if excluded_rune_ids:
            locked |= excluded_rune_ids
        if excluded_unit_ids:
            for uid in excluded_unit_ids:
                for rune in self.get_equipped_runes(uid, mode=mode):
                    locked.add(rune.rune_id)
        return [r for rid, r in self.runes.items() if rid not in locked]


__all__ = [
    "AccountProfile",
    "Artifact",
    "MAIN_STAT_MAX_5STAR",
    "MAIN_STAT_MAX_6STAR",
    "MAX_ROLL_6STAR",
    "Monster",
    "MonsterMasterData",
    "MonsterStats",
    "NAME_TO_SET_ID",
    "Rune",
    "RuneSubstat",
    "SET_ID_MAP",
    "SET_SIZES",
    "SET_STAT_BONUSES",
    "STAT_ID_MAP",
    "SwConstants",
]
