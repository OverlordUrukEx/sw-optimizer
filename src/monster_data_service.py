"""Modular MonsterDataService for O(1) monster metadata lookup and bulk SWARFARM v2 API sync."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

SWARFARM_MONSTERS_API_URL = "https://swarfarm.com/api/v2/monsters/"
SWARFARM_ICON_BASE_URL = "https://swarfarm.com/static/herders/images/monsters/"

DEFAULT_MONSTER_MAP_PATH = Path(__file__).resolve().parent / "data" / "monster_map.json"
CACHE_SCHEMA_VERSION = 1
DEFAULT_CACHE_TTL_SECONDS = 7 * 24 * 3600  # 7 days

# Com2uS attribute / last-digit ID mapping to Element name
COM2US_ELEMENT_MAP: dict[int, str] = {
    1: "Water",
    2: "Fire",
    3: "Wind",
    4: "Light",
    5: "Dark",
    6: "Pure",
}

ELEMENT_BADGE_MAP: dict[str, str] = {
    "Water": "💧 Water",
    "Fire": "🔥 Fire",
    "Wind": "🌪️ Wind",
    "Light": "✨ Light",
    "Dark": "🌑 Dark",
    "Pure": "🌀 Pure",
    "Unknown": "❓ Unknown",
}

# Fallback SVG data URI when a monster has no image_filename (e.g. unknown new monster ID)
DEFAULT_FALLBACK_ICON_DATA_URI = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'>"
    "<rect width='64' height='64' rx='12' fill='%23262730'/>"
    "<text x='50%25' y='54%25' dominant-baseline='middle' text-anchor='middle' "
    "fill='%23f0b90b' font-family='sans-serif' font-size='24' font-weight='bold'>?</text>"
    "</svg>"
)

# Built-in static seed with authentic SWARFARM com2us_id and image_filename values
# Ensures offline operation even if monster_map.json is absent.
BUILTIN_FALLBACK_MONSTERS: dict[int, dict[str, Any]] = {
    10111: {
        "name": "Elucia",
        "element": "Water",
        "base_stars": 3,
        "awaken_level": 1,
        "image_filename": "unit_icon_0000_0_1.png",
    },
    11032: {
        "name": "Raoq",
        "element": "Fire",
        "base_stars": 3,
        "awaken_level": 2,
        "image_filename": "unit_icon_0051_1_3.png",
    },
    11034: {
        "name": "Belladeon",
        "element": "Light",
        "base_stars": 3,
        "awaken_level": 2,
        "image_filename": "unit_icon_0051_3_3.png",
    },
    11035: {
        "name": "Kro",
        "element": "Dark",
        "base_stars": 3,
        "awaken_level": 2,
        "image_filename": "unit_icon_0051_4_3.png",
    },
    11532: {
        "name": "Spectra",
        "element": "Fire",
        "base_stars": 3,
        "awaken_level": 2,
        "image_filename": "unit_icon_0055_0_1.png",
    },
    11533: {
        "name": "Bernard",
        "element": "Wind",
        "base_stars": 3,
        "awaken_level": 2,
        "image_filename": "unit_icon_0055_0_2.png",
    },
    13413: {
        "name": "Lushen",
        "element": "Wind",
        "base_stars": 4,
        "awaken_level": 1,
        "image_filename": "unit_icon_0011_2_2.png",
    },
    14511: {
        "name": "Sigmarus",
        "element": "Water",
        "base_stars": 5,
        "awaken_level": 1,
        "image_filename": "unit_icon_0017_0_3.png",
    },
    14513: {
        "name": "Teshar",
        "element": "Wind",
        "base_stars": 5,
        "awaken_level": 1,
        "image_filename": "unit_icon_0017_2_3.png",
    },
    14712: {
        "name": "Verdehile",
        "element": "Fire",
        "base_stars": 4,
        "awaken_level": 1,
        "image_filename": "unit_icon_0016_1_2.png",
    },
    15713: {
        "name": "Seara",
        "element": "Wind",
        "base_stars": 5,
        "awaken_level": 1,
        "image_filename": "unit_icon_0022_2_1.png",
    },
    17115: {
        "name": "Veromos",
        "element": "Dark",
        "base_stars": 5,
        "awaken_level": 1,
        "image_filename": "unit_icon_0019_4_4.png",
    },
    18913: {
        "name": "Tiana",
        "element": "Wind",
        "base_stars": 5,
        "awaken_level": 1,
        "image_filename": "unit_icon_0033_2_3.png",
    },
    19114: {
        "name": "Fran",
        "element": "Light",
        "base_stars": 3,
        "awaken_level": 1,
        "image_filename": "unit_icon_0028_4_0.png",
    },
    19314: {
        "name": "Loren",
        "element": "Light",
        "base_stars": 3,
        "awaken_level": 1,
        "image_filename": "unit_icon_0032_3_4.png",
    },
    19411: {
        "name": "Galleon",
        "element": "Water",
        "base_stars": 4,
        "awaken_level": 1,
        "image_filename": "unit_icon_0034_0_0.png",
    },
    24511: {
        "name": "Moore",
        "element": "Water",
        "base_stars": 5,
        "awaken_level": 1,
        "image_filename": "unit_icon_0066_1_1.png",
    },
    25112: {
        "name": "Kaki",
        "element": "Fire",
        "base_stars": 4,
        "awaken_level": 1,
        "image_filename": "unit_icon_0073_1_2.png",
    },
    25313: {
        "name": "Oliver",
        "element": "Wind",
        "base_stars": 5,
        "awaken_level": 1,
        "image_filename": "unit_icon_0076_1_3.png",
    },
    25613: {
        "name": "Riley",
        "element": "Wind",
        "base_stars": 5,
        "awaken_level": 1,
        "image_filename": "unit_icon_0078_1_3.png",
    },
}


def infer_element_from_com2us_id(
    com2us_id: int, attribute_id: int | str | None = None
) -> str:
    """Infers monster element from explicit attribute or the last digit of com2us_id."""
    if isinstance(attribute_id, str) and attribute_id.strip():
        cap = attribute_id.strip().capitalize()
        if cap in ELEMENT_BADGE_MAP and cap != "Unknown":
            return cap
    if isinstance(attribute_id, int) and attribute_id in COM2US_ELEMENT_MAP:
        return COM2US_ELEMENT_MAP[attribute_id]
    last_digit = abs(int(com2us_id)) % 10
    return COM2US_ELEMENT_MAP.get(last_digit, "Unknown")


def format_unknown_monster_name(com2us_id: int, element: str = "Unknown") -> str:
    """Returns the standardized fallback display string for unmapped monster IDs."""
    clean_element = (
        element
        if element and element != "Unknown"
        else infer_element_from_com2us_id(com2us_id)
    )
    return f"Unknown Monster (#{com2us_id}) - [{clean_element}]"


class MonsterMetadata(BaseModel):
    """Lightweight monster metadata record stored in the O(1) lookup dictionary."""

    com2us_id: int
    name: str
    element: str = "Unknown"
    base_stars: int = 5
    awaken_level: int = 1
    image_filename: str = ""

    @property
    def icon_url(self) -> str:
        """Full URL for rendering the monster avatar from SWARFARM static assets."""
        if self.image_filename:
            return f"{SWARFARM_ICON_BASE_URL}{self.image_filename}"
        return DEFAULT_FALLBACK_ICON_DATA_URI

    @property
    def element_badge(self) -> str:
        """Formatted element badge with icon."""
        return ELEMENT_BADGE_MAP.get(self.element, f"❓ {self.element}")

    def to_compact_dict(self) -> dict[str, Any]:
        """Serializes essential fields only to keep monster_map.json lightweight."""
        return {
            "name": self.name,
            "element": self.element,
            "base_stars": self.base_stars,
            "awaken_level": self.awaken_level,
            "image_filename": self.image_filename,
        }


class MonsterMapCachePayload(BaseModel):
    """Schema for the versioned local monster_map.json file / localStorage payload."""

    version: int = CACHE_SCHEMA_VERSION
    updated_at: float = Field(default_factory=time.time)
    ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS
    monsters: dict[str, dict[str, Any]] = Field(default_factory=dict)


class MonsterDataService:
    """
    O(1) lookup service for Summoners War monster metadata backed by a bundled
    static JSON map (`data/monster_map.json`) and bulk SWARFARM v2 API sync.
    Guarantees zero N+1 API calls during SWEX JSON import.
    """

    _default_instance: MonsterDataService | None = None

    def __init__(
        self,
        map_path: Path | str = DEFAULT_MONSTER_MAP_PATH,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        auto_load: bool = True,
    ) -> None:
        self.map_path = Path(map_path)
        self.ttl_seconds = ttl_seconds
        self.version = CACHE_SCHEMA_VERSION
        self.updated_at: float = 0.0
        self._map: dict[int, MonsterMetadata] = {}

        if auto_load:
            self.load_local_map()

    @classmethod
    def get_instance(
        cls, map_path: Path | str = DEFAULT_MONSTER_MAP_PATH
    ) -> MonsterDataService:
        """Returns a shared in-memory singleton instance for fast O(1) lookups."""
        resolved = Path(map_path).resolve()
        if (
            cls._default_instance is None
            or cls._default_instance.map_path.resolve() != resolved
        ):
            cls._default_instance = cls(map_path=resolved)
        return cls._default_instance

    @property
    def size(self) -> int:
        """Number of monsters currently loaded in the O(1) lookup table."""
        return len(self._map)

    def is_cache_expired(self, now: float | None = None) -> bool:
        """Checks whether the cached monster map version or timestamp is expired."""
        current_time = time.time() if now is None else now
        if not self._map or self.updated_at <= 0:
            return True
        return (current_time - self.updated_at) > self.ttl_seconds

    def load_local_map(self) -> int:
        """
        Loads the O(1) lookup dictionary from `monster_map.json` if available,
        merging with the built-in static fallback seed so offline execution never fails.
        """
        self._map.clear()

        if self.map_path.exists() and self.map_path.is_file():
            try:
                raw_text = self.map_path.read_text(encoding="utf-8")
                raw_json = json.loads(raw_text)
                if isinstance(raw_json, dict) and "monsters" in raw_json:
                    version = int(raw_json.get("version", 1))
                    if version == CACHE_SCHEMA_VERSION:
                        self.updated_at = float(raw_json.get("updated_at", 0.0))
                        self.ttl_seconds = int(
                            raw_json.get("ttl_seconds", self.ttl_seconds)
                        )
                        monsters_dict = raw_json.get("monsters", {})
                    else:
                        monsters_dict = {}
                elif isinstance(raw_json, dict):
                    monsters_dict = raw_json
                    self.updated_at = self.map_path.stat().st_mtime
                else:
                    monsters_dict = {}

                for cid_str, info in monsters_dict.items():
                    if not isinstance(info, dict):
                        continue
                    cid = int(cid_str)
                    self._map[cid] = MonsterMetadata(
                        com2us_id=cid,
                        name=str(info.get("name") or "").strip(),
                        element=str(
                            info.get("element") or infer_element_from_com2us_id(cid)
                        ),
                        base_stars=int(
                            info.get("base_stars") or info.get("natural_stars") or 5
                        ),
                        awaken_level=int(info.get("awaken_level", 1) or 0),
                        image_filename=str(info.get("image_filename") or ""),
                    )
            except Exception:
                self._map.clear()

        for cid, seed_info in BUILTIN_FALLBACK_MONSTERS.items():
            if cid not in self._map:
                self._map[cid] = MonsterMetadata(
                    com2us_id=cid,
                    name=seed_info["name"],
                    element=seed_info["element"],
                    base_stars=seed_info["base_stars"],
                    awaken_level=seed_info["awaken_level"],
                    image_filename=seed_info["image_filename"],
                )

        return len(self._map)

    def save_local_map(self) -> Path:
        """Persists the current O(1) lookup dictionary to `src/data/monster_map.json`."""
        self.map_path.parent.mkdir(parents=True, exist_ok=True)
        self.updated_at = time.time()
        compact_monsters = {
            str(cid): meta.to_compact_dict()
            for cid, meta in sorted(self._map.items())
        }
        self.map_path.write_text(
            json.dumps(compact_monsters, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return self.map_path

    def export_browser_cache_json(self) -> str:
        """Returns a compact JSON string suitable for browser localStorage/IndexedDB caching."""
        compact_monsters = {
            str(cid): meta.to_compact_dict() for cid, meta in self._map.items()
        }
        return json.dumps(
            {
                "version": self.version,
                "updated_at": self.updated_at or time.time(),
                "ttl_seconds": self.ttl_seconds,
                "monsters": compact_monsters,
            },
            separators=(",", ":"),
        )

    def get_monster_metadata(
        self,
        com2us_id: int,
        element_hint: str | int | None = None,
    ) -> MonsterMetadata:
        """
        O(1) dictionary lookup by `com2us_id` (`unit_master_id`).
        Never performs network or database I/O.
        If not found, returns `"Unknown Monster (#ID) - [Element]"`.
        """
        found = self._map.get(int(com2us_id))
        if found is not None:
            return found

        inferred_element = infer_element_from_com2us_id(com2us_id, element_hint)
        return MonsterMetadata(
            com2us_id=int(com2us_id),
            name=format_unknown_monster_name(int(com2us_id), inferred_element),
            element=inferred_element,
            base_stars=5,
            awaken_level=0,
            image_filename="",
        )

    def register_monster(self, metadata: MonsterMetadata) -> None:
        """Inserts or updates a monster entry in the in-memory O(1) lookup map."""
        self._map[metadata.com2us_id] = metadata

    async def _fetch_all_pages_async(
        self,
        base_url: str = SWARFARM_MONSTERS_API_URL,
        timeout: float = 15.0,
        max_concurrency: int = 8,
    ) -> list[dict[str, Any]]:
        """Fetches all paginated monster pages from SWARFARM v2 API concurrently."""
        headers = {"Accept": "application/json", "User-Agent": "SW-OptiPy/1.0"}
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, headers=headers
        ) as client:
            first_resp = await client.get(base_url, params={"page": 1})
            first_resp.raise_for_status()
            first_data = first_resp.json()
            results: list[dict[str, Any]] = list(first_data.get("results", []))
            total_count = int(first_data.get("count", len(results)))
            page_size = len(results)

            if page_size <= 0 or total_count <= page_size or not first_data.get("next"):
                return results

            total_pages = (total_count + page_size - 1) // page_size
            semaphore = asyncio.Semaphore(max_concurrency)

            async def _fetch_page(page_num: int) -> list[dict[str, Any]]:
                async with semaphore:
                    resp = await client.get(base_url, params={"page": page_num})
                    resp.raise_for_status()
                    body = resp.json()
                    return list(body.get("results", []))

            tasks = [_fetch_page(p) for p in range(2, total_pages + 1)]
            pages_results = await asyncio.gather(*tasks)
            for page_items in pages_results:
                results.extend(page_items)

            return results

    def sync_from_swarfarm(
        self,
        force: bool = False,
        base_url: str = SWARFARM_MONSTERS_API_URL,
        timeout: float = 15.0,
    ) -> int:
        """
        Synchronizes the complete monster bestiary from SWARFARM v2 API in bulk
        (handling pagination) and writes `data/monster_map.json`.
        If the local cache is still fresh and `force=False`, skips network I/O.
        """
        if not force and not self.is_cache_expired() and self.size > 100:
            return self.size

        raw_monsters = asyncio.run(
            self._fetch_all_pages_async(base_url=base_url, timeout=timeout)
        )
        for item in raw_monsters:
            if not isinstance(item, dict):
                continue
            cid = item.get("com2us_id")
            if not cid:
                continue
            cid_int = int(cid)
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            element = str(
                item.get("element") or infer_element_from_com2us_id(cid_int)
            ).capitalize()
            base_stars = int(
                item.get("natural_stars") or item.get("base_stars") or 5
            )
            awaken_level = int(item.get("awaken_level", 1) or 0)
            image_filename = str(item.get("image_filename") or "")

            self._map[cid_int] = MonsterMetadata(
                com2us_id=cid_int,
                name=name,
                element=element,
                base_stars=base_stars,
                awaken_level=awaken_level,
                image_filename=image_filename,
            )

        self.save_local_map()
        return len(self._map)


if __name__ == "__main__":
    service = MonsterDataService(auto_load=True)
    try:
        total = service.sync_from_swarfarm(force=True)
        print(f"Successfully synced {total} monsters into {service.map_path}")
    except Exception as exc:
        service.save_local_map()
        print(
            f"SWARFARM sync unavailable ({exc}); saved fallback map with {service.size} monsters to {service.map_path}"
        )
