import argparse
import sys
import os
from app.ingest import ingest_directory, SUPPORTED_EXTENSIONS
from app.search_text import search_text
from app.semantic_index import search_semantic
from app.qa import answer_question
from app.db import get_connection

def print_banner():
    print("""
╔══════════════════════════════════════════════════╗
║       Universal AI Indexer  v2.0                 ║
║       Your local knowledge — indexed & searchable║
╚══════════════════════════════════════════════════╝
""")

def cmd_stats():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, path FROM workspaces")
    workspaces = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) as total FROM documents")
    total = cursor.fetchone()['total']
    cursor.execute("SELECT statement_type, COUNT(*) as n FROM documents GROUP BY statement_type ORDER BY n DESC")
    by_type = cursor.fetchall()
    conn.close()

    print(f"\n  📊 Total chunks indexed : {total}")
    print(f"  📁 Workspaces          : {len(workspaces)}")
    for ws in workspaces:
        print(f"     • [{ws['id']}] {ws['name']}  →  {ws['path']}")
    print(f"\n  By file type:")
    for row in by_type:
        print(f"     {row['statement_type']:15s} {row['n']:>6} chunks")

def cmd_plugins():
    print("\n  Supported file extensions:\n")
    for ext, ftype in sorted(SUPPORTED_EXTENSIONS.items()):
        print(f"     {ext:8s}  →  {ftype}")

def main():
    print_banner()
    parser = argparse.ArgumentParser(
        description="Universal AI Indexer CLI",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── index / ingest ──
    index_parser = subparsers.add_parser(
        "index", aliases=["ingest"],
        help="Index a directory of files (all supported formats)"
    )
    index_parser.add_argument("path", help="Path to the directory or file to index")
    index_parser.add_argument(
        "name", nargs="?", default=None,
        help="Workspace name (defaults to directory name)"
    )

    # ── search ──
    search_parser = subparsers.add_parser("search", help="Search the indexed knowledge base")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "--mode", choices=["text", "semantic", "hybrid"], default="hybrid",
        help="Search mode (default: hybrid)"
    )
    search_parser.add_argument("--limit", type=int, default=5, help="Max results (default: 5)")

    # ── ask ──
    ask_parser = subparsers.add_parser("ask", help="Ask a natural language question")
    ask_parser.add_argument("question", help="The question to ask")
    ask_parser.add_argument(
        "--no-llm", action="store_true",
        help="Return raw snippets without LLM synthesis"
    )
    ask_parser.add_argument("--limit", type=int, default=5, help="Context chunks (default: 5)")

    # ── stats ──
    subparsers.add_parser("stats", help="Show index statistics")

    # ── plugins ──
    subparsers.add_parser("plugins", help="List supported file formats")

    # ── web ──
    subparsers.add_parser("web", help="Launch the Web UI")

    args = parser.parse_args()

    # ── Dispatch ──
    if args.command in ("index", "ingest"):
        path = os.path.abspath(args.path)
        name = args.name or os.path.basename(path.rstrip("/\\"))
        print(f"  📂 Indexing path : {path}")
        print(f"  🏷️  Workspace     : {name}\n")
        ingest_directory(path, name)

    elif args.command == "search":
        print(f"  🔍 Query: \"{args.query}\"  [mode={args.mode}]\n")
        if args.mode == "text":
            results = search_text(args.query, limit=args.limit)
        elif args.mode == "semantic":
            results = search_semantic(args.query, limit=args.limit)
        else:
            from app.qa import hybrid_search
            results = hybrid_search(args.query, limit=args.limit)

        if not results:
            print("  No results found.")
            return

        for i, res in enumerate(results, 1):
            file_name = os.path.basename(res.get('file_path', 'unknown'))
            lines = f"L{res.get('line_start','?')}-L{res.get('line_end','?')}"
            score = res.get('hybrid_score') or res.get('score', 0)
            score_str = f"{score:.4f}" if isinstance(score, float) else str(score)
            snippet = res['text'][:300].replace('\n', ' ')
            print(f"  ── Result {i} ─────────────────────────")
            print(f"  📄 {file_name}  {lines}   score={score_str}")
            print(f"  {snippet}{'...' if len(res['text']) > 300 else ''}\n")

    elif args.command == "ask":
        print(f"  💬 Question: \"{args.question}\"\n")
        ans = answer_question(args.question, use_llm=not args.no_llm)
        print("  ═══════════════ Answer ═══════════════")
        print(ans['answer'])
        print("  ══════════════════════════════════════\n")

    elif args.command == "stats":
        cmd_stats()

    elif args.command == "plugins":
        cmd_plugins()

    elif args.command == "web":
        import uvicorn
        print("  🌐 Starting Web UI at http://localhost:8000\n")
        uvicorn.run("app.web:app", host="0.0.0.0", port=8000, reload=True)

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
