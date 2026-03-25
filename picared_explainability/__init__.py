"""
picared_explainability
=======================
Model Explainability and Interpretability toolkit for the PICARED
(Prospect Identification, Classification, Analysis, Risk Evaluation,
and Decision) framework.

Modules
-------
explainers.shap_explainer       : SHAP-based feature attribution
explainers.lime_explainer       : LIME local surrogate explanations
explainers.counterfactual_explainer : Counterfactual & necessity/sufficiency
validation.consistency_metrics  : SHAP-LIME consistency quantification

Quick Start
-----------
>>> from picared_explainability.explainers.shap_explainer import SHAPExplainer
>>> from picared_explainability.explainers.lime_explainer import LIMEExplainer
>>> from picared_explainability.explainers.counterfactual_explainer import CounterfactualExplainer
>>> from picared_explainability.validation.consistency_metrics import consistency_report
"""

__version__ = "0.1.0"
__author__ = "PICARED Research Team"
__license__ = "MIT"

from picared_explainability.explainers.shap_explainer import SHAPExplainer, explain_with_shap
from picared_explainability.explainers.lime_explainer import LIMEExplainer
from picared_explainability.explainers.counterfactual_explainer import CounterfactualExplainer
from picared_explainability.validation.consistency_metrics import (
    rank_consistency,
    spearman_consistency,
    top_k_overlap,
    consistency_report,
    compare_models,
    plot_importance_comparison,
    plot_rank_scatter,
)

__all__ = [
    # Explainers
    "SHAPExplainer",
    "explain_with_shap",
    "LIMEExplainer",
    "CounterfactualExplainer",
    # Validation
    "rank_consistency",
    "spearman_consistency",
    "top_k_overlap",
    "consistency_report",
    "compare_models",
    "plot_importance_comparison",
    "plot_rank_scatter",
]
