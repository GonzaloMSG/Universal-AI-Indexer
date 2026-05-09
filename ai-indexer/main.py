#!/usr/bin/env python
"""
Universal AI Indexer - Entry point.
Usage:
    python main.py ingest <path> <workspace_name>
    python main.py search <query>
    python main.py ask <question>
    python main.py web
"""
import sys
import os

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import init_db

# Initialize DB on every startup (idempotent)
init_db()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        import uvicorn
        print("🌐 Starting Web UI at http://localhost:8000")
        uvicorn.run("app.web:app", host="0.0.0.0", port=8000, reload=True)
    else:
        from app.cli import main
        main()
