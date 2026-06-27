from __future__ import annotations

import subprocess
import sys


def run(command: list[str]) -> None:
    print("$ " + " ".join(command))
    subprocess.run(command, check=True)


def main() -> int:
    python = sys.executable
    run([python, "scripts/validate_config.py"])
    run([python, "scripts/generate_audio.py"])
    run([python, "scripts/build_site.py"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
