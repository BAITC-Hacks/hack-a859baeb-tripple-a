"""Run against the actual HTTP server: python demo.py."""
import json
import os
from pathlib import Path
import httpx

with httpx.Client(base_url=os.getenv('API_URL', 'http://localhost:8000'), timeout=240) as c:
    r = c.post('/projects', json={'name': 'Контрольный комплект'}); r.raise_for_status()
    pid = r.json()['id']
    for phase in ['before', 'after']:
        path = Path(__file__).parent / 'examples' / f'{phase}.txt'
        r = c.post(f'/projects/{pid}/documents', data={'phase': phase}, files={'file': (path.name, path.read_bytes(), 'text/plain')})
        r.raise_for_status()
    r = c.post(f'/projects/{pid}/analyses', json={'mode': 'demo'}); r.raise_for_status()
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))
