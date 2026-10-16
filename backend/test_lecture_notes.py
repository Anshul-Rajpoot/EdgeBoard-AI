"""Small offline tests for lecture context formatting and fallback notes."""
import unittest

from ai.lecture_notes import _split_into_chunks, generate_lecture_notes


class LectureNotesTests(unittest.TestCase):
    def test_fallback_keeps_source_text_and_equations(self):
        result = generate_lecture_notes(
            "Digital Electronics", "Adders", [
                {"frame_id": 1, "filename": "first.jpg", "text": "Half Adder"},
                {"frame_id": 2, "filename": "second.jpg", "text": "Sum = A XOR B"},
            ]
        )
        self.assertEqual(result["mode"], "offline_fallback")
        self.assertEqual(result["source_count"], 2)
        self.assertIn("Half Adder", result["notes"])
        self.assertIn("Sum = A XOR B", result["notes"])

    def test_long_context_is_split_without_dropping_content(self):
        text = "\n".join(f"line {i}" for i in range(4000))
        chunks = _split_into_chunks(text, max_chars=1000)
        self.assertGreater(len(chunks), 1)
        self.assertIn("line 0", chunks[0])
        self.assertIn("line 3999", chunks[-1])
        self.assertEqual(sum(chunk.count("line ") for chunk in chunks), 4000)

    def test_empty_capture_is_ignored_and_all_empty_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_lecture_notes("Empty", "", [{"frame_id": 1, "text": "  "}])


if __name__ == "__main__":
    unittest.main()
