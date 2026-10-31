import unittest

from integrate_reviews import owners


class OwnerSelectionTests(unittest.TestCase):
    def test_range_with_main(self):
        self.assertEqual(owners("D1至D6及main"), {"main", "D1", "D2", "D3", "D4", "D5", "D6"})

    def test_disjoint_owners(self):
        self.assertEqual(owners("D2;D5;D7"), {"D2", "D5", "D7"})

    def test_main_only(self):
        self.assertEqual(owners("main"), {"main"})


if __name__ == "__main__":
    unittest.main()
