# Edge TTS Converter

A Windows desktop tool for converting `.txt` and Word `.docx` files into natural reading or multi-speaker dialogue MP3 files with Microsoft Edge TTS voices.

## Features

- Select one or more `.txt`, `.docx`, or `.docm` files.
- Choose an output folder.
- Automatically detect dialogue only when the strict tags below are present.
- Assign a separate Microsoft Edge TTS voice to every detected speaker and narrator.
- Adjust the pause between dialogue turns.
- Generate follow-along audio with a pause 1.2 times each sentence's spoken duration.
- Force Reading or Dialogue mode when automatic detection is not suitable.
- Adjust speech speed from -50% to +50%.
- Convert files one by one in the background.
- See current progress and messages in the status bar and log panel.

## Dialogue Format

Only the following tags are recognised. The tag and its text must be on the same line.

```text
[narration]: The train was nearly empty when Anna entered the carriage.
[speaker: Anna]: Is this seat free?
[speaker: David]: Yes, please sit down.
[speaker: Anna]: Thank you. It has been a long day.
```

For a single unnamed speaker, the short form is supported:

```text
[speaker]: This line uses the generic Speaker voice.
```

Names followed by colons, full-width colons, dashes, Markdown, pipe separators, and other bracket formats are not treated as dialogue markers. In a tagged dialogue file, non-empty unmarked lines are skipped and reported in the log. A file with no valid tags remains a normal single-voice reading in Auto detect mode.

`dialogue_prompt.txt` contains a reusable prompt for asking a language model to produce this format. It is included beside the portable app and can be opened from **Help > Open Dialogue Prompt**.

## Follow-Along Mode

When Follow-along mode is selected, the app splits the material into sentences, generates each sentence separately, measures its actual audio duration, and adds silence equal to 1.2 times that duration. This works for both normal reading and tagged dialogue. The normal turn-pause setting is disabled in this mode.

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
