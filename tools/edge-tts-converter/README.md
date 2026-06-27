# Edge TTS Converter

A small Windows desktop tool for converting `.txt` and Word `.docx` files into MP3 files with Microsoft Edge TTS voices.

## Features

- Select one or more `.txt`, `.docx`, or `.docm` files.
- Choose an output folder.
- Choose a Microsoft Edge TTS voice.
- Adjust speech speed from -50% to +50%.
- Convert files one by one in the background.
- See current progress and messages in the status bar and log panel.

## Portable Package

After building, copy this folder to another Windows computer:

```text
dist/EdgeTTSConverter/
```

Run:

```text
EdgeTTSConverter.exe
```

The target computer needs internet access because Microsoft Edge TTS is an online service. It does not need Python installed.

## Notes

- Modern Word files `.docx` and `.docm` are supported.
- Old binary `.doc` files are not supported by the portable build. Open them in Word and save as `.docx` first.
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
