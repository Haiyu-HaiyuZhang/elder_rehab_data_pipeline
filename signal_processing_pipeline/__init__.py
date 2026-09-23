"""Core helpers for the DUO-GAIT window pipeline.

The production entry point is ``process_duogait_to_json.py``.  This package
contains only the configuration, gait fusion helper, and fuzzy baseline used
by that entry point.
"""

__version__ = "1.0.0"
__author__ = "Data Science Team"

from .config import *
