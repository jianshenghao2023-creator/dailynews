from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import edge_tts
import imageio_ffmpeg
from docx import Document
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSlider,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)


APP_TITLE = "Edge TTS Converter"
SUPPORTED_EXTENSIONS = {".txt", ".docx", ".docm"}
MODE_AUTO = "auto"
MODE_READING = "reading"
MODE_DIALOGUE = "dialogue"
NARRATOR_KEY = "__narrator__"

PRESET_VOICES = [
    "en-US-AvaNeural",
    "en-US-JennyNeural",
    "en-US-GuyNeural",
    "en-US-AriaNeural",
    "en-GB-RyanNeural",
    "en-GB-SoniaNeural",
    "en-GB-LibbyNeural",
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-YunjianNeural",
    "zh-CN-XiaoyiNeural",
    "de-DE-KatjaNeural",
    "de-DE-ConradNeural",
    "fr-FR-DeniseNeural",
    "es-ES-ElviraNeural",
]

ENGLISH_DIALOGUE_VOICES = [
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-GB-RyanNeural",
    "en-GB-SoniaNeural",
    "en-US-AriaNeural",
    "en-GB-LibbyNeural",
]

CHINESE_DIALOGUE_VOICES = [
    "zh-CN-YunxiNeural",
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-YunjianNeural",
    "zh-CN-XiaoyiNeural",
]

NARRATOR_ALIASES = {
    "narrator",
    "narration",
    "voice over",
    "voiceover",
    "旁白",
    "画外音",
    "解说",
}

NON_SPEAKER_LABELS = {
    "act",
    "author",
    "chapter",
    "category",
    "date",
    "description",
    "duration",
    "heading",
    "http",
    "https",
    "introduction",
    "keywords",
    "language",
    "location",
    "note",
    "scene",
    "source",
    "subject",
    "summary",
    "title",
    "time",
    "topic",
    "url",
    "作者",
    "日期",
    "场景",
    "标题",
    "来源",
    "章节",
    "主题",
    "说明",
}

SPEAKER_PATTERNS = [
    re.compile(r"^\s*\*\*(?P<label>[^\n:*：]{1,40})\s*[:：]\*\*\s*(?P<text>.*)\s*$"),
    re.compile(r"^\s*[\[【](?P<label>[^\]】\n]{1,40})[\]】]\s*[:：]?\s*(?P<text>.*)\s*$"),
    re.compile(r"^\s*(?P<label>[^\n:：|]{1,40})\s*[:：]\s*(?P<text>.*)\s*$"),
    re.compile(r"^\s*(?P<label>[^\n|]{1,40})\s*\|\s*(?P<text>.+)\s*$"),
    re.compile(r"^\s*(?P<label>[^\n—–-]{1,40})\s+[—–-]\s+(?P<text>.+)\s*$"),
]


@dataclass(frozen=True)
class ConvertJob:
    source: Path
    output: Path
    mode: str
    reading_voice: str
    narrator_voice: str
    role_voices: tuple[tuple[str, str], ...]
    rate: int
    dialogue_pause_ms: int


@dataclass(frozen=True)
class SpeechSegment:
    speaker: str
    speaker_key: str
    text: str
    is_narrator: bool


@dataclass(frozen=True)
class TextAnalysis:
    is_dialogue: bool
    segments: tuple[SpeechSegment, ...]
    speakers: tuple[str, ...]
    tagged_turns: int


def normalize_speaker_key(label: str) -> str:
    return " ".join(label.split()).casefold()


def is_narrator_label(label: str) -> bool:
    return normalize_speaker_key(label) in NARRATOR_ALIASES


def is_valid_speaker_label(label: str) -> bool:
    label = " ".join(label.strip().strip("*_#").split())
    if not label or len(label) > 40:
        return False
    if not re.search(r"[A-Za-z\u3400-\u9fff]", label):
        return False
    if re.search(r"[.!?。！？;,；，/]", label):
        return False
    if len(label.split()) > 5:
        return False
    first_word = normalize_speaker_key(label).split(maxsplit=1)[0]
    return first_word not in NON_SPEAKER_LABELS


