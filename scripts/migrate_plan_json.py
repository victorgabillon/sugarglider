#!/usr/bin/env python3
"""Run the installed offline canonical-request migration command."""

from sugarglider.migrate_plan_json import MigrationError, main, migrate_document

__all__ = ["MigrationError", "main", "migrate_document"]

if __name__ == "__main__":
    raise SystemExit(main())
