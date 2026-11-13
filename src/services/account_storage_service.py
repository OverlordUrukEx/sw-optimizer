"""Asynchronous IndexedDB persistence service (`AccountStorageService`) for surviving page reloads (F5) without hitting localStorage 5MB limits."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any

from pydantic import BaseModel, Field

from src.domain.models import AccountProfile
from src.services.monster_data_service import MonsterDataService

INDEXED_DB_NAME = "SWOptimizerDB"
INDEXED_DB_VERSION = 1
ACCOUNTS_OBJECT_STORE = "accounts"
MONSTER_MAP_OBJECT_STORE = "monster_map"
ACTIVE_ACCOUNT_KEY = "active_account_v1"

DEFAULT_STATE_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent / ".cache" / "active_account_state.json"
)


class PersistedAccountEnvelope(BaseModel):
    """Normalized persistence envelope for the active Summoners War account."""

    schema_version: int = INDEXED_DB_VERSION
    saved_at: float = Field(default_factory=time.time)
    is_demo_mode: bool = False
    file_signature: str = "demo_account"
    profile: AccountProfile


class AccountStorageService:
    """
    Asynchronous persistence service that replaces synchronous `localStorage` (5MB limit)
    with:
    1. Browser-side asynchronous **IndexedDB** (`SWOptimizerDB` -> object stores `accounts` & `monster_map`)
       capable of storing multi-megabyte normalized inventories without blocking the UI thread.
    2. Atomic local snapshot persistence (`.cache/active_account_state.json`) so Streamlit
       sessions seamlessly restore the normalized `AccountProfile` across full page reloads (`F5`).
    """

    _default_instance: AccountStorageService | None = None

    def __init__(
        self,
        snapshot_path: Path | str = DEFAULT_STATE_SNAPSHOT_PATH,
    ) -> None:
        self.snapshot_path = Path(snapshot_path)

    @classmethod
    def get_instance(
        cls,
        snapshot_path: Path | str = DEFAULT_STATE_SNAPSHOT_PATH,
    ) -> AccountStorageService:
        resolved = Path(snapshot_path).resolve()
        if (
            cls._default_instance is None
            or cls._default_instance.snapshot_path.resolve() != resolved
        ):
            cls._default_instance = cls(snapshot_path=resolved)
        return cls._default_instance

    async def save_account_async(
        self,
        profile: AccountProfile,
        is_demo_mode: bool = False,
        file_signature: str = "custom",
    ) -> PersistedAccountEnvelope:
        """Asynchronously persists the normalized AccountProfile to disk & prepares IndexedDB payload."""
        envelope = PersistedAccountEnvelope(
            schema_version=INDEXED_DB_VERSION,
            saved_at=time.time(),
            is_demo_mode=is_demo_mode,
            file_signature=file_signature,
            profile=profile,
        )
        await asyncio.to_thread(self._write_envelope_sync, envelope)
        return envelope

    def save_account(
        self,
        profile: AccountProfile,
        is_demo_mode: bool = False,
        file_signature: str = "custom",
    ) -> PersistedAccountEnvelope:
        """Persists the normalized AccountProfile so it survives browser page reloads (F5)."""
        envelope = PersistedAccountEnvelope(
            schema_version=INDEXED_DB_VERSION,
            saved_at=time.time(),
            is_demo_mode=is_demo_mode,
            file_signature=file_signature,
            profile=profile,
        )
        self._write_envelope_sync(envelope)
        return envelope

    def _write_envelope_sync(self, envelope: PersistedAccountEnvelope) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.snapshot_path.with_suffix(".tmp")
        payload_str = envelope.model_dump_json()
        tmp_path.write_text(payload_str, encoding="utf-8")
        tmp_path.replace(self.snapshot_path)

    async def restore_account_async(self) -> PersistedAccountEnvelope | None:
        """Asynchronously restores the persisted AccountProfile if present."""
        return await asyncio.to_thread(self.restore_account)

    def restore_account(self) -> PersistedAccountEnvelope | None:
        """Restores the persisted AccountProfile on page reload (F5) if available."""
        if not self.snapshot_path.exists() or not self.snapshot_path.is_file():
            return None
        try:
            raw_text = self.snapshot_path.read_text(encoding="utf-8")
            raw_data = json.loads(raw_text)
            envelope = PersistedAccountEnvelope.model_validate(raw_data)
            if envelope.schema_version != INDEXED_DB_VERSION:
                return None
            return envelope
        except Exception:
            return None

    async def clear_account_async(self) -> None:
        """Asynchronously clears the persisted account snapshot."""
        await asyncio.to_thread(self.clear_account)

    def clear_account(self) -> None:
        """Deletes the persisted account snapshot when the user clears or switches accounts."""
        try:
            if self.snapshot_path.exists():
                self.snapshot_path.unlink()
        except OSError:
            pass

    @staticmethod
    def build_indexeddb_payload(
        profile: AccountProfile | None,
        is_demo_mode: bool = False,
        file_signature: str = "",
    ) -> dict[str, Any] | None:
        """Builds a compact, normalized JSON-serializable summary for browser IndexedDB storage."""
        if profile is None:
            return None
        return {
            "id": ACTIVE_ACCOUNT_KEY,
            "schema_version": INDEXED_DB_VERSION,
            "saved_at": int(time.time()),
            "is_demo_mode": is_demo_mode,
            "file_signature": file_signature,
            "wizard_id": profile.wizard_id,
            "wizard_name": profile.wizard_name,
            "wizard_level": profile.wizard_level,
            "wizard_mana": profile.wizard_mana,
            "wizard_crystal": profile.wizard_crystal,
            "monster_count": len(profile.monsters),
            "rune_count": len(profile.runes),
            "artifact_count": len(profile.artifacts),
            "locked_runes_pve": sorted(profile.locked_runes_pve),
            "locked_runes_rta": sorted(profile.locked_runes_rta),
        }

    @classmethod
    def build_indexeddb_bridge_html(
        cls,
        monster_service: MonsterDataService,
        profile: AccountProfile | None = None,
        is_demo_mode: bool = False,
        file_signature: str = "",
        clear_account_store: bool = False,
    ) -> str:
        """
        Generates the non-blocking IndexedDB JavaScript bridge (`SWOptimizerDB`)
        that stores both the monster catalog metadata and the normalized account inventory
        asynchronously in IndexedDB (replacing synchronous 5MB `localStorage`).
        """
        monster_meta = {
            "id": f"monster_map_v{monster_service.version}",
            "version": monster_service.version,
            "updated_at": int(monster_service.updated_at or time.time()),
            "ttl_seconds": monster_service.ttl_seconds,
            "count": monster_service.size,
        }
        account_payload = cls.build_indexeddb_payload(
            profile=profile,
            is_demo_mode=is_demo_mode,
            file_signature=file_signature,
        )
        monster_meta_json = json.dumps(monster_meta, separators=(",", ":"))
        account_json = (
            json.dumps(account_payload, separators=(",", ":"))
            if account_payload is not None
            else "null"
        )
        should_clear = "true" if clear_account_store else "false"

        return f"""
        <script>
        (function() {{
            if (!("indexedDB" in window)) {{
                return;
            }}
            const DB_NAME = "{INDEXED_DB_NAME}";
            const DB_VERSION = {INDEXED_DB_VERSION};
            const STORE_ACCOUNTS = "{ACCOUNTS_OBJECT_STORE}";
            const STORE_MONSTERS = "{MONSTER_MAP_OBJECT_STORE}";
            const monsterMeta = {monster_meta_json};
            const accountPayload = {account_json};
            const clearAccountStore = {should_clear};

            const openReq = window.indexedDB.open(DB_NAME, DB_VERSION);
            openReq.onupgradeneeded = function(event) {{
                const db = event.target.result;
                if (!db.objectStoreNames.contains(STORE_ACCOUNTS)) {{
                    db.createObjectStore(STORE_ACCOUNTS, {{ keyPath: "id" }});
                }}
                if (!db.objectStoreNames.contains(STORE_MONSTERS)) {{
                    db.createObjectStore(STORE_MONSTERS, {{ keyPath: "id" }});
                }}
            }};
            openReq.onsuccess = function(event) {{
                const db = event.target.result;
                try {{
                    const tx = db.transaction([STORE_ACCOUNTS, STORE_MONSTERS], "readwrite");
                    const monsterStore = tx.objectStore(STORE_MONSTERS);
                    monsterStore.put(monsterMeta);

                    const accountStore = tx.objectStore(STORE_ACCOUNTS);
                    if (clearAccountStore) {{
                        accountStore.delete("{ACTIVE_ACCOUNT_KEY}");
                    }} else if (accountPayload !== null) {{
                        accountStore.put(accountPayload);
                    }}
                }} catch (txErr) {{
                    /* IndexedDB write skipped in restricted context */
                }}
            }};
        }})();
        </script>
        """
