from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dailynews_config import normalized_config


SITE_FILES = [
    "index.html",
    "styles.css",
    "app.js",
    "manifest.webmanifest",
    "service-worker.js",
    "icon.svg",
]


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_tree_contents(
    source: Path,
    target: Path,
    patterns: tuple[str, ...],
    exclude_dirs: set[str] | None = None,
) -> None:
    if not source.exists():
        return
    excluded = exclude_dirs or set()
    for pattern in patterns:
        for file_path in source.rglob(pattern):
            if file_path.is_file():
                relative = file_path.relative_to(source)
                if any(part in excluded for part in relative.parts):
                    continue
                copy_file(file_path, target / relative)


def read_daily_summary(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "date": payload.get("date", path.stem),
        "isDemo": bool(payload.get("is_demo", False)),
        "itemCount": len(payload.get("items", [])),
        "dataUrl": f"data/{path.name}",
        "topics": payload.get("topics", []),
    }


def build_manifest(data_dir: Path, config: dict) -> dict:
    daily_files = sorted(data_dir.glob("????-??-??.json"))
    days = [read_daily_summary(path) for path in daily_files]
    latest = days[-1] if days else None
    return {
        "appName": "DailyNews",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "latestDate": latest["date"] if latest else None,
        "latestDataUrl": latest["dataUrl"] if latest else None,
        "days": days,
        "settings": {
            "timezone": config["schedule"]["timezone"],
            "dailyRunTime": config["schedule"]["daily_run_time"],
            "cefrLevel": config["rewriting"]["english_cefr_level"],
            "maxEnglishWords": config["rewriting"]["max_english_words"],
            "topics": config["news"]["topics"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static DailyNews PWA into public/.")
    parser.add_argument("--config", default="config.txt")
    args = parser.parse_args()

    config = normalized_config(args.config)
    data_dir = Path(config["output"]["data_dir"])
    audio_dir = Path(config["output"]["audio_dir"])
    site_dir = Path(config["output"]["site_source_dir"])
    public_dir = Path(config["output"]["public_dir"])

    public_dir.mkdir(parents=True, exist_ok=True)
    for file_name in SITE_FILES:
        source = site_dir / file_name
        if source.exists():
            copy_file(source, public_dir / file_name)

    reset_directory(public_dir / "data")
    reset_directory(public_dir / "audio")
    copy_tree_contents(data_dir, public_dir / "data", ("*.json",))
    copy_tree_contents(audio_dir, public_dir / "audio", ("*.mp3", "*.srt"), exclude_dirs={"samples"})

    manifest = build_manifest(data_dir, config)
    (public_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Built static site in {public_dir}")
    if manifest["latestDate"]:
        print(f"Latest content date: {manifest['latestDate']}")
    else:
        print("No daily content found yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
