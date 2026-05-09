from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pathlib import Path
import markdown
import os

from app.db import get_connection
from app.ingest import ingest_directory
from app.search_text import search_text
from app.qa import answer_question

app = FastAPI(title="AI Indexer")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def md_to_html(text):
    return markdown.markdown(text, extensions=['fenced_code', 'codehilite'])

templates.env.filters['markdown'] = md_to_html

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, path FROM workspaces")
    workspaces = [dict(row) for row in cursor.fetchall()]
    cursor.execute("SELECT COUNT(*) as total FROM documents")
    total_chunks = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(DISTINCT file_path) as total FROM documents")
    total_files = cursor.fetchone()['total']
    cursor.execute("""
        SELECT statement_type, COUNT(*) as n 
        FROM documents 
        GROUP BY statement_type 
        ORDER BY n DESC
        LIMIT 12
    """)
    by_type = [dict(row) for row in cursor.fetchall()]
    max_chunks = max((r['n'] for r in by_type), default=1)
    conn.close()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "workspaces": workspaces,
        "total_chunks": total_chunks,
        "total_files": total_files,
        "by_type": by_type,
        "max_chunks": max_chunks,
    })

@app.post("/ingest")
async def trigger_ingest(request: Request, name: str = Form(...), path: str = Form(...)):
    if os.path.isdir(path):
        ingest_directory(path, name)
    return RedirectResponse(url="/", status_code=303)

@app.get("/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = "", workspace_id: int = None):
    results = []
    if q:
        results = search_text(q, workspace_id)
        
    return templates.TemplateResponse("search.html", {"request": request, "query": q, "results": results})

@app.get("/ask", response_class=HTMLResponse)
async def ask_page(request: Request, q: str = "", workspace_id: int = None):
    answer_data = None
    if q:
        answer_data = answer_question(q, workspace_id, use_llm=True)
        
    return templates.TemplateResponse("answer.html", {"request": request, "query": q, "answer_data": answer_data})

@app.get("/block/{doc_id}", response_class=HTMLResponse)
async def view_block(request: Request, doc_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT rowid, * FROM documents WHERE rowid = ?", (doc_id,))
    doc = cursor.fetchone()
    conn.close()
    
    if not doc:
        return HTMLResponse("Not found", status_code=404)
        
    return templates.TemplateResponse("block.html", {"request": request, "doc": dict(doc)})
