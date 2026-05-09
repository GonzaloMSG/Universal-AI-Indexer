from abc import ABC, abstractmethod
from typing import List, Dict, Any
from app.config import settings
from openai import OpenAI

class AnswerGenerator(ABC):
    @abstractmethod
    def generate_answer(self, question: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        pass

class DeterministicAnswerGenerator(AnswerGenerator):
    """
    Simply returns the top snippets directly without LLM synthesis.
    """
    def generate_answer(self, question: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        snippets = []
        for i, chunk in enumerate(context_chunks):
            file_path = chunk.get("file_path", "Unknown file")
            lines = f"L{chunk.get('line_start', '?')}-L{chunk.get('line_end', '?')}"
            snippets.append(f"[{i+1}] {file_path} ({lines}):\n```sql\n{chunk.get('text', '')}\n```")
            
        answer = "Here are the most relevant code snippets I found:\n\n" + "\n\n".join(snippets)
        return {
            "answer": answer,
            "citations": context_chunks
        }

class OpenAICompatibleAnswerGenerator(AnswerGenerator):
    """
    Uses OpenAI or compatible API (like vLLM) to synthesize an answer.
    """
    def __init__(self):
        self.model = settings.model_name
        
    def generate_answer(self, question: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not settings.openai_api_key:
            return DeterministicAnswerGenerator().generate_answer(question, context_chunks)
            
        client = OpenAI(api_key=settings.openai_api_key)
        
        context_text = ""
        for i, chunk in enumerate(context_chunks):
            file_path = chunk.get("file_path", "Unknown")
            lines = f"L{chunk.get('line_start', '?')}-L{chunk.get('line_end', '?')}"
            context_text += f"\nSnippet [{i+1}] from {file_path} ({lines}):\n{chunk.get('text', '')}\n"
            
        prompt = f"""You are an expert AI assistant that helps developers understand their SQL codebase.
Use the following context snippets to answer the user's question. 
If the answer is not in the context, just say you don't know, don't try to make it up.
Cite the snippet numbers like [1] or [2] when referencing them.

Context:
{context_text}

Question:
{question}

Answer:"""

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful coding assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=1000
            )
            answer = response.choices[0].message.content
        except Exception as e:
            answer = f"Error communicating with LLM: {str(e)}\n\nFallback Answer:\n"
            fallback = DeterministicAnswerGenerator().generate_answer(question, context_chunks)
            answer += fallback["answer"]
            
        return {
            "answer": answer,
            "citations": context_chunks
        }
