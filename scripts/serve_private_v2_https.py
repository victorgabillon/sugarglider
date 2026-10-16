#!/usr/bin/env python3
"""Explicit loopback-only private HTTPS fixture; no publication or directory listing."""

import argparse
import http.server
import re
import ssl
from functools import partial
from pathlib import Path
from typing import IO

ORIGIN = "https://appassets.androidplatform.net"


class PrivateHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header(
            "Access-Control-Expose-Headers",
            "Content-Length, Content-Range, Accept-Ranges",
        )
        self.send_header("Vary", "Origin")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-transform")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def list_directory(self, path: str) -> None:
        self.send_error(403)
        return None

    def send_head(self) -> IO[bytes] | None:
        path = Path(self.translate_path(self.path))
        root = Path(self.directory).resolve()
        if (
            not path.resolve().is_relative_to(root)
            or path.is_symlink()
            or any(p.is_symlink() for p in path.parents)
        ):
            self.send_error(403)
            return None
        interval = self.headers.get("Range")
        if not interval:
            return super().send_head()
        match = re.fullmatch(r"bytes=([0-9]+)-([0-9]+)", interval)
        if not match or not path.is_file():
            self.send_error(416)
            return None
        start, end = int(match[1]), int(match[2])
        size = path.stat().st_size
        if start > end or end >= size:
            self.send_error(416)
            return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        self._interval = (start, end)
        return path.open("rb")

    def copyfile(self, source: IO[bytes], outputfile: IO[bytes]) -> None:
        interval = getattr(self, "_interval", None)
        if interval is None:
            return super().copyfile(source, outputfile)
        start, end = interval
        source.seek(start)
        remaining = end - start + 1
        while remaining:
            data = source.read(min(65_536, remaining))
            if not data:
                raise OSError("range source changed")
            outputfile.write(data)
            remaining -= len(data)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--port", type=int, default=9443)
    args = parser.parse_args()
    if not args.root.is_dir() or args.root.is_symlink():
        parser.error("existing private site required")
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", args.port), partial(PrivateHandler, directory=str(args.root))
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.certificate, args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    print("Private HTTPS bound only to 127.0.0.1", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
