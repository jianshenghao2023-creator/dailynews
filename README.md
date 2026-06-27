# DailyNews

DailyNews is planned as a Codex-driven daily news listening project.

Each daily run should:

1. Read `config.txt`.
2. Search the configured international media sources.
3. Select the configured number of recent topic-relevant stories.
4. Rewrite each story into short English at the configured CEFR level.
5. Generate a Simplified Chinese version.
6. Generate English MP3 audio and sentence-level subtitle timing.
7. Update the static site files for mobile listening.
8. Publish the static site to GitHub Pages once GitHub is configured.

The scheduled run time is configured in `config.txt` as 07:00 Europe/Berlin.

## Project Layout

- `config.txt` - Daily run configuration. Codex must read this first.
- `prompts/daily-run.md` - Durable prompt for the Codex automation.
- `schema/daily-news.schema.json` - Expected daily JSON shape.
- `data/` - Generated daily JSON files.
- `audio/` - Generated English MP3 and SRT files.
- `site/` - Static web app source.
- `docs/` - Built static site output for GitHub Pages deployment.
- `scripts/` - Future helper scripts for validation, audio, and site build steps.

## Current Status

The local pipeline is scaffolded and testable:

```powershell
.\.venv\Scripts\python.exe scripts\validate_config.py
.\.venv\Scripts\python.exe scripts\generate_audio.py --date 2026-06-27
.\.venv\Scripts\python.exe scripts\build_site.py
```

`data/2026-06-27.json` is demo content for testing the player. In normal daily runs, Codex should replace this pattern with real current news content generated from the configured sources.

Chinese text is generated for reading support, but Chinese MP3 is disabled by default.

To preview locally:

```powershell
.\.venv\Scripts\python.exe -m http.server 8787 --directory docs
```

Then open `http://127.0.0.1:8787/`.

For GitHub Pages, set the repository Pages source to branch `main` and folder `/docs`.
