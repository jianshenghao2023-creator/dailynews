# Edge TTS Converter

A Windows desktop tool for converting `.txt` and Word `.docx` files into natural reading or multi-speaker dialogue MP3 files with Microsoft Edge TTS voices.

## Features

- Select one or more `.txt`, `.docx`, or `.docm` files.
- Choose an output folder.
- Automatically detect ordinary reading text or speaker-labelled dialogue.
- Assign a separate Microsoft Edge TTS voice to every detected speaker and narrator.
- Adjust the pause between dialogue turns.
- Force Reading or Dialogue mode when automatic detection is not suitable.
- Adjust speech speed from -50% to +50%.
- Convert files one by one in the background.
- See current progress and messages in the status bar and log panel.

## Dialogue Formats

The app recognises common speaker labels. Text before the first labelled line is treated as narration.

```text
The train was nearly empty when Anna entered the carriage.

Anna: Is this seat free?
David: Yes, please sit down.
Anna: Thank you. It has been a long day.
```

Full-width Chinese colons, bracket labels, Markdown labels, pipe-separated Word table rows, and dash-separated labels are also supported:

```text
小明：你准备好了吗？
小红：准备好了，我们出发吧。

[Narrator] The lights slowly fade.
**Alex:** We should leave now.
Morgan | I agree.
```

In Auto detect mode, at least two distinct labelled speakers are required. Dialogue mode can be selected to process a script with only one labelled speaker. Ordinary text remains a single-voice reading.

## Portable Package

After building, copy this folder to another Windows computer:

```text
dist/EdgeTTSConverter/
```

Run:

```text
EdgeTTSConverter.exe
```

The target computer needs internet access because Microsoft Edge TTS is an online service. It does not need Python, FFmpeg, or Microsoft Word installed.

## Notes

- Modern Word files `.docx` and `.docm` are supported.
- Old binary `.doc` files are not supported by the portable build. Open them in Word and save as `.docx` first.
- Short stage directions at the start of a labelled turn, such as `(quietly)`, are not spoken.
- Narrator transitions use a slightly longer pause than speaker-to-speaker transitions.
- Very large documents may take several minutes.
- Existing MP3 files are not overwritten; the app adds a number to the filename.

## Development

Install requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r tools\edge-tts-converter\requirements.txt
```

Run from source:

```powershell
.\.venv\Scripts\python.exe tools\edge-tts-converter\edge_tts_converter.py
```

Build portable package:

```powershell
powershell -ExecutionPolicy Bypass -File tools\edge-tts-converter\build.ps1
```
