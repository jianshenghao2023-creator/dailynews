from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path

import edge_tts
from docx import Document
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
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
    QVBoxLayout,
    QWidget,
    QLineEdit,
)


APP_TITLE = "Edge TTS Converter"
SUPPORTED_EXTENSIONS = {".txt", ".docx", ".docm"}

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


@dataclass(frozen=True)
class ConvertJob:
    source: Path
    output: Path
    voice: str
    rate: int


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


def safe_output_path(output_dir: Path, source: Path) -> Path:
    base = re.sub(r'[<>:"/\\|?*]+', "_", source.stem).strip() or "tts-output"
    candidate = output_dir / f"{base}.mp3"
    index = 2
    while candidate.exists():
        candidate = output_dir / f"{base}_{index}.mp3"
        index += 1
    return candidate


async def synthesize_to_mp3(text: str, voice: str, rate: int, output: Path) -> None:
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=rate_to_edge_value(rate),
    )
    await communicate.save(str(output))


def run_self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        source = tmpdir / "self-test.txt"
        source.write_text("This is a short self test for Microsoft Edge text to speech.", encoding="utf-8")
        output = tmpdir / "self-test.mp3"
        text = clean_text(read_input_file(source))
        asyncio.run(synthesize_to_mp3(text, "en-US-AvaNeural", -8, output))
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
                text = clean_text(read_input_file(job.source))
                if not text:
                    raise ValueError("No readable text found")

                self.status.emit(f"Converting {job.source.name}")
                asyncio.run(synthesize_to_mp3(text, job.voice, job.rate, job.output))
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
        self.resize(920, 620)
        self.selected_files: list[Path] = []
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

        self.voice_combo = QComboBox()
        self.voice_combo.setEditable(True)
        self.voice_combo.addItems(PRESET_VOICES)
        self.refresh_voices_button = QPushButton("Refresh Voices")
        settings_layout.addWidget(QLabel("Voice"), 1, 0)
        settings_layout.addWidget(self.voice_combo, 1, 1)
        settings_layout.addWidget(self.refresh_voices_button, 1, 2)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(-50, 50)
        self.speed_slider.setValue(0)
        self.speed_label = QLabel(rate_to_edge_value(0))
        self.speed_label.setMinimumWidth(60)
        settings_layout.addWidget(QLabel("Speed"), 2, 0)
        settings_layout.addWidget(self.speed_slider, 2, 1)
        settings_layout.addWidget(self.speed_label, 2, 2)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        main_layout.addWidget(self.file_list, stretch=2)

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
        self.speed_slider.valueChanged.connect(self.update_speed_label)
        self.start_button.clicked.connect(self.start_conversion)
        self.open_output_button.clicked.connect(self.open_output_folder)

    def show_about(self) -> None:
        QMessageBox.information(
            self,
            APP_TITLE,
            "Convert TXT and Word DOCX files to MP3 with Microsoft Edge TTS.\n\n"
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
        self._update_progress_label(0, len(self.selected_files))

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
        current = self.voice_combo.currentText().strip()
        self.voice_combo.clear()
        self.voice_combo.addItems(voices)
        if current:
            index = self.voice_combo.findText(current)
            if index >= 0:
                self.voice_combo.setCurrentIndex(index)
            else:
                self.voice_combo.setEditText(current)
        self.log(f"Loaded {len(voices)} voices")
        self.statusBar().showMessage(f"Loaded {len(voices)} voice(s)")

    def on_voice_refresh_failed(self, message: str) -> None:
        self.log(message)
        self.statusBar().showMessage("Voice refresh failed")

    def update_speed_label(self, value: int) -> None:
        self.speed_label.setText(rate_to_edge_value(value))

    def start_conversion(self) -> None:
        if self.convert_worker and self.convert_worker.isRunning():
            return
        if not self.selected_files:
            QMessageBox.information(self, APP_TITLE, "Please add one or more TXT or Word files.")
            return

        voice = self.voice_combo.currentText().strip()
        if not voice:
            QMessageBox.information(self, APP_TITLE, "Please choose or enter a voice name.")
            return

        output_dir = Path(self.output_edit.text()).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        rate = self.speed_slider.value()
        jobs = [
            ConvertJob(
                source=path,
                output=safe_output_path(output_dir, path),
                voice=voice,
                rate=rate,
            )
            for path in self.selected_files
        ]

        self.set_controls_enabled(False)
        self.progress_bar.setMaximum(len(jobs))
        self.progress_bar.setValue(0)
        self._update_progress_label(0, len(jobs))
        self.log(f"Starting {len(jobs)} job(s) with voice {voice}, speed {rate_to_edge_value(rate)}")
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
            self.voice_combo,
            self.speed_slider,
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
