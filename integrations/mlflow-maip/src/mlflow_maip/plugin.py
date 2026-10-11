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

"""MLflow tracking-store plugin that generates MAIP receipts on run completion.

When this plugin is registered as an MLflow tracking-store entry point, it
wraps the underlying store (file or SQL) and intercepts lifecycle events
(``set_terminated``, ``log_metric``) to automatically create MAIP receipts.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mlflow.entities import Run, RunStatus, ViewType
from mlflow.store.tracking.file_store import FileStore
from mlflow.store.tracking.abstract_store import AbstractStore

from mlflow_maip.client import MAIPClient
from mlflow_maip.config import MAIPConfig
from mlflow_maip.exceptions import MAIPError
from mlflow_maip.receipts import generate_receipt_from_run

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from synchronous code, handling event-loop reuse."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We are already inside an event loop (e.g. Jupyter / async MLflow).
        # Schedule the coroutine and return a future; the caller won't await it.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


class MAIPTrackingStore(AbstractStore):
    """Tracking store wrapper that emits MAIP receipts on run termination.

    This class delegates all operations to an inner ``FileStore`` (or any other
    concrete store) and hooks into ``set_terminated`` to trigger receipt
    generation.

    Args:
        store_uri: The tracking store URI (passed by MLflow).
        artifact_uri: The default artifact root (passed by MLflow).
    """

    RECEIPT_TAG_KEY = "maip.receipt_id"
    RECEIPT_HASH_TAG_KEY = "maip.payload_hash"

    def __init__(self, store_uri: str, artifact_uri: str | None = None) -> None:
        self._config = MAIPConfig()
        if store_uri.startswith("maip:sqlite:"):
            from mlflow.store.tracking.sqlalchemy_store import SqlAlchemyStore
            from pathlib import Path
            self._inner = SqlAlchemyStore(store_uri[len("maip:"):], artifact_uri or (Path.cwd() / "mlartifacts").as_uri())
        else:
            if store_uri.startswith("maip:"):
                store_uri = "file:" + store_uri[len("maip:"):]
            self._inner = FileStore(store_uri, artifact_uri)
        self._client = MAIPClient(self._config)
        self.last_receipt_error: Exception | None = None
        super().__init__()

    # ------------------------------------------------------------------
    # Receipt generation
    # ------------------------------------------------------------------

    def _create_receipt_for_run(self, run_id: str) -> None:
        """Attempt to create a MAIP receipt for the given run.

        Failures are logged but never propagated so that the core MLflow
        workflow is never interrupted by MAIP issues.
        """
        if not self._config.auto_receipt:
            return

        try:
            run = self._inner.get_run(run_id)
            receipt_payload = generate_receipt_from_run(run, self._config)
            response = self._client.create_receipt_sync(receipt_payload)
            self.last_receipt_error = None
            # Tag the run with the receipt ID for traceability
            self._inner.set_tag(run_id, _make_tag(self.RECEIPT_TAG_KEY, response.receipt_id))
            self._inner.set_tag(
                run_id,
                _make_tag(self.RECEIPT_HASH_TAG_KEY, receipt_payload.payload_hash),
            )
            logger.info(
                "MAIP receipt %s created for run %s",
                response.receipt_id,
                run_id,
            )
        except MAIPError as error:
            self.last_receipt_error = error
            self._inner.set_tag(run_id, _make_tag("maip.receipt_status", "delivery_failed"))
            logger.exception("Failed to create MAIP receipt for run %s", run_id)
        except Exception as error:
            self.last_receipt_error = error
            logger.exception("Unexpected error creating MAIP receipt for run %s", run_id)

    # ------------------------------------------------------------------
    # Delegated AbstractStore methods
    # ------------------------------------------------------------------

    def search_experiments(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.search_experiments(*args, **kwargs)

    def create_experiment(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.create_experiment(*args, **kwargs)

    def get_experiment(self, experiment_id: str) -> Any:
        return self._inner.get_experiment(experiment_id)

    def get_experiment_by_name(self, experiment_name: str) -> Any:
        return self._inner.get_experiment_by_name(experiment_name)

    def delete_experiment(self, experiment_id: str) -> None:
        self._inner.delete_experiment(experiment_id)

    def restore_experiment(self, experiment_id: str) -> None:
        self._inner.restore_experiment(experiment_id)

    def rename_experiment(self, experiment_id: str, new_name: str) -> None:
        self._inner.rename_experiment(experiment_id, new_name)

    def get_run(self, run_id: str) -> Run:
        return self._inner.get_run(run_id)

    def update_run_info(self, run_id: str, run_status: Any, end_time: int, run_name: str) -> Any:
        result = self._inner.update_run_info(run_id, run_status, end_time, run_name)
        # Create receipt when the run reaches a terminal state
        if run_status in (
            RunStatus.FINISHED,
            RunStatus.FAILED,
            RunStatus.KILLED,
            RunStatus.to_string(RunStatus.FINISHED),
            RunStatus.to_string(RunStatus.FAILED),
            RunStatus.to_string(RunStatus.KILLED),
            "FINISHED",
            "FAILED",
            "KILLED",
        ):
            self._create_receipt_for_run(run_id)
        return result

    def create_run(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.create_run(*args, **kwargs)

    def delete_run(self, run_id: str) -> None:
        self._inner.delete_run(run_id)

    def restore_run(self, run_id: str) -> None:
        self._inner.restore_run(run_id)

    def log_metric(self, run_id: str, metric: Any) -> None:
        self._inner.log_metric(run_id, metric)

    def log_param(self, run_id: str, param: Any) -> None:
        self._inner.log_param(run_id, param)

    def set_experiment_tag(self, experiment_id: str, tag: Any) -> None:
        self._inner.set_experiment_tag(experiment_id, tag)

    def set_tag(self, run_id: str, tag: Any) -> None:
        self._inner.set_tag(run_id, tag)

    def get_metric_history(self, run_id: str, metric_key: str, *args: Any, **kwargs: Any) -> Any:
        return self._inner.get_metric_history(run_id, metric_key, *args, **kwargs)

    def search_runs(
        self,
        experiment_ids: list[str],
        filter_string: str,
        run_view_type: ViewType,
        max_results: int = 1000,
        order_by: list[str] | None = None,
        page_token: str | None = None,
    ) -> Any:
        return self._inner.search_runs(
            experiment_ids,
            filter_string,
            run_view_type,
            max_results,
            order_by,
            page_token,
        )

    def log_batch(self, run_id: str, metrics: Any, params: Any, tags: Any) -> None:
        self._inner.log_batch(run_id, metrics, params, tags)

    def record_logged_model(self, run_id: str, mlflow_model: Any) -> None:
        self._inner.record_logged_model(run_id, mlflow_model)


class MAIPTrackingStoreFactory:
    """Factory registered as an MLflow tracking-store entry point.

    MLflow calls ``__init__`` with ``(store_uri, artifact_uri)`` and expects
    an object whose ``.create_store`` or direct call returns an
    ``AbstractStore`` instance.
    """

    def __call__(self, store_uri: str, artifact_uri: str | None = None) -> MAIPTrackingStore:
        return MAIPTrackingStore(store_uri, artifact_uri)

    def create_store(self, store_uri: str, artifact_uri: str | None = None) -> MAIPTrackingStore:
        """Create a ``MAIPTrackingStore`` wrapping the given URI."""
        return MAIPTrackingStore(store_uri, artifact_uri)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_tag(key: str, value: str) -> Any:
    """Create an MLflow ``RunTag`` entity."""
    from mlflow.entities import RunTag

    return RunTag(key, value)
