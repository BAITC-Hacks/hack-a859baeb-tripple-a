"""HTTP boundary for document ingestion and persisted background analysis."""
from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from .database import Store
from .errors import AnalysisError
from .ingestion import MAX_FILE_BYTES, IngestionError, ingest_document
from .models import AnalysisResult, Document

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MAX_TOTAL_BYTES = 60 * 1024 * 1024
MAX_FILES_PER_SIDE = 10
logger = logging.getLogger(__name__)
analysis_slots = threading.BoundedSemaphore(2)


def run_pipeline(documents: list[Document], mode: str, progress: Callable[[int, str], None]) -> AnalysisResult:
    from .pipeline import run_pipeline as implementation
    return implementation(documents, mode, progress)


def _configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _validate_mode(mode: str) -> None:
    if mode not in ("local", "openai"):
        raise HTTPException(422, "Mode must be local or openai.")
    if mode == "openai" and not _configured():
        raise HTTPException(400, "OpenAI is not configured. Set OPENAI_API_KEY in the server environment, or choose local review.")


def _title(value: str) -> str:
    value = " ".join(value.split()).strip()
    if not value:
        return "Organizational change analysis"
    if len(value) > 160:
        raise HTTPException(422, "Analysis title must be at most 160 characters.")
    return value


def _execute(store: Store, analysis_id: str, documents: list[Document], mode: str) -> None:
    try:
        with analysis_slots:
            store.progress(analysis_id, 0, "Reading documents complete")
            result = run_pipeline(documents, mode, lambda stage, label: store.progress(analysis_id, stage, label))
            store.complete(analysis_id, result)
    except Exception as exc:  # noqa: BLE001 - background boundary must persist every failure safely.
        # Never persist raw upstream error text: it can contain credentials or
        # document content. Detailed class is sufficient for server diagnosis.
        logger.error("Analysis %s failed (%s)", analysis_id, type(exc).__name__)
        name = type(exc).__name__
        if isinstance(exc, AnalysisError):
            message = str(exc)
        elif name in {"AuthenticationError", "PermissionDeniedError"}:
            message = "OpenAI rejected the API credentials. Check the server's OPENAI_API_KEY and project permissions."
        elif name == "RateLimitError":
            message = "OpenAI rate or account limits were reached. Check API quota and retry."
        elif name in {"APIConnectionError", "APITimeoutError"}:
            message = "Could not reach OpenAI. Check connectivity and retry."
        else:
            message = "The analysis could not be completed safely. Check the documents and server logs, then retry."
        store.fail(analysis_id, message)


def create_app(db_path: str | Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store.interrupt_stale()
        yield

    app = FastAPI(title="AlemScope API", version="1.0.0", lifespan=lifespan)
    app.state.store = Store(db_path or os.getenv("DATABASE_PATH", str(ROOT / "data" / "alemscope.sqlite3")))

    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):
        length = request.headers.get("content-length")
        if request.method == "POST" and length:
            try:
                if int(length) > MAX_TOTAL_BYTES + 1024 * 1024:
                    from fastapi.responses import JSONResponse
                    return JSONResponse(status_code=413, content={"detail": "Upload exceeds the 60 MB total limit."})
            except ValueError:
                from fastapi.responses import JSONResponse
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length header."})
        return await call_next(request)

    def get_analysis(analysis_id: str) -> dict:
        analysis = app.state.store.get(analysis_id)
        if analysis is None:
            raise HTTPException(404, "Analysis not found.")
        return analysis

    def queue(documents: list[Document], title: str, mode: str, background: BackgroundTasks) -> dict:
        if len({document.id for document in documents}) != len(documents):
            raise HTTPException(422, "The same document was uploaded more than once in a group. Remove duplicate files.")
        analysis = app.state.store.create(_title(title), mode, documents)
        background.add_task(_execute, app.state.store, analysis["id"], documents, mode)
        return analysis

    @app.get("/api/health")
    def health():
        return {"status": "ok", "openai_configured": _configured(), "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini")}

    @app.get("/api/analyses")
    def list_analyses():
        return app.state.store.list()

    @app.post("/api/analyses", status_code=202)
    async def create_analysis(
        background: BackgroundTasks,
        before_files: Annotated[list[UploadFile], File()],
        after_files: Annotated[list[UploadFile], File()],
        title: str = Form("Organizational change analysis"),
        mode: Literal["local", "openai"] = Form("local"),
    ):
        _validate_mode(mode)
        title = _title(title)
        if not before_files or not after_files:
            raise HTTPException(422, "Upload at least one BEFORE and one AFTER document.")
        if max(len(before_files), len(after_files)) > MAX_FILES_PER_SIDE:
            raise HTTPException(422, "Upload at most 10 files in each group.")
        total = 0
        documents: list[Document] = []
        try:
            for side, files in (("before", before_files), ("after", after_files)):
                for upload in files:
                    content = await upload.read(MAX_FILE_BYTES + 1)
                    total += len(content)
                    if total > MAX_TOTAL_BYTES:
                        raise HTTPException(413, "Upload exceeds the 60 MB total limit.")
                    try:
                        documents.append(await run_in_threadpool(ingest_document, upload.filename or "document", content, side))
                    except IngestionError as exc:
                        raise HTTPException(422, str(exc)) from exc
        finally:
            for upload in before_files + after_files:
                await upload.close()
        return queue(documents, title, mode, background)

    @app.post("/api/analyses/demo", status_code=202)
    async def demo_analysis(
        request: Request, background: BackgroundTasks,
        mode: str = Query("local"), title: str = Query("Internal audit · revision 8 → 9"),
    ):
        if request.headers.get("content-type", "").startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
            form = await request.form()
            mode = str(form.get("mode", mode))
            title = str(form.get("title", title))
        _validate_mode(mode)
        documents: list[Document] = []
        filenames = {}
        manifest_path = ROOT / "fixtures" / "manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                filenames = {item["side"]: item["original_filename"] for item in manifest.get("documents", [])}
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                logger.warning("Fixture manifest could not be read; using local fixture filenames.")
        for side in ("before", "after"):
            path = ROOT / "fixtures" / f"{side}.pdf"
            if not path.is_file():
                raise HTTPException(404, "Demo documents are unavailable. Run python scripts/import_fixtures.py, or upload your own BEFORE and AFTER files.")
            try:
                documents.append(await run_in_threadpool(ingest_document, filenames.get(side, path.name), path.read_bytes(), side))
            except IngestionError as exc:
                raise HTTPException(422, str(exc)) from exc
        return queue(documents, title, mode, background)

    @app.get("/api/analyses/{analysis_id}")
    def read_analysis(analysis_id: str):
        return get_analysis(analysis_id)

    @app.get("/api/analyses/{analysis_id}/report")
    def report(analysis_id: str):
        analysis = get_analysis(analysis_id)
        if analysis["status"] != "completed" or not analysis["result"]:
            raise HTTPException(409, "The report is available after the analysis completes.")
        return Response(analysis["result"]["report"], media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="alemscope-{analysis_id}.md"'})

    @app.delete("/api/analyses/{analysis_id}", status_code=204)
    def delete_analysis(analysis_id: str):
        analysis = get_analysis(analysis_id)
        if analysis["status"] not in ("completed", "failed"):
            raise HTTPException(409, "An analysis cannot be deleted while it is running.")
        app.state.store.delete(analysis_id)
        return Response(status_code=204)

    return app


app = create_app()
