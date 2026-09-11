"""Production entry point and explicit backup/verification operations."""

import argparse
import json
import logging
import os
from pathlib import Path

import uvicorn
from pydantic import ValidationError

from sugarglider.social_server.app import create_social_app
from sugarglider.social_server.settings import SocialSettings
from sugarglider.social_server.sqlite_repository import (
    BackupError,
    create_backup,
    prune_backups,
    verify_backup,
)


class PrivateFormatter(logging.Formatter):
    """Keep only our allowlisted structured events; discard arbitrary messages."""

    def format(self, record: logging.LogRecord) -> str:
        if record.name in ("sugarglider.social.http", "sugarglider.social.lifecycle"):
            return record.getMessage()
        return json.dumps({"event": "runtime_log", "level": record.levelname})


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(PrivateFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Sugarglider social service")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    # Only enable this behind the supplied isolated HTTPS proxy network.
    serve.add_argument("--trust-proxy", action="store_true")
    backup = commands.add_parser("backup")
    backup.add_argument("--data-directory", required=True, type=Path)
    backup.add_argument("--destination", required=True, type=Path)
    verify = commands.add_parser("verify-backup")
    verify.add_argument("directory", type=Path)
    prune = commands.add_parser("prune-backups")
    prune.add_argument("directory", type=Path)
    prune.add_argument("--retain-days", type=int, default=7)
    args = parser.parse_args()
    configure_logging()
    try:
        if args.command == "serve":
            settings = SocialSettings()
            uvicorn.run(
                create_social_app(settings),
                host=args.host,
                port=args.port,
                workers=1,
                access_log=False,
                server_header=False,
                log_config=None,
                proxy_headers=args.trust_proxy,
                forwarded_allow_ips="*" if args.trust_proxy else "",
                ws="none",
                backlog=128,
                timeout_keep_alive=5,
                timeout_graceful_shutdown=20,
                h11_max_incomplete_event_size=16_384,
            )
        elif args.command == "backup":
            result = create_backup(args.data_directory, args.destination)
            print(json.dumps({"status": "ok", "backup": result.name}))
        elif args.command == "verify-backup":
            verify_backup(args.directory)
            print('{"status":"ok","operation":"verify_backup"}')
        else:
            removed = prune_backups(args.directory, retain_days=args.retain_days)
            print(
                json.dumps(
                    {"status": "ok", "operation": "prune_backups", "removed": removed}
                )
            )
    except (ValidationError, BackupError, OSError):
        print('{"status":"failed","message":"Check configuration or storage."}')
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
