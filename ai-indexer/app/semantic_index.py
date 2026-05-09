import numpy as np
from sentence_transformers import SentenceTransformer
from app.db import get_connection

MODEL_NAME = "all-MiniLM-L6-v2"
model = None

def get_model():
    global model
    if model is None:
        model = SentenceTransformer(MODEL_NAME)
    return model

def compute_embedding(text: str) -> bytes:
    m = get_model()
    embedding = m.encode(text)
    return embedding.astype(np.float32).tobytes()

def index_unembedded_documents():
    """
    Finds documents without embeddings and computes them.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT rowid, text FROM documents 
        WHERE rowid NOT IN (SELECT doc_id FROM embeddings)
    ''')
    rows = cursor.fetchall()
    
    for row in rows:
        doc_id = row['rowid']
        text = row['text']
        emb_bytes = compute_embedding(text)
        
        cursor.execute('''
            INSERT INTO embeddings (doc_id, embedding) VALUES (?, ?)
        ''', (doc_id, emb_bytes))
        
    conn.commit()
    conn.close()

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    # Handle zero vectors just in case
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return np.dot(a, b) / (norm_a * norm_b)

def search_semantic(query: str, workspace_id: int = None, limit: int = 10):
    """
    Computes query embedding and finds top-K similar chunks.
    """
    query_emb = get_model().encode(query)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    sql = '''
        SELECT d.rowid, d.file_path, d.object_name, d.block_type, d.statement_type, d.text, d.line_start, d.line_end, d.metadata_json, d.workspace_id, e.embedding
        FROM documents d
        JOIN embeddings e ON d.rowid = e.doc_id
    '''
    params = []
    if workspace_id is not None:
        sql += ' WHERE d.workspace_id = ?'
        params.append(workspace_id)
        
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for row in rows:
        emb_bytes = row['embedding']
        doc_emb = np.frombuffer(emb_bytes, dtype=np.float32)
        score = float(cosine_similarity(query_emb, doc_emb))
        
        row_dict = dict(row)
        del row_dict['embedding']
        row_dict['score'] = score
        results.append(row_dict)
        
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:limit]
    
if __name__ == "__main__":
    print("Computing embeddings for new documents...")
    index_unembedded_documents()
    print("Done.")
