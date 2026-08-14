import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.guardian_links import normalize_guardian_student_links


class GuardianLinksTests(unittest.TestCase):
    def test_deduplicates_preserving_order(self):
        linked, primary = normalize_guardian_student_links(["a", "b", "a", ""], ["b", "b"])
        self.assertEqual(linked, ["a", "b"])
        self.assertEqual(primary, ["b"])

    def test_primary_must_be_linked(self):
        with self.assertRaises(ValueError):
            normalize_guardian_student_links(["a"], ["b"])

    def test_empty_legacy_values_are_compatible(self):
        linked, primary = normalize_guardian_student_links(None, None)
        self.assertEqual(linked, [])
        self.assertEqual(primary, [])


if __name__ == "__main__":
    unittest.main()
