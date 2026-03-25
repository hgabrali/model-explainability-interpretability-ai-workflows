"""
SHAP Explainer Module for PICARED Framework
============================================
Implements SHAP (Shapley Additive Explanations) for model interpretability
in the PICARED (Prospect Identification, Classification, Analysis,
Risk Evaluation, and Decision) workflow.

References:
    Lundberg, S. M., & Lee, S. I. (2017). A Unified Approach to Interpreting
    Model Predictions. NeurIPS.
"""

import numpy as np
import pandas as pd
import shap
import matplotlib.pyplot as plt
from typing import Optional, Union, List, Dict, Any
import warnings


class SHAPExplainer:
    """
    SHAP-based explainer for tabular classification and regression models.

    Supports TreeExplainer (for tree-based models), LinearExplainer (for
    linear models), and KernelExplainer (model-agnostic fallback).

    Parameters
    ----------
    model : Any
        Trained machine learning model.
    feature_names : list of str
        Names of input features.
    explainer_type : str, optional
        One of 'tree', 'linear', or 'kernel'. Defaults to 'tree'.
    background_data : array-like, optional
        Background dataset for KernelExplainer.
    """

    SUPPORTED_TYPES = ('tree', 'linear', 'kernel')

    def __init__(
        self,
        model: Any,
        feature_names: List[str],
        explainer_type: str = 'tree',
        background_data: Optional[np.ndarray] = None,
    ) -> None:
        if explainer_type not in self.SUPPORTED_TYPES:
            raise ValueError(
                f"explainer_type must be one of {self.SUPPORTED_TYPES}, "
                f"got '{explainer_type}'."
            )
        self.model = model
        self.feature_names = feature_names
        self.explainer_type = explainer_type
        self.background_data = background_data
        self._explainer: Optional[shap.Explainer] = None
        self.shap_values_: Optional[np.ndarray] = None
        self.expected_value_: Optional[float] = None

    # ------------------------------------------------------------------
    # Explainer initialisation
    # ------------------------------------------------------------------

    def fit(self, X: Union[np.ndarray, pd.DataFrame]) -> "SHAPExplainer":
        """
        Initialise the SHAP explainer.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            Dataset used to build the background distribution for
            KernelExplainer.

        Returns
        -------
        self
        """
        if self.explainer_type == 'tree':
            self._explainer = shap.TreeExplainer(self.model)
        elif self.explainer_type == 'linear':
            self._explainer = shap.LinearExplainer(
                self.model, X if self.background_data is None else self.background_data
            )
        else:  # kernel
            bg = self.background_data if self.background_data is not None else X
            self._explainer = shap.KernelExplainer(self.model.predict_proba, bg)
        return self

    # ------------------------------------------------------------------
    # SHAP value computation
    # ------------------------------------------------------------------

    def compute_shap_values(
        self,
        X: Union[np.ndarray, pd.DataFrame],
        check_additivity: bool = False,
    ) -> np.ndarray:
        """
        Compute SHAP values for a dataset.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
            Input data.
        check_additivity : bool, optional
            Whether to verify the efficiency property. Defaults to False.

        Returns
        -------
        shap_values : ndarray
            SHAP values of shape (n_samples, n_features) for regression /
            binary classification, or (n_classes, n_samples, n_features)
            for multi-class problems.
        """
        if self._explainer is None:
            raise RuntimeError("Call fit() before compute_shap_values().")

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.shap_values_ = self._explainer.shap_values(
                X, check_additivity=check_additivity
            )

        self.expected_value_ = (
            self._explainer.expected_value[1]
            if isinstance(self._explainer.expected_value, (list, np.ndarray))
            else self._explainer.expected_value
        )
        return self.shap_values_

    # ------------------------------------------------------------------
    # Visualisation helpers
    # ------------------------------------------------------------------

    def plot_summary(
        self,
        X: Union[np.ndarray, pd.DataFrame],
        plot_type: str = "dot",
        max_display: int = 20,
        show: bool = True,
    ) -> None:
        """Render a global SHAP summary (beeswarm / bar) plot."""
        self._check_computed()
        shap.summary_plot(
            self.shap_values_,
            X,
            feature_names=self.feature_names,
            plot_type=plot_type,
            max_display=max_display,
            show=show,
        )

    def plot_waterfall(
        self,
        X: Union[np.ndarray, pd.DataFrame],
        instance_idx: int = 0,
        show: bool = True,
    ) -> None:
        """Render a waterfall plot for a single prediction."""
        self._check_computed()
        sv = self.shap_values_
        if sv.ndim == 3:          # multi-class: pick positive class
            sv = sv[1]
        shap.waterfall_plot(
            shap.Explanation(
                values=sv[instance_idx],
                base_values=self.expected_value_,
                data=X.iloc[instance_idx] if hasattr(X, 'iloc') else X[instance_idx],
                feature_names=self.feature_names,
            ),
            show=show,
        )

    def plot_dependence(
        self,
        feature: str,
        X: Union[np.ndarray, pd.DataFrame],
        interaction_feature: str = "auto",
        show: bool = True,
    ) -> None:
        """Render a dependence plot for a single feature."""
        self._check_computed()
        shap.dependence_plot(
            feature,
            self.shap_values_,
            X,
            feature_names=self.feature_names,
            interaction_index=interaction_feature,
            show=show,
        )

    # ------------------------------------------------------------------
    # Consistency & ranking utilities
    # ------------------------------------------------------------------

    def feature_importance(self, aggregation: str = "mean_abs") -> pd.Series:
        """
        Compute global feature importance from SHAP values.

        Parameters
        ----------
        aggregation : str
            'mean_abs'  — mean absolute SHAP value (default)
            'sum_abs'   — sum of absolute SHAP values

        Returns
        -------
        importance : pd.Series sorted descending
        """
        self._check_computed()
        sv = self.shap_values_
        if sv.ndim == 3:
            sv = sv[1]
        if aggregation == "mean_abs":
            scores = np.abs(sv).mean(axis=0)
        elif aggregation == "sum_abs":
            scores = np.abs(sv).sum(axis=0)
        else:
            raise ValueError(f"Unknown aggregation: '{aggregation}'.")
        return pd.Series(scores, index=self.feature_names).sort_values(ascending=False)

    def rank_features(self) -> pd.DataFrame:
        """
        Return a DataFrame with features sorted by SHAP importance.

        Returns
        -------
        pd.DataFrame with columns ['feature', 'shap_importance', 'rank']
        """
        importance = self.feature_importance()
        df = importance.reset_index()
        df.columns = ['feature', 'shap_importance']
        df['rank'] = range(1, len(df) + 1)
        return df

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_computed(self) -> None:
        if self.shap_values_ is None:
            raise RuntimeError("Call compute_shap_values() first.")


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def explain_with_shap(
    model: Any,
    X_train: Union[np.ndarray, pd.DataFrame],
    X_explain: Union[np.ndarray, pd.DataFrame],
    feature_names: List[str],
    explainer_type: str = 'tree',
    plot: bool = True,
) -> Dict[str, Any]:
    """
    One-shot helper: fit a SHAP explainer and return values + importance.

    Parameters
    ----------
    model : Any
        Trained model.
    X_train : array-like
        Training data (used as background for KernelExplainer).
    X_explain : array-like
        Data to explain.
    feature_names : list of str
        Feature names.
    explainer_type : str
        'tree', 'linear', or 'kernel'.
    plot : bool
        If True, display the summary plot.

    Returns
    -------
    dict with keys 'explainer', 'shap_values', 'importance'
    """
    explainer = SHAPExplainer(model, feature_names, explainer_type=explainer_type)
    explainer.fit(X_train)
    shap_values = explainer.compute_shap_values(X_explain)
    if plot:
        explainer.plot_summary(X_explain, show=True)
    return {
        "explainer": explainer,
        "shap_values": shap_values,
        "importance": explainer.feature_importance(),
    }
