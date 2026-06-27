from __future__ import annotations

import json
import sys
from pathlib import Path

from dailynews_config import normalized_config, validate_config


def main() -> int:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.txt")
    errors = validate_config(config_path)
    summary = normalized_config(config_path)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if errors:
        print("\nConfig errors:", file=sys.stderr)
        for error in errors:
            location = ".".join(part for part in [error.section, error.key] if part)
            print(f"- {location}: {error.message}", file=sys.stderr)
        return 1

    print("\nConfig OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
