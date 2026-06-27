from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from dailynews_config import normalized_config


SRT_BLOCK_RE = re.compile(
    r"(?:\d+\s+)?"
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+"
    r"(?P<end>\d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<text>.*?)(?=\n\s*\n|\Z)",
    re.DOTALL,
)


def srt_time_to_seconds(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, millis = rest.split(",")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis) / 1000
    )


def parse_srt(path: Path) -> list[dict[str, float | str]]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8-sig").strip()
    cues: list[dict[str, float | str]] = []
    for match in SRT_BLOCK_RE.finditer(text):
        cue_text = " ".join(match.group("text").split())
        cues.append(
            {
                "start": round(srt_time_to_seconds(match.group("start")), 3),
                "end": round(srt_time_to_seconds(match.group("end")), 3),
                "text": cue_text,
            }
        )
    return cues


def find_daily_file(data_dir: Path, date: str | None) -> Path:
    if date:
        path = data_dir / f"{date}.json"
        if not path.exists():
            raise FileNotFoundError(f"Daily data file not found: {path}")
        return path

    candidates = sorted(data_dir.glob("????-??-??.json"))
    if not candidates:
        raise FileNotFoundError(f"No daily JSON files found in {data_dir}")
    return candidates[-1]


def run_edge_tts(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    mp3_path: Path,
    srt_path: Path,
) -> None:
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.parent.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory() as tmp:
        text_path = Path(tmp) / "tts-input.txt"
        text_path.write_text(text.strip() + "\n", encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "edge_tts",
            "--voice",
            voice,
            f"--rate={rate}",
            f"--pitch={pitch}",
            "--file",
            str(text_path),
            "--write-media",
            str(mp3_path),
            "--write-subtitles",
            str(srt_path),
        ]
        subprocess.run(command, check=True)


def generate_for_item(
    item: dict,
    date: str,
    audio_dir: Path,
    english_voice: str,
    chinese_voice: str,
    rate: str,
    pitch: str,
) -> None:
    item_id = item["id"]
    item_audio_dir = audio_dir / date
    en_mp3 = item_audio_dir / f"{item_id}-en.mp3"
    zh_mp3 = item_audio_dir / f"{item_id}-zh.mp3"
    en_srt = item_audio_dir / f"{item_id}-en.srt"
    zh_srt = item_audio_dir / f"{item_id}-zh.srt"

    if item.get("english"):
        run_edge_tts(item["english"], english_voice, rate, pitch, en_mp3, en_srt)
    if item.get("chinese"):
        run_edge_tts(item["chinese"], chinese_voice, rate, pitch, zh_mp3, zh_srt)

    item["audio"] = {
        "english": f"audio/{date}/{item_id}-en.mp3",
        "chinese": f"audio/{date}/{item_id}-zh.mp3",
    }
    item["subtitle_files"] = {
        "english": f"audio/{date}/{item_id}-en.srt",
        "chinese": f"audio/{date}/{item_id}-zh.srt",
    }
    item["subtitles"] = {
        "english": parse_srt(en_srt),
        "chinese": parse_srt(zh_srt),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Edge TTS MP3 files for daily news JSON.")
    parser.add_argument("--config", default="config.txt")
    parser.add_argument("--date", help="Daily data date in YYYY-MM-DD format. Defaults to latest data file.")
    parser.add_argument("--data", help="Explicit daily JSON path.")
    args = parser.parse_args()

    config = normalized_config(args.config)
    if not config["audio"]["generate_mp3"]:
        print("MP3 generation is disabled in config.txt.")
        return 0

    data_dir = Path(config["output"]["data_dir"])
    audio_dir = Path(config["output"]["audio_dir"])
    daily_file = Path(args.data) if args.data else find_daily_file(data_dir, args.date)
    payload = json.loads(daily_file.read_text(encoding="utf-8"))
    date = payload["date"]

    for item in payload.get("items", []):
        generate_for_item(
            item=item,
            date=date,
            audio_dir=audio_dir,
            english_voice=config["audio"]["english_voice"],
            chinese_voice=config["audio"]["chinese_voice"],
            rate=config["audio"]["edge_tts_rate"],
            pitch=config["audio"]["edge_tts_pitch"],
        )
        print(f"Generated audio for {item['id']}")

    daily_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {daily_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
