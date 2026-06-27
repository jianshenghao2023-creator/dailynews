# DailyNews Daily Run Prompt

Read `config.txt` first and follow its settings exactly.

Daily workflow:

1. Determine today's date using the configured schedule time zone.
2. Search the configured media sources for the latest publicly accessible articles related to the configured topics.
3. Select the configured number of distinct, important stories.
4. For each selected story, write:
   - a short English version within the configured word limit,
   - at the configured CEFR level,
   - in a clear and neutral style,
   - with source attribution and source URL,
   - plus a Simplified Chinese version.
5. Generate or update `data/YYYY-MM-DD.json` using the schema in `schema/daily-news.schema.json`.
6. Run `.venv\Scripts\python.exe scripts\run_postprocess.py` from the project root. This validates config, generates Edge TTS MP3 files, writes subtitle timing, and builds `docs/`.
7. If GitHub publishing is configured and `auto_commit=true`, commit the changed `data/`, `audio/`, and `docs/` files.
8. If GitHub publishing is configured and `auto_push=true`, push the commit.

Do not invent source articles. If there are not enough reliable current articles, include fewer items and record the reason in the run notes.

The daily JSON should use this shape:

```json
{
  "date": "YYYY-MM-DD",
  "timezone": "Europe/Berlin",
  "generated_at": "ISO-8601 timestamp",
  "topics": ["topic"],
  "cefr_level": "B2",
  "max_english_words": 80,
  "items": [
    {
      "id": "news-001",
      "title": "Short headline",
      "source": {
        "name": "Source name",
        "url": "https://example.com/article"
      },
      "english": "Learner-friendly English text.",
      "chinese": "Simplified Chinese text.",
      "keywords": ["keyword"]
    }
  ],
  "run_notes": []
}
```