def match_speaker_line(line: str) -> tuple[str, str] | None:
    candidate = re.sub(r"^\s*[-*]\s+(?=[^:：]{1,40}[:：])", "", line)
    for pattern in SPEAKER_PATTERNS:
        match = pattern.match(candidate)
        if not match:
            continue
        label = " ".join(match.group("label").strip().strip("*_#").split())
        if is_narrator_label(label) or is_valid_speaker_label(label):
            return label, match.group("text").strip()
    return None


def strip_leading_stage_direction(text: str) -> str:
    return re.sub(r"^\s*[\[(（【][^\])）】]{1,60}[\])）】]\s*", "", text).strip()


def append_segment(
    segments: list[SpeechSegment],
    speaker: str,
    speaker_key: str,
    text: str,
    is_narrator: bool,
) -> None:
    text = clean_text(strip_leading_stage_direction(text) if not is_narrator else text)
    if not text:
        return
    if segments and segments[-1].speaker_key == speaker_key:
        previous = segments[-1]
        segments[-1] = SpeechSegment(
            speaker=previous.speaker,
            speaker_key=previous.speaker_key,
            text=f"{previous.text} {text}",
            is_narrator=previous.is_narrator,
        )
        return
    segments.append(
        SpeechSegment(
            speaker=speaker,
            speaker_key=speaker_key,
            text=text,
            is_narrator=is_narrator,
        )
    )


def analyze_text(text: str, mode: str = MODE_AUTO) -> TextAnalysis:
    if mode == MODE_READING:
        cleaned = clean_text(text)
        segments = (
            SpeechSegment("Narrator", NARRATOR_KEY, cleaned, True),
        ) if cleaned else ()
        return TextAnalysis(False, segments, (), 0)

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    markers: list[tuple[int, str, str]] = []
    speaker_names: dict[str, str] = {}
    narrator_was_tagged = False

    for index, line in enumerate(lines):
        matched = match_speaker_line(line)
        if not matched:
            continue
        label, spoken_text = matched
        key = normalize_speaker_key(label)
        markers.append((index, label, spoken_text))
        if is_narrator_label(label):
            narrator_was_tagged = True
        else:
            speaker_names.setdefault(key, label)

    tagged_turns = len(markers)
    auto_dialogue = tagged_turns >= 2 and (
        len(speaker_names) >= 2 or (len(speaker_names) >= 1 and narrator_was_tagged)
    )
    is_dialogue = tagged_turns >= 1 if mode == MODE_DIALOGUE else auto_dialogue

    if not is_dialogue:
        cleaned = clean_text(text)
        segments = (
            SpeechSegment("Narrator", NARRATOR_KEY, cleaned, True),
        ) if cleaned else ()
        return TextAnalysis(False, segments, (), tagged_turns)

    recognized_keys = set(speaker_names)
    segments_list: list[SpeechSegment] = []
    block_speaker: tuple[str, str, bool] | None = None

    for line in lines:
        if not line.strip():
            block_speaker = None
            continue

        matched = match_speaker_line(line)
        if matched:
            label, spoken_text = matched
            is_narrator = is_narrator_label(label)
            key = NARRATOR_KEY if is_narrator else normalize_speaker_key(label)
            if is_narrator or key in recognized_keys:
                display_name = "Narrator" if is_narrator else speaker_names[key]
                spoken_text = strip_leading_stage_direction(spoken_text)
                if spoken_text:
                    append_segment(segments_list, display_name, key, spoken_text, is_narrator)
                    block_speaker = None
                else:
                    block_speaker = (display_name, key, is_narrator)
                continue

        if block_speaker:
            display_name, key, is_narrator = block_speaker
            append_segment(segments_list, display_name, key, line, is_narrator)
        else:
            append_segment(segments_list, "Narrator", NARRATOR_KEY, line, True)

    ordered_speakers: list[str] = []
    seen_speakers: set[str] = set()
    for segment in segments_list:
        if segment.is_narrator or segment.speaker_key in seen_speakers:
            continue
        seen_speakers.add(segment.speaker_key)
        ordered_speakers.append(segment.speaker)

    return TextAnalysis(True, tuple(segments_list), tuple(ordered_speakers), tagged_turns)


