import sys
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils.student_demographics import audit_race_community_record


class StudentDemographicsTests(unittest.TestCase):
    def test_canonical_race_and_community_are_valid(self):
        result = audit_race_community_record({
            "color_race": "parda",
            "comunidade_tradicional": "quilombola",
        })
        self.assertFalse(result["needs_review"])
        self.assertEqual(result["issues"], [])

    def test_traditional_value_in_color_race_requires_review(self):
        result = audit_race_community_record({
            "color_race": "quilombola",
            "comunidade_tradicional": "nao_pertence",
        })
        self.assertTrue(result["needs_review"])
        self.assertIn("traditional_value_in_color_race", result["issues"])
        self.assertIn("traditional_community_needs_confirmation", result["issues"])

    def test_conflicting_traditional_dimensions_are_detected(self):
        result = audit_race_community_record({
            "color_race": "quilombola",
            "comunidade_tradicional": "ribeirinho",
        })
        self.assertIn("traditional_dimensions_conflict", result["issues"])

    def test_unknown_values_are_not_silently_normalized(self):
        result = audit_race_community_record({
            "color_race": "valor_desconhecido",
            "comunidade_tradicional": "outro_valor",
        })
        self.assertIn("unsupported_color_race", result["issues"])
        self.assertIn("unsupported_traditional_community", result["issues"])


if __name__ == "__main__":
    unittest.main()
