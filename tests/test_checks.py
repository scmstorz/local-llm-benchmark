import unittest

from local_llm_benchmark.checks import evaluate_output, words


class OutputChecksTest(unittest.TestCase):
    def test_german_structured_output_passes(self) -> None:
        text = """# Kernaussage

Der Artikel erklärt, dass die Emissionen nicht nur durch den direkten
Stromverbrauch entstehen. Die Forschenden zeigen auch, wie sich ein höheres
Wachstum auf den Energieverbrauch auswirken kann.
"""
        result = evaluate_output(text, maximum_words=1000)

        self.assertTrue(result["nonempty"])
        self.assertEqual(result["detected_language"], "de")
        self.assertTrue(result["language_pass"])
        self.assertTrue(result["maximum_words_pass"])
        self.assertTrue(result["source_location_labels_absent"])
        self.assertEqual(result["markdown_heading_count"], 1)
        self.assertEqual(result["bold_heading_count"], 0)
        self.assertTrue(result["heading_pass"])
        self.assertTrue(result["reasoning_markup_absent"])

    def test_english_and_source_label_are_detected(self) -> None:
        text = "# Main point\n\nThe article is about the climate and the effects of AI [P04]."
        result = evaluate_output(text, maximum_words=5)

        self.assertEqual(result["detected_language"], "en")
        self.assertFalse(result["language_pass"])
        self.assertFalse(result["maximum_words_pass"])
        self.assertFalse(result["source_location_labels_absent"])

    def test_bold_heading_and_reasoning_markup(self) -> None:
        text = "**Kernaussage**\n\nDer Text ist kurz.</think>"
        result = evaluate_output(text, maximum_words=1000)

        self.assertEqual(result["markdown_heading_count"], 0)
        self.assertEqual(result["bold_heading_count"], 1)
        self.assertEqual(result["structural_heading_count"], 1)
        self.assertTrue(result["heading_pass"])
        self.assertFalse(result["reasoning_markup_absent"])

    def test_personal_thought_label_is_detected(self) -> None:
        result = evaluate_output("# Post\n\nDas ist mein Gedanke [T02].", 600)

        self.assertFalse(result["source_location_labels_absent"])

    def test_word_count_handles_german_compounds_and_hyphens(self) -> None:
        self.assertEqual(words("AI-getriebenes Wachstum ist CO2-relevant."), [
            "AI-getriebenes",
            "Wachstum",
            "ist",
            "CO2-relevant",
        ])


if __name__ == "__main__":
    unittest.main()
