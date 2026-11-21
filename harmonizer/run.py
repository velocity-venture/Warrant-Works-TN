"""Start WarrantWorks TN on this computer.

    python run.py                 # http://127.0.0.1:8765, data in ./data
    python run.py --port 9000 --data /path/to/data
"""
import argparse
import webbrowser

import uvicorn

from warrantworks.api import create_app


def main():
    ap = argparse.ArgumentParser(description="WarrantWorks TN (local)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data", default="data", help="folder for the database and stored files")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    app = create_app(a.data)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"WarrantWorks TN running at {url}  (data: {a.data})  Ctrl+C to stop.")
    if not a.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
