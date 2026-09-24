"""Core helpers for the DUO-GAIT window processing pipeline."""

__version__ = "1.0.0"

from . import config
from .duogait_metrics import stride_from_cadence_height_and_feet
from .fuzzy_classifier import FuzzyExerciseClassifier, classify_exercise_state

__all__ = [
	"config",
	"stride_from_cadence_height_and_feet",
	"FuzzyExerciseClassifier",
	"classify_exercise_state",
]
