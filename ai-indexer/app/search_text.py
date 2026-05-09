from typing import List, Dict, Any
from app.db import get_connection

def search_text(query: str, workspace_id: int = None, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Performs BM25 full-text search on the FTS5 documents table.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Basic tokenization for FTS5 (avoid syntax errors with quotes)
    safe_query = query.replace('"', '""')
    
    sql = '''
        SELECT rowid, file_path, object_name, block_type, statement_type, text, line_start, line_end, metadata_json, workspace_id, bm25(documents) as score
        FROM documents 
        WHERE documents MATCH ?
    '''
    params = [f'"{safe_query}"']
    
    if workspace_id is not None:
        sql += ' AND workspace_id = ?'
        params.append(workspace_id)
        
    sql += ' ORDER BY score LIMIT ?'
    params.append(limit)
    
    cursor.execute(sql, tuple(params))
    results = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return results
