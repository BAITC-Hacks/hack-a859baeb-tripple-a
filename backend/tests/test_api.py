import io

import pytest
from app import main
from app.database import Store
from app.ingestion import ingest_document
from app.models import AnalysisResult
from docx import Document as DocxDocument
from fastapi.testclient import TestClient


def document_bytes(text="Audit Department reviews internal controls."):
    doc = DocxDocument()
    doc.add_paragraph(text)
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = main.create_app(tmp_path / "analyses.sqlite3")

    def fake_pipeline(documents, mode, progress):
        assert {doc.side for doc in documents} == {"before", "after"}
        for stage in range(1, 8):
            progress(stage, f"Stage {stage}")
        return AnalysisResult(units=[], functions=[], unit_mappings=[], function_mappings=[],
                              findings=[], warnings=[], summary={"units_before": 0},
                              report="# Verified report\n\nHuman validation required.")

    monkeypatch.setattr(main, "run_pipeline", fake_pipeline)
    with TestClient(app) as test_client:
        yield test_client


def upload(client, mode="local"):
    return client.post("/api/analyses", data={"title": "Audit policy comparison", "mode": mode}, files=[
        ("before_files", ("before.docx", document_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ("after_files", ("after.docx", document_bytes("Audit Department reviews controls and risks."), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
    ])


def test_health_and_analysis_flow_persistence_report_delete(client):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["openai_configured"] is False
    created = upload(client)
    assert created.status_code == 202, created.text
    assert created.json()["status"] == "queued"
    analysis_id = created.json()["id"]
    completed = client.get(f"/api/analyses/{analysis_id}").json()
    assert completed["status"] == "completed"
    assert completed["stage"] == 7
    assert len(completed["documents"]) == 2
    assert completed["documents"][0]["chunks"][0]["paragraph"] == 1
    persisted = Store(client.app.state.store.path).get(analysis_id)
    assert persisted["result"] == completed["result"]
    recent = client.get("/api/analyses").json()
    assert recent[0]["id"] == analysis_id
    assert "documents" not in recent[0] and "result" not in recent[0]
    report = client.get(f"/api/analyses/{analysis_id}/report")
    assert report.status_code == 200
    assert "Verified report" in report.text
    assert "attachment" in report.headers["content-disposition"]
    assert client.delete(f"/api/analyses/{analysis_id}").status_code == 204
    assert client.get(f"/api/analyses/{analysis_id}").status_code == 404
    with client.app.state.store.connect() as db:
        assert db.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0


def test_requires_both_upload_groups_and_rejects_invalid_files(client):
    response = client.post("/api/analyses", files={"before_files": ("before.docx", document_bytes())})
    assert response.status_code == 422
    response = client.post("/api/analyses", files=[
        ("before_files", ("bad.exe", b"executable")),
        ("after_files", ("after.docx", document_bytes())),
    ])
    assert response.status_code == 422
    assert "Supported formats" in response.json()["detail"]
    assert client.get("/api/analyses").json() == []


def test_openai_mode_requires_environment_key(client):
    response = upload(client, "openai")
    assert response.status_code == 400
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_duplicate_documents_are_rejected(client):
    content = document_bytes()
    response = client.post("/api/analyses", files=[
        ("before_files", ("one.docx", content)),
        ("before_files", ("duplicate.docx", content)),
        ("after_files", ("after.docx", content)),
    ])
    assert response.status_code == 422
    assert "more than once" in response.json()["detail"]


def test_background_failure_is_persisted_without_secret_leak(client, monkeypatch):
    def failure(*args, **kwargs):
        raise RuntimeError("Authorization: sk-sensitive-secret should never be returned")
    monkeypatch.setattr(main, "run_pipeline", failure)
    created = upload(client)
    state = client.get(f"/api/analyses/{created.json()['id']}")
    assert state.json()["status"] == "failed"
    assert "sk-sensitive" not in state.text
    assert client.get(f"/api/analyses/{created.json()['id']}/report").status_code == 409


def test_known_pipeline_limit_has_actionable_safe_error(client, monkeypatch):
    from app.errors import AnalysisError

    def failure(*args, **kwargs):
        raise AnalysisError("This document set exceeds the prototype limit. Split it into smaller sets.")

    monkeypatch.setattr(main, "run_pipeline", failure)
    created = upload(client)
    state = client.get(f"/api/analyses/{created.json()['id']}").json()
    assert state["status"] == "failed"
    assert "Split it into smaller sets" in state["error"]


def test_actual_local_pipeline_from_upload_to_evidenced_report(client, monkeypatch):
    from app.pipeline import run_pipeline

    monkeypatch.setattr(main, "run_pipeline", run_pipeline)
    created = client.post("/api/analyses", data={"mode": "local"}, files=[
        ("before_files", ("before.docx", document_bytes("Audit Department reviews and approves every internal control process."))),
        ("after_files", ("after.docx", document_bytes("Risk Department maintains the enterprise incident register and coordinates quarterly risk workshops."))),
    ])
    assert created.status_code == 202
    result = client.get(f"/api/analyses/{created.json()['id']}").json()
    assert result["status"] == "completed", result.get("error")
    assert len(result["result"]["units"]) >= 2
    assert len(result["result"]["functions"]) >= 2
    assert result["result"]["findings"]
    chunks = {chunk["id"]: chunk for doc in result["documents"] for chunk in doc["chunks"]}
    for finding in result["result"]["findings"]:
        assert finding["requires_review"] is True
        assert finding["evidence"]
        assert all(ev["quote"] in chunks[ev["chunk_id"]]["text"] for ev in finding["evidence"])
    assert "## Evidence references" in result["result"]["report"]


def test_running_analyses_cannot_be_deleted_and_restart_recovers(tmp_path):
    db_path = tmp_path / "recovery.sqlite3"
    app = main.create_app(db_path)
    with TestClient(app) as client:
        document = ingest_document("source.docx", document_bytes(), "before")
        analysis = app.state.store.create("Interrupted analysis", "local", [document])
        assert client.delete(f"/api/analyses/{analysis['id']}").status_code == 409
    with TestClient(main.create_app(db_path)) as client:
        restored = client.get(f"/api/analyses/{analysis['id']}").json()
        assert restored["status"] == "failed"
        assert "server stopped" in restored["error"]


def test_missing_demo_fixtures_have_actionable_error(client, monkeypatch, tmp_path):
    monkeypatch.setattr(main, "ROOT", tmp_path)
    response = client.post("/api/analyses/demo")
    assert response.status_code == 404
    assert "import_fixtures.py" in response.json()["detail"]


def test_total_upload_limit(client):
    response = client.post("/api/analyses", headers={"Content-Length": str(main.MAX_TOTAL_BYTES + 2 * 1024 * 1024)})
    assert response.status_code == 413
