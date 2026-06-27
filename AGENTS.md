# DailyNews Agent Notes

Always read `config.txt` before changing generated content, prompts, audio, or publishing behavior.

Daily content must be generated from current news sources and the configured topics. Do not hard-code news items into scripts or frontend code.

Keep generated daily content in `data/`, generated audio in `audio/`, and deployable static files in `docs/`.

When implementing the site, prefer a mobile-first static PWA that can run from GitHub Pages.

Use `Europe/Berlin` for the daily schedule unless the user changes `config.txt`.

Daily content generation belongs to Codex automation, not hard-coded scripts. Scripts may validate configuration, generate audio from text, copy static assets, and build deployment output.

After Codex writes `data/YYYY-MM-DD.json`, run `.venv\Scripts\python.exe scripts\run_postprocess.py` from the project root.
