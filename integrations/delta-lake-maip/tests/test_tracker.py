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

"""Tests for the DeltaTableTracker."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from delta_lake_maip.config import DeltaMAIPConfig
from delta_lake_maip.exceptions import DeltaTableError
from delta_lake_maip.tracker import DeltaTableTracker

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_SCHEMA_JSON = json.dumps(
    {
        "type": "struct",
        "fields": [
            {"name": "id", "type": "integer", "nullable": False, "metadata": {}},
            {"name": "value", "type": "string", "nullable": True, "metadata": {}},
        ],
    }
)

EVOLVED_SCHEMA_JSON = json.dumps(
    {
        "type": "struct",
        "fields": [
            {"name": "id", "type": "integer", "nullable": False, "metadata": {}},
            {"name": "value", "type": "string", "nullable": True, "metadata": {}},
            {"name": "extra", "type": "double", "nullable": True, "metadata": {}},
        ],
    }
)


def _canonical_hash(schema_json: str) -> str:
    """Helper to compute the expected canonical hash."""
    parsed = json.loads(schema_json)
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Tests: __init__
# ---------------------------------------------------------------------------


class TestTrackerInit:
    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_successful_init(self, mock_dt_cls: MagicMock) -> None:
        """Tracker opens the Delta table on construction."""
        mock_dt_cls.return_value = MagicMock()
        tracker = DeltaTableTracker("/data/events")
        mock_dt_cls.assert_called_once_with("/data/events")

    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_init_failure_raises_delta_table_error(self, mock_dt_cls: MagicMock) -> None:
        """DeltaTableError is raised when the table cannot be opened."""
        mock_dt_cls.side_effect = Exception("Not found")
        with pytest.raises(DeltaTableError, match="Failed to open Delta table"):
            DeltaTableTracker("/bad/path")


# ---------------------------------------------------------------------------
# Tests: get_current_version
# ---------------------------------------------------------------------------


class TestGetCurrentVersion:
    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_returns_version(self, mock_dt_cls: MagicMock) -> None:
        """get_current_version returns the table's version number."""
        mock_table = MagicMock()
        mock_table.version.return_value = 42
        mock_dt_cls.return_value = mock_table

        tracker = DeltaTableTracker("/data/events")
        assert tracker.get_current_version() == 42

    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_version_failure_raises(self, mock_dt_cls: MagicMock) -> None:
        """DeltaTableError is raised when version() fails."""
        mock_table = MagicMock()
        mock_table.version.side_effect = Exception("I/O error")
        mock_dt_cls.return_value = mock_table

        tracker = DeltaTableTracker("/data/events")
        with pytest.raises(DeltaTableError, match="Failed to read version"):
            tracker.get_current_version()


# ---------------------------------------------------------------------------
# Tests: get_schema_hash
# ---------------------------------------------------------------------------


class TestGetSchemaHash:
    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_schema_hash_current(self, mock_dt_cls: MagicMock) -> None:
        """get_schema_hash with no version returns hash of latest schema."""
        mock_schema = MagicMock()
        mock_schema.to_json.return_value = SAMPLE_SCHEMA_JSON
        mock_table = MagicMock()
        mock_table.schema.return_value = mock_schema
        mock_dt_cls.return_value = mock_table

        tracker = DeltaTableTracker("/data/events")
        h = tracker.get_schema_hash()

        assert h == _canonical_hash(SAMPLE_SCHEMA_JSON)
        assert len(h) == 64

    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_schema_hash_specific_version(self, mock_dt_cls: MagicMock) -> None:
        """get_schema_hash with a version opens the table at that version."""
        mock_schema = MagicMock()
        mock_schema.to_json.return_value = SAMPLE_SCHEMA_JSON
        mock_version_table = MagicMock()
        mock_version_table.schema.return_value = mock_schema

        # First call in __init__, second call for specific version
        mock_dt_cls.side_effect = [MagicMock(), mock_version_table]

        tracker = DeltaTableTracker("/data/events")
        h = tracker.get_schema_hash(version=3)

        assert h == _canonical_hash(SAMPLE_SCHEMA_JSON)
        mock_dt_cls.assert_called_with("/data/events", version=3)

    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_schema_failure_raises(self, mock_dt_cls: MagicMock) -> None:
        """DeltaTableError is raised when schema cannot be read."""
        mock_table = MagicMock()
        mock_table.schema.side_effect = Exception("Corrupt log")
        mock_dt_cls.return_value = mock_table

        tracker = DeltaTableTracker("/data/events")
        with pytest.raises(DeltaTableError, match="Failed to read schema"):
            tracker.get_schema_hash()


# ---------------------------------------------------------------------------
# Tests: detect_schema_changes
# ---------------------------------------------------------------------------