def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def read_txt(path: Path) -> str:
    encodings = ["utf-8-sig", "utf-8", "utf-16", "gb18030", "big5", "cp1252"]
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def read_docx(path: Path) -> str:
    document = Document(str(path))
    parts: list[str] = []

    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            parts.append(paragraph.text)

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    return "\n".join(parts)


def read_input_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return read_txt(path)
    if suffix in {".docx", ".docm"}:
        return read_docx(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def rate_to_edge_value(rate: int) -> str:
    sign = "+" if rate >= 0 else ""
    return f"{sign}{rate}%"


def safe_output_path(
    output_dir: Path,
    source: Path,
    reserved_paths: set[Path] | None = None,
) -> Path:
    base = re.sub(r'[<>:"/\\|?*]+', "_", source.stem).strip() or "tts-output"
    candidate = output_dir / f"{base}.mp3"
    index = 2
    reserved_paths = reserved_paths if reserved_paths is not None else set()
    while candidate.exists() or candidate.resolve() in reserved_paths:
        candidate = output_dir / f"{base}_{index}.mp3"
        index += 1
    reserved_paths.add(candidate.resolve())
    return candidate


async def synthesize_to_mp3(text: str, voice: str, rate: int, output: Path) -> None:
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate_to_edge_value(rate),
    )
    await communicate.save(str(output))


def run_ffmpeg(arguments: list[str]) -> None:
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip().splitlines()
        message = details[-1] if details else "Unknown FFmpeg error"
        raise RuntimeError(f"Could not combine dialogue audio: {message}")


def create_silence_mp3(output: Path, duration_ms: int) -> None:
    run_ffmpeg(
        [
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            f"{duration_ms / 1000:.3f}",
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "48k",
            str(output),
        ]
    )


def combine_dialogue_mp3(
    segment_files: list[Path],
    segments: tuple[SpeechSegment, ...],
    pause_ms: int,
    output: Path,
) -> None:
    if len(segment_files) == 1:
        shutil.copyfile(segment_files[0], output)
        return

    work_dir = segment_files[0].parent
    standard_pause = work_dir / "pause.mp3"
    narrator_pause = work_dir / "narrator-pause.mp3"
    if pause_ms > 0:
        create_silence_mp3(standard_pause, pause_ms)
        create_silence_mp3(narrator_pause, min(2500, pause_ms + 250))

    concat_lines: list[str] = []
    for index, segment_file in enumerate(segment_files):
        concat_lines.append(f"file '{segment_file.name}'")
        if pause_ms <= 0 or index == len(segment_files) - 1:
            continue
        transition_uses_narrator = segments[index].is_narrator or segments[index + 1].is_narrator
        pause_file = narrator_pause if transition_uses_narrator else standard_pause
        concat_lines.append(f"file '{pause_file.name}'")

    concat_file = work_dir / "dialogue-concat.txt"
    concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
    run_ffmpeg(
        [
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-ar",
            "24000",
            "-ac",
            "1",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "48k",
            str(output),
        ]
    )


