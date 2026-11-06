"""DEV-001 smoke tests: environment/foundation is usable.

Imports every top-level src/ package and the full pinned stack together,
in the order required by ADR-003 (torch must load before xgboost/sklearn).
"""
import importlib

import src  # noqa: F401  (ADR-003: must be imported first to load torch before xgboost/sklearn)


def test_pinned_stack_imports_together():
    for module_name in [
        "pandas", "numpy", "xgboost", "sklearn", "tensorflow",
        "sentence_transformers", "shap", "streamlit", "plotly",
        "mlflow", "pdfplumber", "requests",
    ]:
        importlib.import_module(module_name)


def test_src_subpackages_import():
    for subpackage in [
        "src.data", "src.features", "src.models",
        "src.explainability", "src.nlp", "src.recommendation",
        "src.evaluation",  # added DEV-014 (REF-009 ADR-023) - beyond Appendix B's original list
    ]:
        importlib.import_module(subpackage)
