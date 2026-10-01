import unittest
from unittest.mock import patch

import numpy as np

import process_duogait_to_json
from process_duogait_to_json import DUOGAITProcessor
from signal_processing_pipeline.fuzzy_classifier import (
    FuzzyExerciseClassifier,
    assess_exercise_state,
    classify_exercise_state,
)


def assessment(**overrides):
    data = {
        "mean_hr_bpm": 90.0,
        "max_hr_bpm": 95.0,
        "step_frequency_hz": 1.7,
        "step_length_m": 0.55,
        "step_time_variability_ms": 25.0,
        "warmup_baseline": {
            "warmup_cadence_hz": 1.7,
            "warmup_stride_m": 0.55,
            "warmup_var_ms": 25.0,
        },
        "player_age": 70,
        "rpe": None,
        "imu_quality": 0.9,
        "hr_quality": 0.9,
    }
    data.update(overrides)
    return assess_exercise_state(**data)


class AssessmentPromptTests(unittest.TestCase):
    def test_returns_two_layer_prompt_schema(self):
        out = assessment()

        self.assertEqual(
            set(out.keys()),
            {"research_layer", "system_layer"},
        )
        self.assertEqual(out["research_layer"]["exercise_load_state"], "moderate")
        self.assertEqual(out["system_layer"]["clinical_flag"], "normal")
        self.assertIn("modality_contribution", out["research_layer"])
        self.assertIn("reasoning", out["research_layer"])

    def test_hr_percentage_boundaries_use_mean_hr(self):
        self.assertEqual(
            assessment(mean_hr_bpm=74.9)["research_layer"]["exercise_load_state"],
            "low",
        )
        self.assertEqual(
            assessment(mean_hr_bpm=75.0)["research_layer"]["exercise_load_state"],
            "moderate",
        )
        self.assertEqual(
            assessment(mean_hr_bpm=105.0)["research_layer"]["exercise_load_state"],
            "high",
        )
        self.assertEqual(
            assessment(mean_hr_bpm=120.0)["research_layer"]["exercise_load_state"],
            "excessive",
        )

    def test_missing_hr_is_unknown_and_does_not_trigger_hr_safety(self):
        out = assessment(mean_hr_bpm=None, max_hr_bpm=180.0, rpe=7)
        research = out["research_layer"]

        self.assertEqual(research["exercise_load_state"], "unknown")
        self.assertLessEqual(research["modality_contribution"]["hr_weight"], 0.2)
        self.assertNotIn("high_cardiac_load", research["compensation_flags"])
        self.assertEqual(out["system_layer"]["clinical_flag"], "normal")

    def test_both_low_quality_is_data_invalid_not_normal(self):
        out = assessment(imu_quality=0.5, hr_quality=0.5)

        research = out["research_layer"]
        self.assertEqual(research["exercise_load_state"], "unknown")
        self.assertEqual(research["fatigue_level"], "unknown")
        self.assertEqual(research["movement_quality"], "unknown")
        self.assertEqual(research["composite_state"], "unknown")
        self.assertEqual(out["system_layer"]["clinical_flag"], "data_invalid")
        self.assertEqual(out["system_layer"]["dda_delta"], 0)

        legacy = classify_exercise_state(
            mean_hr_bpm=90.0,
            max_hr_bpm=95.0,
            step_frequency_hz=1.7,
            step_length_m=0.55,
            step_time_variability_ms=25.0,
            warmup_baseline={},
            player_age=70,
            rpe=None,
            imu_quality=0.5,
            hr_quality=0.5,
        )
        self.assertEqual(legacy["composite_state"], "unknown")

    def test_rpe_7_and_9_boundaries(self):
        mild = assessment(mean_hr_bpm=90.0, rpe=7)
        hard_stop = assessment(mean_hr_bpm=90.0, rpe=9)

        self.assertEqual(mild["research_layer"]["fatigue_level"], "mild")
        self.assertEqual(
            hard_stop["research_layer"]["exercise_load_state"],
            "excessive",
        )
        self.assertIn("high_rpe", hard_stop["research_layer"]["compensation_flags"])
        self.assertEqual(hard_stop["system_layer"]["clinical_flag"], "hard_stop")

    def test_warmup_stride_drop_boundary_flags_compensation(self):
        out = assessment(
            step_length_m=0.39,
            step_time_variability_ms=61.0,
            warmup_baseline={
                "warmup_cadence_hz": 1.7,
                "warmup_stride_m": 0.50,
                "warmup_var_ms": 25.0,
            },
        )

        self.assertEqual(out["research_layer"]["fatigue_level"], "moderate")
        self.assertIn("stride_drop_fatigue", out["research_layer"]["compensation_flags"])
        self.assertEqual(out["system_layer"]["clinical_flag"], "fatigue_compensation")

    def test_create_window_json_writes_assessment_and_preserves_nulls(self):
        proc = DUOGAITProcessor("", "", "", subject_id="sub_01")
        out = proc.create_window_json(
            1,
            {
                "step_frequency_hz": np.nan,
                "step_length_m": None,
                "step_time_variability_ms": 25.0,
            },
            {"hr_mean_bpm": None, "hr_max_bpm": None},
            {},
            0.9,
            0.9,
            70,
        )

        self.assertIsNone(out["input_features"]["step_frequency_hz"])
        self.assertIsNone(out["input_features"]["step_length_m"])
        self.assertEqual(
            out["ground_truth"]["research_layer"]["exercise_load_state"],
            "unknown",
        )
        self.assertNotEqual(out["input_features"]["step_frequency_hz"], 0)

    def test_create_window_json_exception_fallback_is_invalid(self):
        proc = DUOGAITProcessor("", "", "", subject_id="sub_01")
        with patch.object(
            process_duogait_to_json,
            "assess_exercise_state",
            side_effect=RuntimeError("boom"),
        ):
            out = proc.create_window_json(
                1,
                {
                    "step_frequency_hz": 1.7,
                    "step_length_m": 0.55,
                    "step_time_variability_ms": 25.0,
                },
                {"hr_mean_bpm": 90.0, "hr_max_bpm": 95.0},
                {},
                0.9,
                0.9,
                70,
            )

        self.assertEqual(
            out["ground_truth"]["system_layer"]["clinical_flag"],
            "data_invalid",
        )
        self.assertEqual(
            out["ground_truth"]["research_layer"]["composite_state"],
            "unknown",
        )

    def test_legacy_classifier_wrapper_stays_compatible(self):
        out = FuzzyExerciseClassifier(age=70).classify(
            hr_mean=90.0,
            step_var=25.0,
            hr_recovery=None,
            stride_length=0.55,
            cadence_hz=1.7,
        )

        self.assertEqual(out["exercise_load"][1], "moderate")
        self.assertEqual(out["composite_state"], "normal")


if __name__ == "__main__":
    unittest.main()
