import sys
import uvicorn

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        print("Starting web interface...")
        uvicorn.run("app.web:app", host="0.0.0.0", port=8000, reload=True)
    else:
        from app.cli import main
        main()
