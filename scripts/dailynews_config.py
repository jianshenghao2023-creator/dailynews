from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import re


CEFR_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}


@dataclass(frozen=True)
class ConfigError:
    message: str
    section: str | None = None
    key: str | None = None


def parse_config(path: str | Path = "config.txt") -> dict[str, dict[str, str]]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    data: dict[str, dict[str, str]] = {}
    current_section = "default"
    data[current_section] = {}

    for line_number, raw_line in enumerate(
        config_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip()
            if not current_section:
                raise ValueError(f"Empty section name at line {line_number}")
            data.setdefault(current_section, {})
            continue

        if "=" not in line:
            raise ValueError(f"Invalid config line {line_number}: {raw_line}")

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Empty key at line {line_number}")
        data.setdefault(current_section, {})[key] = value.strip()

    data.pop("default", None)
    return data


def get(config: dict[str, dict[str, str]], section: str, key: str, default: str = "") -> str:
    return config.get(section, {}).get(key, default)


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def as_bool(value: str, default: bool = False) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def as_int(value: str, default: int) -> int:
    if value == "":
        return default
    return int(value)


def media_sources(config: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    news = config.get("news", {})
    sources: list[dict[str, str]] = []
    indexes = sorted(
        {
            int(match.group(1))
            for key in news
            if (match := re.match(r"media_source_(\d+)_name$", key))
        }
    )

    for index in indexes:
        name = news.get(f"media_source_{index}_name", "").strip()
        homepage = news.get(f"media_source_{index}_homepage", "").strip()
        feed = news.get(f"media_source_{index}_feed", "").strip()
        if name or homepage or feed:
            sources.append({"name": name, "homepage": homepage, "feed": feed})

    return sources


def normalized_config(path: str | Path = "config.txt") -> dict[str, Any]:
    config = parse_config(path)
    return {
        "schedule": {
            "timezone": get(config, "schedule", "timezone", "Europe/Berlin"),
            "daily_run_time": get(config, "schedule", "daily_run_time", "07:00"),
        },
        "news": {
            "topics": split_csv(get(config, "news", "topics")),
            "news_count": as_int(get(config, "news", "news_count"), 10),
            "sources": media_sources(config),
            "avoid_paywalled_articles": as_bool(
                get(config, "news", "avoid_paywalled_articles"), True
            ),
        },
        "rewriting": {
            "english_cefr_level": get(config, "rewriting", "english_cefr_level", "B2"),
            "max_english_words": as_int(
                get(config, "rewriting", "max_english_words"), 80
            ),
            "generate_chinese_version": as_bool(
                get(config, "rewriting", "generate_chinese_version"), True
            ),
        },
        "audio": {
            "generate_mp3": as_bool(get(config, "audio", "generate_mp3"), True),
            "tts_provider": get(config, "audio", "tts_provider", "edge_tts"),
            "english_voice": get(config, "audio", "english_voice", "en-US-AvaNeural"),
            "chinese_voice": get(config, "audio", "chinese_voice", "zh-CN-XiaoxiaoNeural"),
            "edge_tts_rate": get(config, "audio", "edge_tts_rate", "-8%"),
            "edge_tts_pitch": get(config, "audio", "edge_tts_pitch", "+0Hz"),
        },
        "output": {
            "data_dir": get(config, "output", "data_dir", "data"),
            "audio_dir": get(config, "output", "audio_dir", "audio"),
            "site_source_dir": get(config, "output", "site_source_dir", "site"),
            "public_dir": get(config, "output", "public_dir", "public"),
        },
        "publishing": {
            "publish_target": get(config, "publishing", "publish_target", "github_pages"),
            "auto_commit": as_bool(get(config, "publishing", "auto_commit"), False),
            "auto_push": as_bool(get(config, "publishing", "auto_push"), False),
        },
    }


def validate_config(path: str | Path = "config.txt") -> list[ConfigError]:
    errors: list[ConfigError] = []
    raw = parse_config(path)
    config = normalized_config(path)

    timezone = config["schedule"]["timezone"]
    try:
        ZoneInfo(timezone)
    except Exception:
        errors.append(ConfigError("Invalid IANA time zone.", "schedule", "timezone"))

    run_time = config["schedule"]["daily_run_time"]
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", run_time):
        errors.append(ConfigError("Run time must use HH:MM 24-hour format.", "schedule", "daily_run_time"))

    if not config["news"]["topics"]:
        errors.append(ConfigError("At least one topic is required.", "news", "topics"))

    if config["news"]["news_count"] < 1:
        errors.append(ConfigError("news_count must be at least 1.", "news", "news_count"))

    if not config["news"]["sources"]:
        errors.append(ConfigError("At least one media source is required.", "news", "media_source_*"))

    for index, source in enumerate(config["news"]["sources"], start=1):
        if not source["name"]:
            errors.append(ConfigError("Media source name is required.", "news", f"media_source_{index}_name"))
        if not source["homepage"] and not source["feed"]:
            errors.append(ConfigError("Media source needs a homepage or feed.", "news", f"media_source_{index}"))

    cefr = config["rewriting"]["english_cefr_level"].upper()
    if cefr not in CEFR_LEVELS:
        errors.append(ConfigError("CEFR level must be A1, A2, B1, B2, C1, or C2.", "rewriting", "english_cefr_level"))

    if config["rewriting"]["max_english_words"] < 20:
        errors.append(ConfigError("max_english_words should be at least 20.", "rewriting", "max_english_words"))

    provider = config["audio"]["tts_provider"]
    if provider != "edge_tts":
        errors.append(ConfigError("Only edge_tts is implemented for now.", "audio", "tts_provider"))

    if config["audio"]["generate_mp3"] and not config["audio"]["english_voice"]:
        errors.append(ConfigError("English voice is required when MP3 generation is enabled.", "audio", "english_voice"))

    if "output" not in raw:
        errors.append(ConfigError("Missing output section.", "output", None))

    return errors
