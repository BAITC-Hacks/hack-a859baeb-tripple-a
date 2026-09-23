import hashlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
import httpx
from fastapi import FastAPI, Depends, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session as DBSession
from .db import Base, engine, Session, Project, Document, Fragment, Analysis
from .schemas import ProjectInput, RunInput
from .parsers import extract
from .analysis import demo, ollama, validate_and_enrich

STORAGE = Path(os.getenv('STORAGE_DIR', './data/uploads')).resolve()
MAX_UPLOAD = 15 * 1024 * 1024

@asynccontextmanager
async def lifespan(app):
    STORAGE.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    yield

app = FastAPI(title='Org Agent — анализ организационных изменений', version='0.1.0', lifespan=lifespan,
              description='Тестовый backend. Demo — правила, ollama — локальная модель. Все выводы требуют проверки.')

def session():
    with Session() as db: yield db

def require(db, model, id):
    obj = db.get(model, id)
    if not obj: raise HTTPException(404, 'Объект не найден')
    return obj

def document_json(d):
    return {'id': d.id, 'project_id': d.project_id, 'phase': d.phase, 'name': d.name,
            'sha256': d.sha256, 'warnings': d.warnings, 'download_url': f'/documents/{d.id}/download'}

@app.get('/health')
def health(db: DBSession = Depends(session)):
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'database': engine.dialect.name}

@app.post('/projects', status_code=201)
def create_project(body: ProjectInput, db: DBSession = Depends(session)):
    if not body.name.strip(): raise HTTPException(422, 'Название не должно быть пустым')
    p = Project(name=body.name.strip()); db.add(p); db.commit()
    return {'id': p.id, 'name': p.name}

@app.get('/projects')
def projects(db: DBSession = Depends(session)):
    return [{'id': p.id, 'name': p.name, 'created_at': p.created_at} for p in db.scalars(select(Project).order_by(Project.created_at))]

@app.post('/projects/{project_id}/documents', status_code=201)
def upload(project_id: str, phase: str = Form(...), file: UploadFile = File(...), db: DBSession = Depends(session)):
    require(db, Project, project_id)
    if phase not in {'before', 'after'}: raise HTTPException(422, 'phase: before или after')
    raw = file.file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD: raise HTTPException(413, 'Максимальный размер файла 15 МБ')
    name = Path((file.filename or 'document').replace('\\', '/')).name[:255]
    digest = hashlib.sha256(raw).hexdigest()
    existing = db.scalar(select(Document).where(Document.project_id==project_id, Document.phase==phase, Document.sha256==digest))
    if existing: return document_json(existing)
    try: fragments, warnings = extract(name, raw)
    except Exception as e:
        if isinstance(e, ValueError): raise HTTPException(422, str(e)) from e
        raise HTTPException(422, 'Не удалось прочитать документ: проверьте формат и целостность') from e
    path = STORAGE / (str(uuid4()) + Path(name).suffix.lower())
    path.write_bytes(raw)
    try:
        d = Document(project_id=project_id, phase=phase, name=name, sha256=digest, path=str(path), warnings=warnings)
        db.add(d); db.flush()
        for i, f in enumerate(fragments): db.add(Fragment(document_id=d.id, ordinal=i, **f))
        db.commit()
    except Exception:
        db.rollback(); path.unlink(missing_ok=True); raise
    return document_json(d)

@app.get('/projects/{project_id}/documents')
def documents(project_id: str, db: DBSession = Depends(session)):
    require(db, Project, project_id)
    return [document_json(d) for d in db.scalars(select(Document).where(Document.project_id==project_id))]

@app.get('/documents/{document_id}/fragments')
def fragments(document_id: str, db: DBSession = Depends(session)):
    require(db, Document, document_id)
    return [{'id': f.id, 'text': f.text, 'locator': f.locator} for f in db.scalars(select(Fragment).where(Fragment.document_id==document_id).order_by(Fragment.ordinal))]

@app.get('/documents/{document_id}/download')
def download(document_id: str, db: DBSession = Depends(session)):
    d = require(db, Document, document_id)
    if not Path(d.path).is_file(): raise HTTPException(404, 'Исходный файл недоступен')
    return FileResponse(d.path, filename=d.name, media_type='application/octet-stream')

@app.post('/projects/{project_id}/analyses', status_code=201)
def analyze(project_id: str, body: RunInput, db: DBSession = Depends(session)):
    require(db, Project, project_id)
    docs = list(db.scalars(select(Document).where(Document.project_id==project_id).order_by(Document.created_at, Document.id)))
    if {d.phase for d in docs} != {'before', 'after'}: raise HTTPException(422, 'Загрузите документы обоих комплектов')
    rows = []
    for d in docs:
        for f in db.scalars(select(Fragment).where(Fragment.document_id==d.id).order_by(Fragment.ordinal)):
            rows.append({'id': f.id, 'document_id': d.id, 'document_name': d.name, 'phase': d.phase,
                         'text': f.text, 'locator': f.locator, 'download_url': f'/documents/{d.id}/download'})
    if sum(len(r['text']) for r in rows) > 150_000 or len(rows)>3000:
        raise HTTPException(422, 'Комплект превышает лимит MVP: 150 000 символов или 3000 фрагментов')
    try:
        report = demo(rows) if body.mode=='demo' else ollama(rows)
        if len(report.functions)>500: raise ValueError('MVP: не более 500 извлечённых функций')
        result = validate_and_enrich(report, rows)
    except ValueError as e: raise HTTPException(422, str(e)) from e
    except (httpx.HTTPError, KeyError, TypeError) as e:
        raise HTTPException(502, 'Модель недоступна или вернула некорректный ответ') from e
    result['warnings'] = [w for d in docs for w in d.warnings] + [
        'Отсутствие функции в комплекте не доказывает её фактическую утрату.',
        'Проверка цитат подтверждает источник, но не логическую правильность вывода.',
        'Demo использует ограниченные правила и не является семантическим ИИ-анализом.' if body.mode=='demo' else 'Результат локальной модели требует экспертной проверки.']
    result['provenance'] = {'document_ids': [d.id for d in docs], 'sha256': {d.id:d.sha256 for d in docs},
                            'engine': body.mode, 'engine_version': '0.1.0', 'model': os.getenv('OLLAMA_MODEL') if body.mode=='ollama' else None}
    a = Analysis(project_id=project_id, mode=body.mode, result=result); db.add(a); db.commit()
    return {'id': a.id, 'project_id': project_id, 'mode': a.mode, 'result': result}

@app.get('/projects/{project_id}/analyses')
def analyses(project_id: str, db: DBSession = Depends(session)):
    require(db, Project, project_id)
    return [{'id': a.id, 'mode': a.mode, 'created_at': a.created_at} for a in db.scalars(select(Analysis).where(Analysis.project_id==project_id))]

@app.get('/analyses/{analysis_id}')
def get_analysis(analysis_id: str, db: DBSession = Depends(session)):
    a = require(db, Analysis, analysis_id)
    return {'id': a.id, 'project_id': a.project_id, 'mode': a.mode, 'created_at': a.created_at, 'result': a.result}