async def synthesize_dialogue_segments(
    segments: tuple[SpeechSegment, ...],
    role_voices: dict[str, str],
    narrator_voice: str,
    fallback_voice: str,
    rate: int,
    work_dir: Path,
    progress_callback: Callable[[int, int, SpeechSegment], None] | None = None,
) -> list[Path]:
    segment_files: list[Path] = []
    total = len(segments)
    for index, segment in enumerate(segments, start=1):
        voice = narrator_voice if segment.is_narrator else role_voices.get(
            segment.speaker_key,
            fallback_voice,
        )
        segment_file = work_dir / f"segment-{index:04d}.mp3"
        if progress_callback:
            progress_callback(index, total, segment)
        await synthesize_to_mp3(segment.text, voice, rate, segment_file)
        segment_files.append(segment_file)
    return segment_files


def synthesize_dialogue_to_mp3(
    analysis: TextAnalysis,
    role_voices: dict[str, str],
    narrator_voice: str,
    fallback_voice: str,
    rate: int,
    pause_ms: int,
    output: Path,
    progress_callback: Callable[[int, int, SpeechSegment], None] | None = None,
) -> None:
    with tempfile.TemporaryDirectory(prefix="edge-tts-dialogue-") as tmp:
        work_dir = Path(tmp)
        segment_files = asyncio.run(
            synthesize_dialogue_segments(
                analysis.segments,
                role_voices,
                narrator_voice,
                fallback_voice,
                rate,
                work_dir,
                progress_callback,
            )
        )
        combined_output = work_dir / "combined.mp3"
        combine_dialogue_mp3(
            segment_files,
            analysis.segments,
            pause_ms,
            combined_output,
        )
        shutil.copyfile(combined_output, output)


def run_self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        source = tmpdir / "self-test.txt"
        source.write_text(
            "Ava: This is a short dialogue self test.\nRyan: The audio tools are working.",
            encoding="utf-8",
        )
        output = tmpdir / "self-test.mp3"
        analysis = analyze_text(read_input_file(source), MODE_AUTO)
        if not analysis.is_dialogue:
            return 1
        synthesize_dialogue_to_mp3(
            analysis=analysis,
            role_voices={"ava": "en-US-AvaNeural", "ryan": "en-GB-RyanNeural"},
            narrator_voice="en-US-AvaNeural",
            fallback_voice="en-US-AvaNeural",
            rate=-8,
            pause_ms=250,
            output=output,
        )
        if not output.exists() or output.stat().st_size == 0:
            return 1
    return 0


class ConvertWorker(QThread):
    progress = Signal(int, int)
    status = Signal(str)
    log = Signal(str)
    finished_summary = Signal(int, int)

    def __init__(self, jobs: list[ConvertJob]) -> None:
        super().__init__()
        self.jobs = jobs

    def run(self) -> None:
        completed = 0
        failed = 0
        total = len(self.jobs)

        for index, job in enumerate(self.jobs, start=1):
            try:
                self.status.emit(f"Reading {job.source.name}")
                source_text = read_input_file(job.source)
                if not clean_text(source_text):
                    raise ValueError("No readable text found")

                analysis = analyze_text(source_text, job.mode)
                if analysis.is_dialogue:
                    if not analysis.segments:
                        raise ValueError("No speakable dialogue text found")
                    role_voices = dict(job.role_voices)
                    self.log.emit(
                        f"Dialogue detected: {job.source.name} - "
                        f"{len(analysis.speakers)} speaker(s), {len(analysis.segments)} turn(s)"
                    )

                    def report_turn(done: int, turn_total: int, segment: SpeechSegment) -> None:
                        self.status.emit(
                            f"{job.source.name}: turn {done}/{turn_total} ({segment.speaker})"
                        )

                    synthesize_dialogue_to_mp3(
                        analysis=analysis,
                        role_voices=role_voices,
                        narrator_voice=job.narrator_voice,
                        fallback_voice=job.reading_voice,
                        rate=job.rate,
                        pause_ms=job.dialogue_pause_ms,
                        output=job.output,
                        progress_callback=report_turn,
                    )
                else:
                    self.status.emit(f"Converting {job.source.name} as reading")
                    asyncio.run(
                        synthesize_to_mp3(
                            clean_text(source_text),
                            job.reading_voice,
                            job.rate,
                            job.output,
                        )
                    )
                completed += 1
                self.log.emit(f"Done: {job.source.name} -> {job.output.name}")
            except Exception as exc:
                failed += 1
                self.log.emit(f"Failed: {job.source.name} - {exc}")
                self.log.emit(traceback.format_exc())
            finally:
                self.progress.emit(index, total)

        self.finished_summary.emit(completed, failed)


