"""Servidor local do frontend; nunca publica .env, Python, SQL ou arquivos Git."""

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
PUBLIC_FILES = {"/manifest.webmanifest", "/service-worker.js"}
PUBLIC_DIRS = {"html", "css", "js", "icons"}


class FrontendHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".webmanifest": "application/manifest+json",
        ".js": "text/javascript",
        ".svg": "image/svg+xml",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def list_directory(self, path):
        self.send_error(404)
        return None

    def send_head(self):
        raw = unquote(urlsplit(self.path).path)
        if raw == "/":
            self.path = "/html/index.html"
            raw = self.path
        path = (ROOT / raw.lstrip("/")).resolve()
        parts = Path(raw.lstrip("/")).parts
        public = raw in PUBLIC_FILES or (parts and parts[0] in PUBLIC_DIRS)
        public = public or (
            parts
            and parts[0] == "docs"
            and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"}
        )
        if ROOT in path.parents:
            resolved = path.relative_to(ROOT).parts
            public = public and (
                resolved[0] in PUBLIC_DIRS
                or "/" + str(path.relative_to(ROOT)) in PUBLIC_FILES
                or (
                    resolved[0] == "docs"
                    and path.suffix.lower()
                    in {".png", ".jpg", ".jpeg", ".webp", ".svg"}
                )
            )
        if (
            not public
            or ROOT not in path.parents
            or not path.is_file()
            or any(p.startswith(".") for p in parts)
        ):
            self.send_error(404)
            return None
        return super().send_head()

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-cache")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob: http://127.0.0.1:8000 http://localhost:8000; connect-src 'self' http://127.0.0.1:8000 http://localhost:8000; frame-src 'self' blob: http://127.0.0.1:8000 http://localhost:8000; object-src 'none'; worker-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
        )
        if urlsplit(self.path).path == "/service-worker.js":
            self.send_header("Service-Worker-Allowed", "/")
        super().end_headers()

    def log_request(self, code="-", size="-"):
        # Links de confirmação/reset podem conter tokens na query; nunca registrá-los.
        self.log_message(
            '"%s %s" %s %s', self.command, urlsplit(self.path).path, code, size
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=5500)
    p.add_argument(
        "--bind", default="127.0.0.1", choices=["127.0.0.1", "localhost", "0.0.0.0"]
    )
    args = p.parse_args()
    server = ThreadingHTTPServer((args.bind, args.port), FrontendHandler)
    print(f"Talentix: http://{args.bind}:{args.port}/html/index.html", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
