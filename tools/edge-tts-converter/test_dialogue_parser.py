import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from mutagen.id3 import ID3

from edge_tts_converter import (
    FOLLOW_ALONG_PAUSE_MULTIPLIER,
    LyricCue,
    MODE_AUTO,
    MODE_DIALOGUE,
    NARRATOR_KEY,
    RenderedSegment,
    SpeechSegment,
    analyze_text,
    build_dialogue_lyric_cues,
    build_follow_along_lyric_cues,
    create_silence_mp3,
    expand_segments_to_sentences,
    format_lrc_timestamp,
    probe_audio_duration_ms,
    safe_output_path,
    split_sentences,
    write_synchronized_lyrics,
)


class DialogueParserTests(unittest.TestCase):
    def test_plain_article_remains_reading(self) -> None:
        text = "A winter morning\nThe streets were quiet and the first bus arrived early."
        analysis = analyze_text(text, MODE_AUTO)

        self.assertFalse(analysis.is_dialogue)
        self.assertEqual(analysis.speakers, ())
        self.assertEqual(len(analysis.segments), 1)

    def test_only_strict_tags_are_dialogue(self) -> None:
        nonstandard_text = """Anna: Is this seat free?
小明：你准备好了吗？
David - Yes, please sit down.
[Narrator] The train was nearly empty."""
        analysis = analyze_text(nonstandard_text, MODE_AUTO)

        self.assertFalse(analysis.is_dialogue)
        self.assertEqual(analysis.tagged_turns, 0)

    def test_named_speakers_and_narration_are_detected(self) -> None:
        text = """[narration]: The train was nearly empty.
[speaker: Anna]: Is this seat free?
[speaker: David]: Yes, please sit down.
[speaker: Anna]: Thank you."""
        analysis = analyze_text(text, MODE_AUTO)

        self.assertTrue(analysis.is_dialogue)
        self.assertEqual(analysis.speakers, ("Anna", "David"))
        self.assertEqual(analysis.segments[0].speaker_key, NARRATOR_KEY)
        self.assertEqual(
            [segment.speaker for segment in analysis.segments],
            ["Narrator", "Anna", "David", "Anna"],
        )

    def test_generic_speaker_tag_is_supported(self) -> None:
        analysis = analyze_text("[speaker]: Welcome to the programme.", MODE_AUTO)

        self.assertTrue(analysis.is_dialogue)
        self.assertEqual(analysis.speakers, ("Speaker",))
        self.assertEqual(analysis.segments[0].speaker_key, "speaker")

    def test_tags_are_case_insensitive(self) -> None:
        text = "[NARRATION]: The room grows quiet.\n[SPEAKER: Anna]: We can begin."
        analysis = analyze_text(text, MODE_AUTO)

        self.assertTrue(analysis.is_dialogue)
        self.assertEqual(analysis.speakers, ("Anna",))

    def test_unmarked_lines_are_skipped_in_dialogue(self) -> None:
        text = "Heading to skip\n[speaker: Anna]: Hello.\nAnother note to skip"
        analysis = analyze_text(text, MODE_AUTO)

        self.assertTrue(analysis.is_dialogue)
        self.assertEqual(len(analysis.segments), 1)
        self.assertEqual(analysis.ignored_lines, 2)

    def test_forced_dialogue_rejects_text_without_tags(self) -> None:
        analysis = analyze_text("Anna: This is not a strict tag.", MODE_DIALOGUE)

        self.assertTrue(analysis.is_dialogue)
        self.assertEqual(analysis.segments, ())
        self.assertEqual(analysis.ignored_lines, 1)

    def test_sentence_splitter_handles_english_and_chinese(self) -> None:
        sentences = split_sentences("Are you ready? I am ready! 我们出发吧。好的！")

        self.assertEqual(
            sentences,
            ["Are you ready?", "I am ready!", "我们出发吧。", "好的！"],
        )

    def test_sentence_splitter_keeps_common_abbreviations(self) -> None:
        sentences = split_sentences("Dr. Smith is here. The U.S. team arrived.")

        self.assertEqual(sentences, ["Dr. Smith is here.", "The U.S. team arrived."])

    def test_dialogue_turns_expand_to_sentences(self) -> None:
        analysis = analyze_text(
            "[speaker: Anna]: First sentence. Second sentence?",
            MODE_AUTO,
        )
        expanded = expand_segments_to_sentences(analysis.segments)

        self.assertEqual(len(expanded), 2)
        self.assertTrue(all(segment.speaker == "Anna" for segment in expanded))

    def test_generated_silence_duration_can_be_measured(self) -> None:
        with TemporaryDirectory() as tmp:
            silence_path = Path(tmp) / "silence.mp3"
            expected_ms = round(500 * FOLLOW_ALONG_PAUSE_MULTIPLIER)
            create_silence_mp3(silence_path, expected_ms)
            measured_ms = probe_audio_duration_ms(silence_path)

            self.assertLessEqual(abs(measured_ms - expected_ms), 80)

    def test_lrc_timestamp_format(self) -> None:
        self.assertEqual(format_lrc_timestamp(62_340), "01:02.34")

    def test_dialogue_lyrics_include_turn_pause(self) -> None:
        segments = (
            SpeechSegment("Narrator", NARRATOR_KEY, "Opening.", True),
            SpeechSegment("Anna", "anna", "Hello.", False),
        )
        rendered = [
            RenderedSegment(Path("one.mp3"), 1000, (LyricCue(100, 900, "Opening."),)),
            RenderedSegment(Path("two.mp3"), 500, (LyricCue(50, 450, "Hello."),)),
        ]

        cues = build_dialogue_lyric_cues(rendered, segments, [800, 0])

        self.assertEqual(cues[0].start_ms, 100)
        self.assertEqual(cues[1].start_ms, 1850)
        self.assertEqual(cues[1].text, "Anna: Hello.")

    def test_follow_along_lyrics_include_sentence_silence(self) -> None:
        segments = (
            SpeechSegment("Narrator", NARRATOR_KEY, "First.", True),
            SpeechSegment("Narrator", NARRATOR_KEY, "Second.", True),
        )
        rendered = [
            RenderedSegment(Path("one.mp3"), 1000, (LyricCue(0, 900, "First."),)),
            RenderedSegment(Path("two.mp3"), 500, (LyricCue(0, 450, "Second."),)),
        ]

        cues = build_follow_along_lyric_cues(
            rendered,
            segments,
            is_dialogue=False,
            applied_pauses_ms=[1200, 600],
        )

        self.assertEqual(cues[0].start_ms, 0)
        self.assertEqual(cues[1].start_ms, 2200)

    def test_lrc_and_embedded_id3_lyrics_are_written(self) -> None:
        with TemporaryDirectory() as tmp:
            mp3_path = Path(tmp) / "lesson.mp3"
            create_silence_mp3(mp3_path, 1000)
            cues = (
                LyricCue(0, 400, "First sentence."),
                LyricCue(500, 900, "Second sentence."),
            )

            lrc_path = write_synchronized_lyrics(mp3_path, cues)
            tags = ID3(mp3_path)

            self.assertTrue(lrc_path.exists())
            self.assertIn("[00:00.50]Second sentence.", lrc_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(len(tags.getall("SYLT")), 1)
            self.assertEqual(len(tags.getall("USLT")), 1)

    def test_batch_outputs_with_same_filename_are_unique(self) -> None:
        with TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            reserved: set[Path] = set()

            first = safe_output_path(output_dir, Path("first/report.txt"), reserved)
            second = safe_output_path(output_dir, Path("second/report.docx"), reserved)

            self.assertEqual(first.name, "report.mp3")
            self.assertEqual(second.name, "report_2.mp3")


if __name__ == "__main__":
    unittest.main()
