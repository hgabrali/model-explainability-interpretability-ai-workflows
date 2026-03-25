"""
LIME Explainer Module for PICARED Framework
============================================
Implements LIME (Local Interpretable Model-Agnostic Explanations) for
individual prediction explanations in the PICARED workflow.

References:
    Ribeiro, M. T., Singh, S., & Guestrin, C. (2016). "Why Should I Trust You?":
    Explaining the Predictions of Any Classifier. KDD.
"""

import numpy as np
import pandas as pd
import lime
import lime.lime_tabular
import matplotlib.pyplot as plt
from typing import Optional, Union, List, Dict, Any, Callable, Tuple


class LIMEExplainer:
    """
    LIME-based explainer for tabular classification and regression models.

    Wraps `lime.lime_tabular.LimeTabularExplainer` and adds utilities for
    batch explanation, rank extraction, and consistency analysis with SHAP.

    Parameters
    ----------
    feature_names : list of str
        Names of input features.
    class_names : list of str, optional
        Names of output classes for classification tasks.
    mode : str
        'classification' or 'regression'. Defaults to 'classification'.
    categorical_features : list of int, optional
        Indices of categorical features.
    kernel_width : float, optional
        Width of the exponential kernel (controls locality).
    num_samples : int
        Number of perturbed samples generated per explanation. Default 5000.
    random_state : int, optional
        Random seed for reproducibility.
    """

    def __init__(
        self,
        feature_names: List[str],
        class_names: Optional[List[str]] = None,
        mode: str = 'classification',
        categorical_features: Optional[List[int]] = None,
        kernel_width: Optional[float] = None,
        num_samples: int = 5000,
        random_state: int = 42,
    ) -> None:
        self.feature_names = feature_names
        self.class_names = class_names or ['Class 0', 'Class 1']
        self.mode = mode
        self.categorical_features = categorical_features or []
        self.kernel_width = kernel_width
        self.num_samples = num_samples
        self.random_state = random_state
        self._explainer: Optional[lime.lime_tabular.LimeTabularExplainer] = None

    # ------------------------------------------------------------------
    # Explainer initialisation
    # ------------------------------------------------------------------

    def fit(self, X_train: Union[np.ndarray, pd.DataFrame]) -> "LIMEExplainer":
        """
        Build the LIME background distribution from training data.

        Parameters
        ----------
        X_train : array-like of shape (n_samples, n_features)
            Training dataset.

        Returns
        -------
        self
        """
        data = X_train.values if hasattr(X_train, 'values') else np.asarray(X_train)
        kwargs: Dict[str, Any] = dict(
            training_data=data,
            feature_names=self.feature_names,
            class_names=self.class_names,
            mode=self.mode,
            categorical_features=self.categorical_features,
            random_state=self.random_state,
        )
        if self.kernel_width is not None:
            kwargs['kernel_width'] = self.kernel_width

        self._explainer = lime.lime_tabular.LimeTabularExplainer(**kwargs)
        return self

    # ------------------------------------------------------------------
    # Single-instance explanation
    # ------------------------------------------------------------------

    def explain_instance(
        self,
        instance: Union[np.ndarray, pd.Series],
        predict_fn: Callable,
        num_features: int = 10,
        top_labels: int = 1,
    ) -> lime.lime_tabular.explanation.Explanation:
        """
        Explain a single prediction.

        Parameters
        ----------
        instance : 1-D array-like
            Feature vector to explain.
        predict_fn : callable
            Model prediction function (predict_proba for classification,
            predict for regression).
        num_features : int
            Number of features to include in the explanation.
        top_labels : int
            Number of top labels to explain.

        Returns
        -------
        lime Explanation object
        """
        self._check_fitted()
        data = instance.values if hasattr(instance, 'values') else np.asarray(instance)
        return self._explainer.explain_instance(
            data,
            predict_fn,
            num_features=num_features,
            top_labels=top_labels,
            num_samples=self.num_samples,
        )

    # ------------------------------------------------------------------
    # Batch explanation & importance extraction
    # ------------------------------------------------------------------

    def explain_batch(
        self,
        X: Union[np.ndarray, pd.DataFrame],
        predict_fn: Callable,
        num_features: int = 10,
    ) -> List[Dict[str, float]]:
        """
        Explain a set of instances and return feature weights per instance.

        Parameters
        ----------
        X : array-like of shape (n_samples, n_features)
        predict_fn : callable
        num_features : int

        Returns
        -------
        list of dicts mapping feature_name -> LIME weight
        """
        self._check_fitted()
        results = []
        X_arr = X.values if hasattr(X, 'values') else np.asarray(X)
        for i in range(len(X_arr)):
            exp = self.explain_instance(X_arr[i], predict_fn, num_features=num_features)
            weights = dict(exp.as_list())
            results.append(weights)
        return results

    def feature_importance(
        self,
        X: Union[np.ndarray, pd.DataFrame],
        predict_fn: Callable,
        num_features: int = 10,
        aggregation: str = "mean_abs",
    ) -> pd.Series:
        """
        Aggregate LIME weights across instances to global importance.

        Parameters
        ----------
        aggregation : str
            'mean_abs' (default) or 'sum_abs'.

        Returns
        -------
        pd.Series sorted descending
        """
        batch = self.explain_batch(X, predict_fn, num_features=num_features)
        df = pd.DataFrame(batch).fillna(0.0)
        if aggregation == "mean_abs":
            scores = df.abs().mean()
        else:
            scores = df.abs().sum()
        return scores.sort_values(ascending=False)

    def rank_features(
        self,
        X: Union[np.ndarray, pd.DataFrame],
        predict_fn: Callable,
        num_features: int = 10,
    ) -> pd.DataFrame:
        """
        Return a DataFrame with features sorted by LIME importance.

        Returns
        -------
        pd.DataFrame with columns ['feature', 'lime_importance', 'rank']
        """
        importance = self.feature_importance(X, predict_fn, num_features=num_features)
        df = importance.reset_index()
        df.columns = ['feature', 'lime_importance']
        df['rank'] = range(1, len(df) + 1)
        return df

    # ------------------------------------------------------------------
    # Visualisation helpers
    # ------------------------------------------------------------------

    def plot_explanation(
        self,
        instance: Union[np.ndarray, pd.Series],
        predict_fn: Callable,
        num_features: int = 10,
        title: str = "LIME Explanation",
        show: bool = True,
    ) -> None:
        """Bar plot for a single-instance LIME explanation."""
        exp = self.explain_instance(instance, predict_fn, num_features=num_features)
        fig = exp.as_pyplot_figure()
        fig.suptitle(title)
        if show:
            plt.tight_layout()
            plt.show()

    # ------------------------------------------------------------------
    # Consistency utilities
    # ------------------------------------------------------------------

    def consistency_with_shap(
        self,
        lime_ranks: pd.DataFrame,
        shap_ranks: pd.DataFrame,
        top_k: int = 10,
    ) -> float:
        """
        Compute rank-based consistency between LIME and SHAP explanations.

        Consistency = 1 - (1/K) * Σ |rank_SHAP(k) - rank_LIME(k)|

        Parameters
        ----------
        lime_ranks : pd.DataFrame
            Output of rank_features(), must have 'feature' and 'rank'.
        shap_ranks : pd.DataFrame
            Output of SHAPExplainer.rank_features().
        top_k : int
            Number of top features to consider.

        Returns
        -------
        float in [0, 1] — higher is more consistent
        """
        lime_top = lime_ranks.head(top_k).set_index('feature')['rank']
        shap_top = shap_ranks.head(top_k).set_index('feature')['rank']
        all_features = lime_top.index.union(shap_top.index)
        fallback_rank = top_k + 1
        rank_diff = sum(
            abs(lime_top.get(f, fallback_rank) - shap_top.get(f, fallback_rank))
            for f in all_features
        )
        return max(0.0, 1.0 - rank_diff / (top_k * top_k))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_fitted(self) -> None:
        if self._explainer is None:
            raise RuntimeError("Call fit() before explain_instance().")
