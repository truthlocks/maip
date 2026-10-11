"""Real MLflow lifecycle with an HTTP fixture at the external API boundary."""
import json
import httpx
import respx
import pytest
from mlflow.entities import RunStatus
from mlflow_maip.entrypoint import create_store


@pytest.mark.parametrize('backend', ['file', 'sqlite'])
def test_real_store_finishes_run_and_confirms_receipt(tmp_path, monkeypatch, backend):
    monkeypatch.setenv('MAIP_API_KEY', 'tl_test_fixture')
    monkeypatch.setenv('MAIP_AGENT_ID', 'maip:qa')
    monkeypatch.setenv('MLFLOW_ALLOW_FILE_STORE', 'true')
    uri = (tmp_path / 'mlruns').as_uri().replace('file:', 'maip:', 1) if backend == 'file' else 'maip:sqlite:///' + (tmp_path / 'mlflow.db').as_posix()
    store = create_store(uri, (tmp_path / 'artifacts').as_uri())
    experiment = store.create_experiment('QA local integration')
    run = store.create_run(experiment, 'qa', 1, [], 'QA run')
    with respx.mock as router:
        route = router.post('https://sandbox-api.truthlocks.com/v1/agent-receipts').mock(
            return_value=httpx.Response(201, json={'receipt_id': 'maip-receipt:qa', 'status': 'valid'}))
        store.update_run_info(run.info.run_id, RunStatus.FINISHED, 2, 'QA run')
        assert route.call_count == 1
        assert json.loads(route.calls[0].request.content)['metadata']['run_id'] == run.info.run_id
    saved = store.get_run(run.info.run_id)
    assert saved.info.status == 'FINISHED'
    assert saved.data.tags['maip.receipt_id'] == 'maip-receipt:qa'
    assert store.last_receipt_error is None
