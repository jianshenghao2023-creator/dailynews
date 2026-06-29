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


def ensure_within_workspace(path: Path, workspace_root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(workspace_root)
    except ValueError as exc:
        raise RuntimeError(f"Refusing to modify path outside workspace: {resolved}") from exc
    return resolved


def reset_directory(path: Path, workspace_root: Path) -> None:
    ensure_within_workspace(path, workspace_root)
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


def retained_daily_files(data_dir: Path, history_days: int) -> list[Path]:
    return sorted(data_dir.glob("????-??-??.json"))[-history_days:]


def prune_generated_archives(
    data_dir: Path,
    audio_dir: Path,
    keep_dates: set[str],
    workspace_root: Path,
) -> None:
    ensure_within_workspace(data_dir, workspace_root)
    ensure_within_workspace(audio_dir, workspace_root)

    for path in sorted(data_dir.glob("????-??-??.json")):
        if path.stem not in keep_dates:
            ensure_within_workspace(path, workspace_root)
            path.unlink()

    if not audio_dir.exists():
        return

    for path in sorted(audio_dir.iterdir()):
        if path.is_dir() and path.name not in keep_dates and path.match("????-??-??"):
            ensure_within_workspace(path, workspace_root)
            shutil.rmtree(path)


def copy_daily_files(daily_files: list[Path], target: Path) -> None:
    for path in daily_files:
        copy_file(path, target / path.name)


def copy_audio_archives(audio_dir: Path, target: Path, keep_dates: set[str]) -> None:
    for date in sorted(keep_dates):
        source = audio_dir / date
        if source.exists() and source.is_dir():
            copy_tree_contents(source, target / date, ("*.mp3", "*.srt"))


def build_manifest(daily_files: list[Path], config: dict) -> dict:
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
            "historyDays": config["output"]["history_days"],
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
    history_days = config["output"]["history_days"]
    workspace_root = Path.cwd().resolve()
    daily_files = retained_daily_files(data_dir, history_days)
    keep_dates = {path.stem for path in daily_files}

    prune_generated_archives(data_dir, audio_dir, keep_dates, workspace_root)
    daily_files = retained_daily_files(data_dir, history_days)
    keep_dates = {path.stem for path in daily_files}

    ensure_within_workspace(public_dir, workspace_root)
    public_dir.mkdir(parents=True, exist_ok=True)
    for file_name in SITE_FILES:
        source = site_dir / file_name
        if source.exists():
            copy_file(source, public_dir / file_name)

    reset_directory(public_dir / "data", workspace_root)
    reset_directory(public_dir / "audio", workspace_root)
    copy_daily_files(daily_files, public_dir / "data")
    copy_audio_archives(audio_dir, public_dir / "audio", keep_dates)

    manifest = build_manifest(daily_files, config)
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
