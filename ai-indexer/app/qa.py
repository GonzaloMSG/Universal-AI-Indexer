from typing import List, Dict, Any
from app.search_text import search_text
from app.semantic_index import search_semantic
from app.answer_generators import DeterministicAnswerGenerator, OpenAICompatibleAnswerGenerator

def hybrid_search(query: str, workspace_id: int = None, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Combines text and semantic search. 
    Implements a simple Reciprocal Rank Fusion (RRF).
    """
    text_results = search_text(query, workspace_id, limit=limit*2)
    semantic_results = search_semantic(query, workspace_id, limit=limit*2)
    
    # RRF constants
    k = 60
    scores = {}
    docs = {}
    
    for rank, doc in enumerate(text_results):
        doc_id = doc['rowid']
        docs[doc_id] = doc
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
        
    for rank, doc in enumerate(semantic_results):
        doc_id = doc['rowid']
        if doc_id not in docs:
            docs[doc_id] = doc
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
        
    # Sort by RRF score
    sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    # Return top K
    final_results = []
    for doc_id, score in sorted_docs[:limit]:
        doc = docs[doc_id]
        doc['hybrid_score'] = score
        final_results.append(doc)
        
    return final_results

def answer_question(question: str, workspace_id: int = None, use_llm: bool = True) -> Dict[str, Any]:
    context = hybrid_search(question, workspace_id, limit=5)
    
    if use_llm:
        generator = OpenAICompatibleAnswerGenerator()
    else:
        generator = DeterministicAnswerGenerator()
        
    return generator.generate_answer(question, context)
