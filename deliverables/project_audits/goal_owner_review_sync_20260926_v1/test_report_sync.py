import unittest

from lxml import etree

from report_sync import W, insert_paragraph, replace_run_text, text


class TextEditTests(unittest.TestCase):
    def paragraph(self, parts):
        p = etree.Element(W + "p")
        for value in parts:
            run = etree.SubElement(p, W + "r")
            etree.SubElement(run, W + "rPr")
            etree.SubElement(run, W + "t").text = value
        return p

    def test_replacement_spans_runs_without_dropping_styles(self):
        p = self.paragraph(["prefix o", "ld tex", "t suffix"])
        replace_run_text(p, "old text", "new text")
        self.assertEqual(text(p), "prefix new text suffix")
        self.assertEqual(len(p.findall(".//" + W + "rPr")), 3)

    def test_ambiguous_replacement_rejected(self):
        p = self.paragraph(["old old"])
        with self.assertRaises(ValueError):
            replace_run_text(p, "old", "new")

    def test_insert_only_text_properties(self):
        root = etree.Element(W + "body")
        p = self.paragraph(["original"])
        p.insert(0, etree.Element(W + "pPr"))
        root.append(p)
        insert_paragraph(p, "note")
        self.assertEqual([text(e) for e in root], ["original", "note"])
        self.assertIsNotNone(root[1].find(W + "pPr"))
        self.assertEqual(text(root[0]), "original")


if __name__ == "__main__":
    unittest.main()