class VoiceRefreshWorker(QThread):
    voices_loaded = Signal(list)
    failed = Signal(str)

    def run(self) -> None:
        try:
            voices = asyncio.run(edge_tts.list_voices())
            names = sorted({voice["ShortName"] for voice in voices if "ShortName" in voice})
            self.voices_loaded.emit(names)
        except Exception as exc:
            self.failed.emit(f"Could not refresh voices: {exc}")


class EdgeTTSConverterWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1020, 800)
        self.selected_files: list[Path] = []
        self.available_voices = list(PRESET_VOICES)
        self.role_voice_choices: dict[str, str] = {}
        self.detected_speaker_samples: dict[str, tuple[str, str]] = {}
        self.convert_worker: ConvertWorker | None = None
        self.voice_worker: VoiceRefreshWorker | None = None

        self._build_ui()
        self._build_menu()
        self._update_progress_label(0, 0)
        self.statusBar().showMessage("Ready")

    def _build_menu(self) -> None:
        help_menu = self.menuBar().addMenu("Help")
        about = QAction("About", self)
        about.triggered.connect(self.show_about)
        help_menu.addAction(about)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        file_bar = QHBoxLayout()
        self.add_button = QPushButton("Add Files")
        self.remove_button = QPushButton("Remove Selected")
        self.clear_button = QPushButton("Clear")
        file_bar.addWidget(self.add_button)
        file_bar.addWidget(self.remove_button)
        file_bar.addWidget(self.clear_button)
        file_bar.addStretch(1)
        main_layout.addLayout(file_bar)

        settings_group = QGroupBox("Settings")
        settings_layout = QGridLayout(settings_group)
        main_layout.addWidget(settings_group)

        self.output_edit = QLineEdit(str(Path.home() / "Desktop" / "EdgeTTS_MP3"))
        self.output_button = QPushButton("Browse")
        settings_layout.addWidget(QLabel("Output folder"), 0, 0)
        settings_layout.addWidget(self.output_edit, 0, 1)
        settings_layout.addWidget(self.output_button, 0, 2)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Auto detect", MODE_AUTO)
        self.mode_combo.addItem("Reading", MODE_READING)
        self.mode_combo.addItem("Dialogue", MODE_DIALOGUE)
        settings_layout.addWidget(QLabel("Text mode"), 1, 0)
        settings_layout.addWidget(self.mode_combo, 1, 1, 1, 2)

        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        self.voice_combo.addItems(self.available_voices)
        self.refresh_voices_button = QPushButton("Refresh Voices")
        settings_layout.addWidget(QLabel("Reading voice"), 2, 0)
        settings_layout.addWidget(self.voice_combo, 2, 1)
        settings_layout.addWidget(self.refresh_voices_button, 2, 2)

        self.narrator_voice_combo = QComboBox()
        self.narrator_voice_combo.setEditable(True)
        self.narrator_voice_combo.addItems(self.available_voices)
        self.narrator_voice_combo.setCurrentText("en-US-AvaNeural")
        settings_layout.addWidget(QLabel("Narrator voice"), 3, 0)
        settings_layout.addWidget(self.narrator_voice_combo, 3, 1, 1, 2)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(-50, 50)
        self.speed_slider.setValue(0)
        self.speed_label = QLabel(rate_to_edge_value(0))
        self.speed_label.setMinimumWidth(60)
        settings_layout.addWidget(QLabel("Speed"), 4, 0)
        settings_layout.addWidget(self.speed_slider, 4, 1)
        settings_layout.addWidget(self.speed_label, 4, 2)

        self.pause_slider = QSlider(Qt.Orientation.Horizontal)
        self.pause_slider.setRange(0, 2000)
        self.pause_slider.setSingleStep(50)
        self.pause_slider.setPageStep(100)
        self.pause_slider.setValue(550)
        self.pause_label = QLabel("550 ms")
        self.pause_label.setMinimumWidth(60)
        settings_layout.addWidget(QLabel("Turn pause"), 5, 0)
        settings_layout.addWidget(self.pause_slider, 5, 1)
        settings_layout.addWidget(self.pause_label, 5, 2)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        main_layout.addWidget(self.file_list, stretch=2)

        dialogue_group = QGroupBox("Dialogue Voices")
        dialogue_layout = QVBoxLayout(dialogue_group)
        self.role_table = QTableWidget(0, 2)
        self.role_table.setHorizontalHeaderLabels(["Speaker", "Voice"])
        self.role_table.verticalHeader().setVisible(False)
        self.role_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.role_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.role_table.setMinimumHeight(135)
        dialogue_layout.addWidget(self.role_table)
        main_layout.addWidget(dialogue_group, stretch=1)

        action_bar = QHBoxLayout()
        self.start_button = QPushButton("Start Convert")
        self.open_output_button = QPushButton("Open Output Folder")
        action_bar.addWidget(self.start_button)
        action_bar.addWidget(self.open_output_button)
        action_bar.addStretch(1)
        main_layout.addLayout(action_bar)

        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group, stretch=1)

        status = QStatusBar()
        self.setStatusBar(status)
        self.progress_label = QLabel()
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumWidth(260)
        status.addPermanentWidget(self.progress_label)
        status.addPermanentWidget(self.progress_bar)

        self.add_button.clicked.connect(self.add_files)
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.clear_files)
        self.output_button.clicked.connect(self.choose_output_dir)
        self.refresh_voices_button.clicked.connect(self.refresh_voices)
        self.mode_combo.currentIndexChanged.connect(self.refresh_detected_speakers)
        self.speed_slider.valueChanged.connect(self.update_speed_label)
        self.pause_slider.valueChanged.connect(self.update_pause_label)
        self.start_button.clicked.connect(self.start_conversion)
        self.open_output_button.clicked.connect(self.open_output_folder)

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            APP_TITLE,
            "Convert TXT and Word DOCX files to MP3 with Microsoft Edge TTS.\n"
            "Dialogue text can use a different voice for each speaker and narrator.\n\n"
            "Internet access is required. Old .doc files should be saved as .docx first.",
        )

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select text or Word files",
            "",
            "Text and Word files (*.txt *.docx *.docm);;Text files (*.txt);;Word files (*.docx *.docm);;All files (*.*)",
        )
        if not paths:
            return

        known = {path.resolve() for path in self.selected_files}
        unsupported: list[str] = []
        added = 0

        for raw_path in paths:
            path = Path(raw_path)
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                unsupported.append(path.name)
                continue
            resolved = path.resolve()
            if resolved not in known:
                self.selected_files.append(path)
                known.add(resolved)
                added += 1

        self.refresh_file_list()
        if unsupported:
            self.log(f"Skipped unsupported files: {', '.join(unsupported)}")
        if added:
            self.statusBar().showMessage(f"Added {added} file(s)")

    def remove_selected(self) -> None:
        selected_rows = sorted({index.row() for index in self.file_list.selectedIndexes()}, reverse=True)
        if not selected_rows:
            return
        for row in selected_rows:
            self.selected_files.pop(row)
        self.refresh_file_list()
        self.statusBar().showMessage("Selected file(s) removed")

    def clear_files(self) -> None:
        self.selected_files.clear()
        self.refresh_file_list()
        self.statusBar().showMessage("File list cleared")

    def refresh_file_list(self) -> None:
        self.file_list.clear()
        for path in self.selected_files:
            item = QListWidgetItem(str(path))
            item.setToolTip(str(path))
            self.file_list.addItem(item)
        self.refresh_detected_speakers()
        self._update_progress_label(0, len(self.selected_files))

    def current_mode(self) -> str:
        return self.mode_combo.currentData() or MODE_AUTO

    def default_role_voice(self, index: int, sample_text: str) -> str:
        cjk_count = len(re.findall(r"[\u3400-\u9fff]", sample_text))
        latin_count = len(re.findall(r"[A-Za-z]", sample_text))
        pool = CHINESE_DIALOGUE_VOICES if cjk_count > latin_count else ENGLISH_DIALOGUE_VOICES
        return pool[index % len(pool)]

    def refresh_detected_speakers(self) -> None:
        if not hasattr(self, "role_table"):
            return

        for row in range(self.role_table.rowCount()):
            item = self.role_table.item(row, 0)
            combo = self.role_table.cellWidget(row, 1)
            if item and isinstance(combo, QComboBox):
                key = item.data(Qt.ItemDataRole.UserRole)
                if key:
                    self.role_voice_choices[key] = combo.currentText().strip()

        samples: dict[str, tuple[str, str]] = {}
        mode = self.current_mode()
        if mode != MODE_READING:
            for path in self.selected_files:
                try:
                    analysis = analyze_text(read_input_file(path), mode)
                except Exception as exc:
                    self.log(f"Could not inspect {path.name}: {exc}")
                    continue
                if not analysis.is_dialogue:
                    continue
                for segment in analysis.segments:
                    if segment.is_narrator:
                        continue
                    samples.setdefault(segment.speaker_key, (segment.speaker, segment.text))

        self.detected_speaker_samples = samples
        self.role_table.setRowCount(0)
        for row, (key, (display_name, sample_text)) in enumerate(samples.items()):
            self.role_table.insertRow(row)
            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, key)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setToolTip(sample_text[:240])
            self.role_table.setItem(row, 0, name_item)

            voice_combo = QComboBox()
            voice_combo.setEditable(True)
            voice_combo.addItems(self.available_voices)
            selected_voice = self.role_voice_choices.get(key)
            if not selected_voice:
                selected_voice = self.default_role_voice(row, sample_text)
                self.role_voice_choices[key] = selected_voice
            voice_combo.setCurrentText(selected_voice)
            voice_combo.currentTextChanged.connect(
                lambda value, speaker_key=key: self.role_voice_choices.__setitem__(
                    speaker_key,
                    value.strip(),
                )
            )
            self.role_table.setCellWidget(row, 1, voice_combo)

    def replace_combo_voices(self, combo: QComboBox, voices: list[str]) -> None:
        current = combo.currentText().strip()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(voices)
        combo.setCurrentText(current)
        combo.blockSignals(False)

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if path:
            self.output_edit.setText(path)

    def open_output_folder(self) -> None:
        output_dir = Path(self.output_edit.text()).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(output_dir))

    def refresh_voices(self) -> None:
        if self.convert_worker and self.convert_worker.isRunning():
            return
        self.statusBar().showMessage("Fetching voice list...")
        self.refresh_voices_button.setEnabled(False)
        self.voice_worker = VoiceRefreshWorker()
        self.voice_worker.voices_loaded.connect(self.on_voices_loaded)
        self.voice_worker.failed.connect(self.on_voice_refresh_failed)
        self.voice_worker.finished.connect(lambda: self.refresh_voices_button.setEnabled(True))
        self.voice_worker.start()

    def on_voices_loaded(self, voices: list[str]) -> None:
        self.available_voices = voices
        self.replace_combo_voices(self.voice_combo, voices)
        self.replace_combo_voices(self.narrator_voice_combo, voices)
        self.refresh_detected_speakers()
        self.log(f"Loaded {len(voices)} voices")
        self.statusBar().showMessage(f"Loaded {len(voices)} voice(s)")

    def on_voice_refresh_failed(self, message: str) -> None:
        self.log(message)
        self.statusBar().showMessage("Voice refresh failed")

    def update_speed_label(self, value: int) -> None:
        self.speed_label.setText(rate_to_edge_value(value))

    def update_pause_label(self, value: int) -> None:
        self.pause_label.setText(f"{value} ms")

    def start_conversion(self) -> None:
        if self.convert_worker and self.convert_worker.isRunning():
            return
        if not self.selected_files:
            QMessageBox.information(self, APP_TITLE, "Please add one or more TXT or Word files.")
            return

        reading_voice = self.voice_combo.currentText().strip()
        narrator_voice = self.narrator_voice_combo.currentText().strip()
        if not reading_voice or not narrator_voice:
            QMessageBox.information(self, APP_TITLE, "Please choose the reading and narrator voices.")
            return

        self.refresh_detected_speakers()
        role_voices = tuple(
            (key, self.role_voice_choices.get(key, "").strip())
            for key in self.detected_speaker_samples
        )
        missing_roles = [
            display_name
            for key, (display_name, _) in self.detected_speaker_samples.items()
            if not self.role_voice_choices.get(key, "").strip()
        ]
        if missing_roles:
            QMessageBox.information(
                self,
                APP_TITLE,
                f"Please choose a voice for: {', '.join(missing_roles)}",
            )
            return

        output_dir = Path(self.output_edit.text()).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        rate = self.speed_slider.value()
        mode = self.current_mode()
        jobs: list[ConvertJob] = []
        reserved_outputs: set[Path] = set()
        for path in self.selected_files:
            jobs.append(
                ConvertJob(
                    source=path,
                    output=safe_output_path(output_dir, path, reserved_outputs),
                    mode=mode,
                    reading_voice=reading_voice,
                    narrator_voice=narrator_voice,
                    role_voices=role_voices,
                    rate=rate,
                    dialogue_pause_ms=self.pause_slider.value(),
                )
            )

        self.set_controls_enabled(False)
        self.progress_bar.setMaximum(len(jobs))
        self.progress_bar.setValue(0)
        self._update_progress_label(0, len(jobs))
        self.log(
            f"Starting {len(jobs)} job(s), mode {mode}, speed {rate_to_edge_value(rate)}, "
            f"turn pause {self.pause_slider.value()} ms"
        )
        self.statusBar().showMessage("Converting...")

        self.convert_worker = ConvertWorker(jobs)
        self.convert_worker.status.connect(self.statusBar().showMessage)
        self.convert_worker.log.connect(self.log)
        self.convert_worker.progress.connect(self.on_progress)
        self.convert_worker.finished_summary.connect(self.on_finished)
        self.convert_worker.start()

    def set_controls_enabled(self, enabled: bool) -> None:
        for widget in [
            self.add_button,
            self.remove_button,
            self.clear_button,
            self.output_button,
            self.refresh_voices_button,
            self.mode_combo,
            self.voice_combo,
            self.narrator_voice_combo,
            self.speed_slider,
            self.pause_slider,
            self.role_table,
            self.start_button,
        ]:
            widget.setEnabled(enabled)

    def on_progress(self, done: int, total: int) -> None:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)
        self._update_progress_label(done, total)

    def on_finished(self, completed: int, failed: int) -> None:
        self.set_controls_enabled(True)
        self.statusBar().showMessage(f"Finished: {completed} done, {failed} failed")
        self.log(f"Finished: {completed} done, {failed} failed")

    def _update_progress_label(self, done: int, total: int) -> None:
        self.progress_label.setText(f"{done} / {total}")

    def log(self, message: str) -> None:
        self.log_text.appendPlainText(message.rstrip())


def main() -> int:
    if "--self-test" in sys.argv:
        return run_self_test()

    app = QApplication(sys.argv)
    window = EdgeTTSConverterWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
