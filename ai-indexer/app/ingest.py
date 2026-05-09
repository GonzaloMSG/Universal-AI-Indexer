import os
import json
import chardet
import hashlib
import sqlglot
from pathlib import Path
from typing import Optional, List, Dict, Any
from app.db import get_connection
from app.splitter import split_sql_batches

# ─────────────────────────────────────────────
# Supported extensions and their file type label
# ─────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {
    '.sql':  'sql',
    '.py':   'python',
    '.md':   'markdown',
    '.txt':  'text',
    '.log':  'text',
    '.json': 'json',
    '.yaml': 'yaml',
    '.yml':  'yaml',
    '.csv':  'csv',
    '.js':   'javascript',
    '.ts':   'typescript',
    '.html': 'html',
    '.css':  'css',
    '.sh':   'shell',
    '.bat':  'shell',
    '.toml': 'toml',
    '.ini':  'config',
    '.cfg':  'config',
    '.env':  'config',
}

CHUNK_SIZE = 1200   # characters per chunk
CHUNK_OVERLAP = 150  # characters of overlap between chunks


# ─────────────────────────────────────────────
# Encoding detection
# ─────────────────────────────────────────────
def detect_encoding(file_path: str) -> str:
    try:
        with open(file_path, 'rb') as f:
            raw = f.read(20_000)
        result = chardet.detect(raw)
        return result.get('encoding') or 'utf-8'
    except Exception:
        return 'utf-8'


def read_file(file_path: str) -> Optional[str]:
    encoding = detect_encoding(file_path)
    try:
        with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
            return f.read()
    except Exception as e:
        print(f"  [!] Could not read {file_path}: {e}")
        return None


# ─────────────────────────────────────────────
# Chunking strategies
# ─────────────────────────────────────────────
def chunk_by_size(text: str, file_path: str, file_type: str) -> List[Dict[str, Any]]:
    """Generic sliding-window chunker."""
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                'text': chunk_text,
                'line_start': text[:start].count('\n') + 1,
                'line_end':   text[:end].count('\n') + 1,
                'chunk_index': idx,
                'strategy': 'size_overlap',
            })
        start += CHUNK_SIZE - CHUNK_OVERLAP
        idx += 1
    return chunks


def chunk_markdown(text: str, file_path: str) -> List[Dict[str, Any]]:
    """Split Markdown by headings (H1/H2/H3)."""
    import re
    sections = re.split(r'(?=^#{1,3} )', text, flags=re.MULTILINE)
    chunks = []
    line_cursor = 1
    for idx, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue
        line_count = section.count('\n') + 1
        # Extract heading for metadata
        first_line = section.splitlines()[0]
        heading = first_line.lstrip('#').strip() if first_line.startswith('#') else ''
        # If section is too long, sub-chunk it
        if len(section) > CHUNK_SIZE:
            sub_chunks = chunk_by_size(section, file_path, 'markdown')
            for sc in sub_chunks:
                sc['heading'] = heading
                chunks.append(sc)
        else:
            chunks.append({
                'text': section,
                'line_start': line_cursor,
                'line_end': line_cursor + line_count - 1,
                'chunk_index': idx,
                'strategy': 'semantic_heading',
                'heading': heading,
            })
        line_cursor += line_count
    return chunks


