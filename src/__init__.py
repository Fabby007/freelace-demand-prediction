"""Mechanic Service Demand Opportunity Prediction and Recommendation System.

Importing torch before xgboost/scikit-learn/pandas/numpy is required on
this project's Windows development environment - see
specs/reference/REF-009-architecture-decisions.md ADR-003. Every entrypoint
(scripts, tests, the dashboard app) must import `src` (or any `src.*`
submodule, e.g. `from src.data.clean_dataset import run`) as its FIRST
import, before pandas/numpy/xgboost/sklearn/tensorflow, so this ordering is
applied automatically. Bypassing the `src` package (e.g. manipulating
sys.path to import a submodule directly) skips this safeguard.
"""
try:
    import torch  # noqa: F401  (import-order fix, see ADR-003; sentence-transformers pulls this in anyway)
except ImportError:
    pass
