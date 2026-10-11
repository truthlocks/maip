# Copyright 2026 Truthlocks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Delta table state tracker with schema-evolution detection."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from deltalake import DeltaTable

from delta_lake_maip.config import DeltaMAIPConfig
from delta_lake_maip.exceptions import DeltaTableError
from delta_lake_maip.receipts import generate_schema_evolution_receipt
from delta_lake_maip.schemas import DeltaSchemaEvolutionReceipt

logger = logging.getLogger(__name__)


class DeltaTableTracker:
    """Tracks Delta table state and detects schema evolution.

    Wraps a ``deltalake.DeltaTable`` instance to provide version querying,
    deterministic schema hashing, and automatic schema-diff receipt
    generation between arbitrary version pairs.

    Args:
        table_path: Filesystem path or URI of the Delta table.
        config: Optional plugin configuration for receipt generation.
    """

    def __init__(
        self,
        table_path: str,
        config: DeltaMAIPConfig | None = None,
    ) -> None:
        self._table_path = table_path
        self._config = config or DeltaMAIPConfig()
        try:
            self._table = DeltaTable(table_path)
        except Exception as exc:
            raise DeltaTableError(
                f"Failed to open Delta table at {table_path}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Version queries
    # ------------------------------------------------------------------

    def get_current_version(self) -> int:
        """Return the latest committed version of the Delta table.

        Returns:
            The current Delta table version number.

        Raises:
            DeltaTableError: If the version cannot be determined.
        """
        try:
            return self._table.version()
        except Exception as exc:
            raise DeltaTableError(
                f"Failed to read version for {self._table_path}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Schema hashing
    # ------------------------------------------------------------------

    def get_schema_json(self, version: int | None = None) -> str:
        """Return the schema JSON string at a given version.

        When *version* is ``None`` the current (latest) version is used.

        Args:
            version: Delta version number.  ``None`` means latest.

        Returns:
            The raw JSON string of the table schema.

        Raises:
            DeltaTableError: If the schema cannot be read.
        """
        try:
            if version is not None:
                table = DeltaTable(self._table_path, version=version)
            else:
                table = self._table
            return table.schema().to_json()
        except Exception as exc:
            raise DeltaTableError(
                f"Failed to read schema at version {version} for {self._table_path}: {exc}"
            ) from exc

    def get_schema_hash(self, version: int | None = None) -> str:
        """Compute a deterministic SHA-256 hash of the table schema.

        The schema JSON is parsed, re-serialised with sorted keys and compact
        separators, then hashed.  This ensures logically equivalent schemas
        always produce the same digest.

        Args:
            version: Delta version number.  ``None`` means latest.

        Returns:
            A lowercase hex-encoded SHA-256 digest of the canonical schema.

        Raises:
            DeltaTableError: If the schema cannot be read.
        """
        schema_json = self.get_schema_json(version)
        parsed = json.loads(schema_json)
        canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ------------------------------------------------------------------
    # Schema evolution detection
    # ------------------------------------------------------------------

    def detect_schema_changes(
        self,
        from_version: int,
        to_version: int,
    ) -> DeltaSchemaEvolutionReceipt | None:
        """Compare schemas between two versions and return a receipt if they differ.

        If the schemas are identical, ``None`` is returned.

        Args:
            from_version: The earlier Delta version (baseline).
            to_version: The later Delta version to compare against.

        Returns:
            A ``DeltaSchemaEvolutionReceipt`` if the schema changed, else ``None``.

        Raises:
            DeltaTableError: If either schema cannot be read.
        """
        previous_json = self.get_schema_json(from_version)
        new_json = self.get_schema_json(to_version)

        prev_hash = self._canonical_hash(previous_json)
        new_hash = self._canonical_hash(new_json)

        if prev_hash == new_hash:
            return None

        # Determine commit timestamp from the target version's metadata
        commit_timestamp = self._get_commit_timestamp(to_version)

        return generate_schema_evolution_receipt(
            table_path=self._table_path,
            version=to_version,
            previous_schema_json=previous_json,
            new_schema_json=new_json,
            commit_timestamp=commit_timestamp,
            config=self._config,
        )

    # ------------------------------------------------------------------
    # Transaction log helpers
    # ------------------------------------------------------------------

    def get_commit_info(self, version: int | None = None) -> dict[str, Any]:
        """Extract ``commitInfo`` from the transaction log at a given version.

        Args:
            version: Delta version number.  ``None`` means latest.

        Returns:
            The ``commitInfo`` dict, or an empty dict if unavailable.

        Raises:
            DeltaTableError: If the transaction log cannot be read.
        """
        try:
            if version is not None:
                table = DeltaTable(self._table_path, version=version)
            else:
                table = self._table

            history = table.history(limit=1)
            if history:
                return dict(history[0])
            return {}
        except Exception as exc:
            raise DeltaTableError(
                f"Failed to read commit info at version {version}: {exc}"
            ) from exc

    def get_add_actions(self, version: int | None = None) -> list[dict[str, Any]]:
        """Return the ``add`` actions from the transaction log at a given version.

        Args:
            version: Delta version number.  ``None`` means latest.

        Returns:
            A list of add-action dicts.

        Raises:
            DeltaTableError: If the transaction log cannot be read.
        """
        try:
            if version is not None:
                table = DeltaTable(self._table_path, version=version)
            else:
                table = self._table
            files = table.get_add_actions(flatten=True).to_pydict()
            # Convert column-oriented dict to list of row dicts
            if not files:
                return []
            keys = list(files.keys())
            num_rows = len(files[keys[0]]) if keys else 0
            return [
                {k: files[k][i] for k in keys}
                for i in range(num_rows)
            ]
        except Exception as exc:
            raise DeltaTableError(
                f"Failed to read add actions at version {version}: {exc}"
            ) from exc

    def reload(self) -> None:
        """Reload the Delta table to pick up new commits.

        Call this after external writes to refresh the internal state.
        """
        try:
            self._table = DeltaTable(self._table_path)
        except Exception as exc:
            raise DeltaTableError(
                f"Failed to reload Delta table at {self._table_path}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _canonical_hash(schema_json: str) -> str:
        """Return the SHA-256 digest of a canonicalised schema JSON string."""
        parsed = json.loads(schema_json)
        canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _get_commit_timestamp(self, version: int) -> int:
        """Return the commit timestamp for a given version.

        Falls back to ``0`` if the timestamp cannot be determined.
        """
        try:
            info = self.get_commit_info(version)
            ts = info.get("timestamp", 0)
            return int(ts) if ts is not None else 0
        except DeltaTableError:
            logger.warning("Could not determine commit timestamp for version %d", version)
            return 0
