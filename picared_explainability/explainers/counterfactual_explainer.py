"""
Counterfactual Explainer Module for PICARED Framework
======================================================
Generates diverse counterfactual explanations to answer "what-if" questions
about model predictions, implementing necessity and sufficiency metrics.

References:
    Mothilal, R. K., Sharma, A., & Tan, C. (2020). Explaining Machine Learning
    Classifiers through Diverse Counterfactual Explanations. FAccT.

    Chowdhury, P., Mustafa, A., Prabhushankar, M., & AlRegib, G. (2025).
    A unified framework for evaluating the robustness of machine-learning
    interpretability for prospect risking. Geophysics, 90(3).
"""

import numpy as np
import pandas as pd
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


class CounterfactualExplainer:
    """
    Generates counterfactual explanations and evaluates necessity / sufficiency.

    For each query instance the explainer finds *diverse* perturbations that
    change the model's predicted class (or push a regression output over a
    threshold), while minimising the distance from the original instance.

    Parameters
    ----------
    model : Any
        Trained model with a predict method (and optionally predict_proba).
    feature_names : list of str
        Feature names.
    feature_ranges : dict, optional
        Mapping feature_name -> (min, max) used to constrain perturbations.
        Features absent from the dict are treated as continuous with no bounds.
    categorical_features : list of str, optional
        Names of categorical (discrete) features.
    n_counterfactuals : int
        Number of diverse counterfactuals to generate per instance. Default 5.
    max_iter : int
        Maximum optimisation iterations. Default 1000.
    step_size : float
        Perturbation step size for gradient-free search. Default 0.05.
    random_state : int
        Random seed.
    """

    def __init__(
        self,
        model: Any,
        feature_names: List[str],
        feature_ranges: Optional[Dict[str, Tuple[float, float]]] = None,
        categorical_features: Optional[List[str]] = None,
        n_counterfactuals: int = 5,
        max_iter: int = 1000,
        step_size: float = 0.05,
        random_state: int = 42,
    ) -> None:
        self.model = model
        self.feature_names = feature_names
        self.feature_ranges = feature_ranges or {}
        self.categorical_features = categorical_features or []
        self.n_counterfactuals = n_counterfactuals
        self.max_iter = max_iter
        self.step_size = step_size
        self.rng = np.random.default_rng(random_state)

    # ------------------------------------------------------------------
    # Counterfactual generation
    # ------------------------------------------------------------------

    def generate(
        self,
        instance: Union[np.ndarray, pd.Series],
        X_reference: Union[np.ndarray, pd.DataFrame],
        desired_class: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Generate diverse counterfactual examples for one instance.

        Uses a random perturbation search biased towards reference-data
        statistics, keeping only candidates that flip the prediction and
        maximising diversity via greedy farthest-point selection.

        Parameters
        ----------
        instance : 1-D array-like
            Query instance.
        X_reference : array-like of shape (n_samples, n_features)
            Reference dataset used to sample realistic perturbations.
        desired_class : int, optional
            Target class for classification. If None the opposite of the
            current class is used.

        Returns
        -------
        pd.DataFrame of shape (n_counterfactuals, n_features)
            Each row is a valid counterfactual.
        """
        x = self._to_array(instance)
        X_ref = self._to_array(X_reference)
        original_pred = self._predict_class(x)

        if desired_class is None:
            desired_class = 1 - int(original_pred)

        candidates = []
        for _ in range(self.max_iter):
            cf = self._perturb(x, X_ref)
            if self._predict_class(cf) == desired_class:
                candidates.append(cf)
            if len(candidates) >= self.n_counterfactuals * 10:
                break

        if not candidates:
            return pd.DataFrame(columns=self.feature_names)

        diverse = self._select_diverse(np.array(candidates), self.n_counterfactuals)
        return pd.DataFrame(diverse, columns=self.feature_names)

    # ------------------------------------------------------------------
    # Necessity and Sufficiency
    # ------------------------------------------------------------------

    def necessity_score(
        self,
        instance: Union[np.ndarray, pd.Series],
        feature: str,
        X_reference: Union[np.ndarray, pd.DataFrame],
        n_trials: int = 200,
    ) -> float:
        """
        Estimate necessity: P(prediction changes | feature is altered).

        N(i) = P(f(x) ≠ f(x_{-i}) | f(x) = target)

        Parameters
        ----------
        instance : 1-D array-like
            Query instance.
        feature : str
            Name of the feature to mask.
        X_reference : array-like
            Reference distribution.
        n_trials : int
            Monte-Carlo sample size.

        Returns
        -------
        float in [0, 1]
        """
        x = self._to_array(instance)
        X_ref = self._to_array(X_reference)
        feat_idx = self.feature_names.index(feature)
        original_pred = self._predict_class(x)
        changed = 0
        for _ in range(n_trials):
            x_masked = x.copy()
            x_masked[feat_idx] = self.rng.choice(X_ref[:, feat_idx])
            if self._predict_class(x_masked) != original_pred:
                changed += 1
        return changed / n_trials

    def sufficiency_score(
        self,
        instance: Union[np.ndarray, pd.Series],
        feature: str,
        X_reference: Union[np.ndarray, pd.DataFrame],
        n_trials: int = 200,
    ) -> float:
        """
        Estimate sufficiency: P(prediction unchanged | only feature is kept).

        S(i) = P(f(x) = f(xᵢ) | f(x) = target)

        Parameters
        ----------
        instance : 1-D array-like
        feature : str
        X_reference : array-like
        n_trials : int

        Returns
        -------
        float in [0, 1]
        """
        x = self._to_array(instance)
        X_ref = self._to_array(X_reference)
        feat_idx = self.feature_names.index(feature)
        original_pred = self._predict_class(x)
        unchanged = 0
        for _ in range(n_trials):
            x_isolated = self.rng.choice(X_ref, axis=0).copy()
            x_isolated[feat_idx] = x[feat_idx]
            if self._predict_class(x_isolated) == original_pred:
                unchanged += 1
        return unchanged / n_trials

    def necessity_sufficiency_report(
        self,
        instance: Union[np.ndarray, pd.Series],
        X_reference: Union[np.ndarray, pd.DataFrame],
        top_features: Optional[List[str]] = None,
        n_trials: int = 200,
    ) -> pd.DataFrame:
        """
        Compute necessity and sufficiency for each (or selected) feature.

        Returns
        -------
        pd.DataFrame with columns ['feature', 'necessity', 'sufficiency',
                                    'robustness_score']
        where robustness_score = (necessity + sufficiency) / 2.
        """
        features = top_features or self.feature_names
        records = []
        for feat in features:
            n = self.necessity_score(instance, feat, X_reference, n_trials)
            s = self.sufficiency_score(instance, feat, X_reference, n_trials)
            records.append({
                'feature': feat,
                'necessity': round(n, 4),
                'sufficiency': round(s, 4),
                'robustness_score': round((n + s) / 2, 4),
            })
        return pd.DataFrame(records).sort_values('robustness_score', ascending=False)

    # ------------------------------------------------------------------
    # Distance utilities
    # ------------------------------------------------------------------

    @staticmethod
    def distance(cf: np.ndarray, original: np.ndarray, metric: str = "l1") -> float:
        """Compute distance between counterfactual and original instance."""
        diff = cf - original
        if metric == "l1":
            return float(np.abs(diff).sum())
        if metric == "l2":
            return float(np.sqrt((diff ** 2).sum()))
        raise ValueError(f"Unknown metric: '{metric}'.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _predict_class(self, x: np.ndarray) -> int:
        x2d = x.reshape(1, -1)
        if hasattr(self.model, 'predict_proba'):
            return int(np.argmax(self.model.predict_proba(x2d)[0]))
        return int(self.model.predict(x2d)[0])

    def _perturb(self, x: np.ndarray, X_ref: np.ndarray) -> np.ndarray:
        """Random perturbation biased towards reference distribution."""
        cf = x.copy()
        n_features_to_change = self.rng.integers(1, len(self.feature_names) + 1)
        feat_indices = self.rng.choice(len(self.feature_names), n_features_to_change, replace=False)
        for idx in feat_indices:
            feat = self.feature_names[idx]
            if feat in self.categorical_features:
                cf[idx] = self.rng.choice(np.unique(X_ref[:, idx]))
            else:
                lo, hi = self.feature_ranges.get(feat, (X_ref[:, idx].min(), X_ref[:, idx].max()))
                noise = self.rng.normal(0, self.step_size * (hi - lo))
                cf[idx] = np.clip(x[idx] + noise, lo, hi)
        return cf

    def _select_diverse(self, candidates: np.ndarray, k: int) -> np.ndarray:
        """Greedy farthest-point selection for diversity."""
        selected = [candidates[0]]
        for _ in range(1, min(k, len(candidates))):
            dists = np.array([
                min(np.linalg.norm(c - s) for s in selected) for c in candidates
            ])
            selected.append(candidates[np.argmax(dists)])
        return np.array(selected)

    @staticmethod
    def _to_array(x: Union[np.ndarray, pd.DataFrame, pd.Series]) -> np.ndarray:
        if hasattr(x, 'values'):
            return x.values.astype(float)
        return np.asarray(x, dtype=float)
