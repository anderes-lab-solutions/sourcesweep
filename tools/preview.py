#!/usr/bin/env python3
"""Live preview of the report design. No network, no API key, no tokens.

    python tools/preview.py                         # the bundled example scan
    python tools/preview.py path/to/scan-folder     # any saved scan (needs sources.json; screening.json and briefing.md optional)

Open http://localhost:8765 and edit the report template and styles in sourcesweep/scanner.py.
Every time you save, the report is re-rendered from the saved scan and the browser tab reloads.
Your scan folder is never modified: rendering happens in a temporary copy.

Options: --port 8765, --width-check (also prints the URL to view the report at the app's width).
"""
import argparse
import http.server
import importlib
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TEMPLATE = ROOT / "sourcesweep" / "scanner.py"
RELOAD = """<script>(function(){let v=null;setInterval(async()=>{try{const r=await fetch('/__version',{cache:'no-store'});
const t=await r.text();if(v&&t!==v)location.reload();v=t}catch(e){}},700)})();</script>"""
APP_FRAME = """<!doctype html><meta charset=utf-8><title>Report at app width</title>
<body style="margin:0;background:#f7f2f8;font:14px system-ui"><p style="padding:10px 20px;margin:0">
Report inside a 1040 px frame, roughly as the web app shows it.</p>
<iframe src="/" style="width:1040px;height:94vh;border:1px solid #ddd;background:#fff;margin:0 20px"></iframe>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scan", nargs="?", default=str(ROOT / "examples" / "claudin-18-2"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--title", default="")
    a = ap.parse_args()

    src = Path(a.scan).resolve()
    if not (src / "sources.json").exists():
        sys.exit(f"{src} has no sources.json")
    work = Path(tempfile.mkdtemp(prefix="sourcesweep_preview_"))
    for name in ("sources.json", "screening.json", "briefing.md"):
        if (src / name).exists():
            shutil.copy(src / name, work / name)

    state = {"version": "0", "html": b"", "error": ""}

    def build():
        try:
            import sourcesweep.scanner as scanner
            scanner = importlib.reload(scanner)
            if (src / "briefing.md").exists():       # render() fills "Last mention" into briefing.md; start fresh each time
                shutil.copy(src / "briefing.md", work / "briefing.md")
            html = scanner.render(work, title=a.title).read_text()
            state["html"] = html.replace("</body>", RELOAD + "</body>").encode()
            state["error"] = ""
        except Exception as e:  # keep serving the last good version, show the error
            state["error"] = f"{type(e).__name__}: {e}"
            print("render failed:", state["error"], file=sys.stderr)
        state["version"] = str(time.time())

    def watch():
        last = TEMPLATE.stat().st_mtime
        while True:
            time.sleep(0.5)
            m = TEMPLATE.stat().st_mtime
            if m != last:
                last = m
                build()
                print(time.strftime("%H:%M:%S"), "re-rendered" if not state["error"] else "error: " + state["error"])

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/__version"):
                body, ctype = state["version"].encode(), "text/plain"
            elif self.path.startswith("/app"):
                body, ctype = APP_FRAME.encode(), "text/html"
            else:
                body = state["html"]
                if state["error"]:
                    body = body.replace(b"<body>", b"<body><pre style='background:#fee;color:#900;padding:10px;margin:0'>"
                                        + state["error"].encode() + b"</pre>", 1)
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    build()
    threading.Thread(target=watch, daemon=True).start()
    print(f"Previewing {src}\n  report:          http://localhost:{a.port}\n  at app width:    http://localhost:{a.port}/app\n"
          f"Edit {TEMPLATE.relative_to(ROOT)} and save; the page reloads. Ctrl+C to stop.")
    http.server.ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