def chunk_python(text: str, file_path: str) -> List[Dict[str, Any]]:
    """Split Python by top-level functions and classes using ast."""
    import ast
    chunks = []
    lines = text.splitlines()
    try:
        tree = ast.parse(text)
        nodes = [n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        # Only top-level nodes (direct children of Module)
        top_nodes = [n for n in ast.iter_child_nodes(tree)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        for idx, node in enumerate(top_nodes):
            start = node.lineno - 1
            end = node.end_lineno
            node_text = '\n'.join(lines[start:end])
            docstring = ast.get_docstring(node) or ''
            chunks.append({
                'text': node_text,
                'line_start': node.lineno,
                'line_end': node.end_lineno,
                'chunk_index': idx,
                'strategy': 'structural_ast',
                'node_type': type(node).__name__,
                'name': node.name,
                'docstring': docstring,
            })
        # If no nodes found or file is small, treat as plain text
        if not chunks:
            chunks = chunk_by_size(text, file_path, 'python')
    except SyntaxError:
        # Fallback: plain size chunking
        chunks = chunk_by_size(text, file_path, 'python')
    return chunks


def chunk_sql(text: str, file_path: str) -> List[Dict[str, Any]]:
    """Use the existing SQL splitter (GO-based batches)."""
    batches = split_sql_batches(text)
    chunks = []
    for idx, batch in enumerate(batches):
        batch['chunk_index'] = idx
        batch['strategy'] = 'sql_go_separator'
        chunks.append(batch)
    return chunks


# ─────────────────────────────────────────────
# SQL metadata via sqlglot
# ─────────────────────────────────────────────
def parse_sql_metadata(sql_text: str) -> Dict[str, Any]:
    meta = {"statement_type": "unknown", "object_name": None,
            "block_type": "unknown", "tables": [], "columns": [], "parse_error": False}
    try:
        parsed = sqlglot.parse(sql_text)
        if not parsed:
            return meta
        stmt = parsed[0]
        if not stmt:
            return meta
        meta["statement_type"] = stmt.key.upper()
        meta["tables"] = list({t.name for t in stmt.find_all(sqlglot.exp.Table)})
        meta["columns"] = list({c.name for c in stmt.find_all(sqlglot.exp.Column)})
        if isinstance(stmt, sqlglot.exp.Create):
            meta["block_type"] = "DDL"
            if stmt.this:
                meta["object_name"] = stmt.this.name
        elif isinstance(stmt, (sqlglot.exp.Select, sqlglot.exp.Insert,
                                sqlglot.exp.Update, sqlglot.exp.Delete)):
            meta["block_type"] = "DML"
            if hasattr(stmt, 'this') and stmt.this and hasattr(stmt.this, 'name'):
                meta["object_name"] = stmt.this.name
    except Exception as e:
        meta["parse_error"] = True
        meta["error_msg"] = str(e)
    return meta


# ─────────────────────────────────────────────
# Dispatch chunking by extension
# ─────────────────────────────────────────────
def chunk_file(text: str, file_path: str, file_type: str) -> List[Dict[str, Any]]:
    if file_type == 'sql':
        return chunk_sql(text, file_path)
    elif file_type == 'markdown':
        return chunk_markdown(text, file_path)
    elif file_type == 'python':
        return chunk_python(text, file_path)
    else:
        return chunk_by_size(text, file_path, file_type)


# ─────────────────────────────────────────────
# File ingestion
# ─────────────────────────────────────────────
def ingest_file(file_path: str, workspace_id: int, file_type: str):
    text = read_file(file_path)
    if not text or not text.strip():
        return 0

    chunks = chunk_file(text, file_path, file_type)
    conn = get_connection()
    cursor = conn.cursor()
    saved = 0

    for chunk in chunks:
        chunk_text = chunk.get('text', '').strip()
        if not chunk_text:
            continue

        # Build metadata JSON
        meta = {k: v for k, v in chunk.items() if k not in ('text', 'line_start', 'line_end')}
        if file_type == 'sql':
            meta.update(parse_sql_metadata(chunk_text))

        content_hash = hashlib.sha256(chunk_text.encode('utf-8', errors='ignore')).hexdigest()
        object_name = meta.get('name') or meta.get('object_name') or meta.get('heading') or ''
        block_type = meta.get('node_type') or meta.get('block_type') or meta.get('strategy', '')
        statement_type = meta.get('statement_type', file_type)

        cursor.execute('''
            INSERT INTO documents (
                file_path, object_name, block_type, statement_type, text,
                line_start, line_end, metadata_json, workspace_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            file_path,
            object_name,
            block_type,
            statement_type,
            chunk_text,
            chunk.get('line_start', 0),
            chunk.get('line_end', 0),
            json.dumps(meta),
            workspace_id
        ))
        saved += 1

    conn.commit()
    conn.close()
    return saved


# ─────────────────────────────────────────────
# Directory ingestion
# ─────────────────────────────────────────────
def ingest_directory(dir_path: str, workspace_name: str):
    abs_path = str(Path(dir_path).resolve())

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM workspaces WHERE path = ?', (abs_path,))
    row = cursor.fetchone()
    if row:
        workspace_id = row['id']
        cursor.execute('DELETE FROM documents WHERE workspace_id = ?', (workspace_id,))
        cursor.execute('UPDATE workspaces SET name = ? WHERE id = ?', (workspace_name, workspace_id))
        print(f"  Re-indexing existing workspace '{workspace_name}'...")
    else:
        cursor.execute('INSERT INTO workspaces (name, path) VALUES (?, ?)', (workspace_name, abs_path))
        workspace_id = cursor.lastrowid
        print(f"  Created new workspace '{workspace_name}' (id={workspace_id})")

    conn.commit()
    conn.close()

    total_files = 0
    total_chunks = 0
    skipped = 0

    for root, dirs, files in os.walk(abs_path):
        # Skip hidden dirs and common noise
        dirs[:] = [d for d in dirs if not d.startswith('.')
                   and d not in ('__pycache__', 'node_modules', '.git', 'venv', '.venv')]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            file_type = SUPPORTED_EXTENSIONS.get(ext)
            if not file_type:
                skipped += 1
                continue
            full_path = os.path.join(root, file)
            print(f"  Indexing [{file_type.upper():10s}] {full_path}")
            n = ingest_file(full_path, workspace_id, file_type)
            total_chunks += n
            total_files += 1

    print(f"\n  ✅ Done: {total_files} files, {total_chunks} chunks indexed. ({skipped} files skipped)")

    print("  Computing semantic embeddings...")
    from app.semantic_index import index_unembedded_documents
    index_unembedded_documents()
    print("  ✅ Embeddings ready.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        ingest_directory(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python -m app.ingest <dir_path> <workspace_name>")