class TestDetectSchemaChanges:
    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_no_changes(self, mock_dt_cls: MagicMock) -> None:
        """Returns None when schemas are identical."""
        mock_schema = MagicMock()
        mock_schema.to_json.return_value = SAMPLE_SCHEMA_JSON
        mock_table = MagicMock()
        mock_table.schema.return_value = mock_schema
        mock_table.history.return_value = [{"timestamp": 1700000000000}]
        mock_dt_cls.return_value = mock_table

        tracker = DeltaTableTracker("/data/events")
        result = tracker.detect_schema_changes(from_version=4, to_version=5)

        assert result is None

    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_schema_changed(self, mock_dt_cls: MagicMock) -> None:
        """Returns a schema evolution receipt when schemas differ."""
        mock_old_schema = MagicMock()
        mock_old_schema.to_json.return_value = SAMPLE_SCHEMA_JSON
        mock_old_table = MagicMock()
        mock_old_table.schema.return_value = mock_old_schema
        mock_old_table.history.return_value = [{"timestamp": 1700000000000}]

        mock_new_schema = MagicMock()
        mock_new_schema.to_json.return_value = EVOLVED_SCHEMA_JSON
        mock_new_table = MagicMock()
        mock_new_table.schema.return_value = mock_new_schema
        mock_new_table.history.return_value = [{"timestamp": 1700003600000}]

        # Calls: __init__, get_schema_json(4), get_schema_json(5), get_commit_info(5)
        mock_dt_cls.side_effect = [
            MagicMock(),  # __init__
            mock_old_table,  # version=4
            mock_new_table,  # version=5
            mock_new_table,  # commit_info version=5
        ]

        tracker = DeltaTableTracker("/data/events")
        result = tracker.detect_schema_changes(from_version=4, to_version=5)

        assert result is not None
        assert result.receipt_type == "delta_schema_evolution_receipt"
        assert "extra" in result.columns_added
        assert len(result.payload_hash) == 64

    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_schema_hash_deterministic(self, mock_dt_cls: MagicMock) -> None:
        """Same schema JSON always produces the same hash."""
        mock_schema = MagicMock()
        mock_schema.to_json.return_value = SAMPLE_SCHEMA_JSON
        mock_table = MagicMock()
        mock_table.schema.return_value = mock_schema
        mock_dt_cls.return_value = mock_table

        tracker = DeltaTableTracker("/data/events")
        h1 = tracker.get_schema_hash()
        h2 = tracker.get_schema_hash()
        assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: get_commit_info
# ---------------------------------------------------------------------------


class TestGetCommitInfo:
    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_returns_commit_info(self, mock_dt_cls: MagicMock) -> None:
        """get_commit_info returns the first history entry as a dict."""
        mock_table = MagicMock()
        mock_table.history.return_value = [
            {"timestamp": 1700000000000, "operation": "WRITE", "version": 5}
        ]
        mock_dt_cls.return_value = mock_table

        tracker = DeltaTableTracker("/data/events")
        info = tracker.get_commit_info()

        assert info["operation"] == "WRITE"
        assert info["timestamp"] == 1700000000000

    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_empty_history(self, mock_dt_cls: MagicMock) -> None:
        """An empty history returns an empty dict."""
        mock_table = MagicMock()
        mock_table.history.return_value = []
        mock_dt_cls.return_value = mock_table

        tracker = DeltaTableTracker("/data/events")
        info = tracker.get_commit_info()

        assert info == {}

    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_commit_info_failure_raises(self, mock_dt_cls: MagicMock) -> None:
        """DeltaTableError is raised when history() fails."""
        mock_table = MagicMock()
        mock_table.history.side_effect = Exception("Log corrupt")
        mock_dt_cls.return_value = mock_table

        tracker = DeltaTableTracker("/data/events")
        with pytest.raises(DeltaTableError, match="Failed to read commit info"):
            tracker.get_commit_info()


# ---------------------------------------------------------------------------
# Tests: reload
# ---------------------------------------------------------------------------


class TestReload:
    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_reload_recreates_table(self, mock_dt_cls: MagicMock) -> None:
        """reload() re-opens the Delta table."""
        mock_dt_cls.return_value = MagicMock()

        tracker = DeltaTableTracker("/data/events")
        tracker.reload()

        # Called twice: once in __init__, once in reload
        assert mock_dt_cls.call_count == 2

    @patch("delta_lake_maip.tracker.DeltaTable")
    def test_reload_failure_raises(self, mock_dt_cls: MagicMock) -> None:
        """DeltaTableError is raised when reload fails."""
        mock_dt_cls.side_effect = [MagicMock(), Exception("Table deleted")]

        tracker = DeltaTableTracker("/data/events")
        with pytest.raises(DeltaTableError, match="Failed to reload"):
            tracker.reload()
