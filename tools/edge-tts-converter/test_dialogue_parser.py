import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from edge_tts_converter import (
    MODE_AUTO,
    MODE_DIALOGUE,
    NARRATOR_KEY,
    analyze_text,
    safe_output_path,
)


class DialogueParserTests(unittest.TestCase):
    def test_plain_article_remains_reading(self) -> None:
        text = "A winter morning\nThe streets were quiet and the first bus arrived early."
        analysis = analyze_text(text, MODE_AUTO)

        self.assertFalse(analysis.is_dialogue)
        self.assertEqual(analysis.speakers, ())
        self.assertEqual(len(analysis.segments), 1)

    def test_intro_becomes_narration_and_roles_are_detected(self) -> None:
        text = """The train was nearly empty when Anna entered.

Anna: Is this seat free?
David: Yes, please sit down.
Anna: Thank you."""
        analysis = analyze_text(text, MODE_AUTO)

        self.assertTrue(analysis.is_dialogue)
        self.assertEqual(analysis.speakers, ("Anna", "David"))
        self.assertEqual(analysis.segments[0].speaker_key, NARRATOR_KEY)
        self.assertEqual(
            [segment.speaker for segment in analysis.segments],
            ["Narrator", "Anna", "David", "Anna"],
        )

    def test_chinese_full_width_labels(self) -> None:
        analysis = analyze_text("小明：你准备好了吗？\n小红：准备好了。", MODE_AUTO)

        self.assertTrue(analysis.is_dialogue)
        self.assertEqual(analysis.speakers, ("小明", "小红"))

    def test_standalone_labels_and_stage_directions(self) -> None:
        text = """ALICE:
(quietly) We should go now.

BOB:
Not yet."""
        analysis = analyze_text(text, MODE_AUTO)

        self.assertTrue(analysis.is_dialogue)
        self.assertEqual(analysis.segments[0].text, "We should go now.")
        self.assertEqual(analysis.segments[1].text, "Not yet.")

    def test_force_dialogue_allows_one_labelled_speaker(self) -> None:
        text = "An opening note.\nHost: Welcome to the programme."

        self.assertFalse(analyze_text(text, MODE_AUTO).is_dialogue)
        self.assertTrue(analyze_text(text, MODE_DIALOGUE).is_dialogue)

    def test_metadata_labels_do_not_trigger_dialogue(self) -> None:
        text = "Title: Weekly Briefing\nAuthor: Morgan Lee\nA normal article follows."
        analysis = analyze_text(text, MODE_AUTO)

        self.assertFalse(analysis.is_dialogue)
        self.assertEqual(analysis.tagged_turns, 0)

    def test_explicit_narrator_and_one_role_are_dialogue(self) -> None:
        text = "Narrator: The room grows quiet.\nAnna: I think we can begin."
        analysis = analyze_text(text, MODE_AUTO)

        self.assertTrue(analysis.is_dialogue)
        self.assertEqual(analysis.speakers, ("Anna",))
        self.assertTrue(analysis.segments[0].is_narrator)

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
