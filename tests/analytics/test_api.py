import pathlib
from unittest.mock import patch


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_runs_empty(client):
    with patch("dashboard.analytics.backend.main.readers.list_runs", return_value=[]):
        r = client.get("/api/runs")
    assert r.status_code == 200
    assert r.json() == []


def test_list_runs_returns_summaries(client, tmp_runs):
    data_root, run_id = tmp_runs
    with patch("dashboard.analytics.backend.main.DATA_ROOT", data_root):
        r = client.get("/api/runs")
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 1
    assert runs[0]["run_id"] == run_id
    assert runs[0]["ebs"] == 62.5
    assert runs[0]["survival_rate"] == 0.5


def test_list_runs_with_limit_offset(client, tmp_runs):
    data_root, run_id = tmp_runs
    with patch("dashboard.analytics.backend.main.DATA_ROOT", data_root):
        r = client.get("/api/runs?limit=1&offset=0")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_run_detail_ok(client, tmp_runs):
    data_root, run_id = tmp_runs
    with patch("dashboard.analytics.backend.main.DATA_ROOT", data_root):
        r = client.get(f"/api/runs/{run_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"]["run_id"] == run_id
    assert body["metadata"]["agent_names"] == ["Alice", "Bob"]
    assert body["agents"]["final_survivors"] == ["Bob"]
    assert body["ebs"] == 62.5
    assert body["ebs_components"]["novelty"] == 75.0


def test_run_detail_404(client, tmp_runs):
    data_root, _ = tmp_runs
    with patch("dashboard.analytics.backend.main.DATA_ROOT", data_root):
        r = client.get("/api/runs/nonexistent_run_id")
    assert r.status_code == 404
