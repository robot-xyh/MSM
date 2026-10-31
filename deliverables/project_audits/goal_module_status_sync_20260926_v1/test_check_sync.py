"""Tests for the documentation audit, without importing research modules."""

import unittest

from check_sync import BEGIN, END, strip_blocks


class StripBlocksTests(unittest.TestCase):
    def test_unmarked_text_is_unchanged(self):
        original = "# Historical note\n\nOld result: 12.  \n"
        self.assertEqual(strip_blocks(original), original)

    def test_insert_preserves_original_spacing(self):
        original = "# Title\n\nOriginal paragraph.\n"
        added = BEGIN + "\nCurrent evidence.\n" + END + "\n\n"
        current = original.replace("Original", added + "Original", 1)
        self.assertEqual(strip_blocks(current), original)

    def test_multiple_inserts_preserve_text_between_them(self):
        block = BEGIN + "\nStatus.\n" + END + "\n\n"
        self.assertEqual(strip_blocks(block + "Old A\n" + block + "Old B\n"),
                         "Old A\nOld B\n")

    def test_missing_end_marker_is_not_removed(self):
        content = BEGIN + "\nUnfinished insertion.\n"
        self.assertEqual(strip_blocks(content), content)

    def test_missing_separator_is_not_removed(self):
        content = BEGIN + "\nStatus.\n" + END + "\nOld text.\n"
        self.assertEqual(strip_blocks(content), content)


if __name__ == "__main__":
    unittest.main()
