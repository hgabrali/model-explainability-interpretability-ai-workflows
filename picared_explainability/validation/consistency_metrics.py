"""
Interpretability Consistency Metrics
=====================================
Quantifies agreement between SHAP and LIME explanations to measure
intrinsic model interpretability as defined in:

    Zhang, Y., Chen, L., & Tian, Y. (2026). A Framework for Interpreting
    Machine Learning Models in Bond Default Risk Prediction Using LIME and SHAP.
    Risks, 14(2), 23.

Consistency = 1 - (1/K) * Σ |rank_SHAP(k) - rank_LIME(k)|
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from typing import Dict, List, Optional, Tuple, Union
import scipy.stats as stats


# ---------------------------------------------------------------------------
# Core consistency metrics
# ---------------------------------------------------------------------------

def rank_consistency(
    shap_importance: Union[pd.Series, Dict[str, float]],
    lime_importance: Union[pd.Series, Dict[str, float]],
    top_k: int = 10,
) -> float:
    """
    Compute normalised rank-based consistency between SHAP and LIME.

    Consistency = 1 - (1/K) * Σ_{k=1}^{K} |rank_SHAP(k) - rank_LIME(k)|
                  / max_possible_disagreement

    Parameters
    ----------
    shap_importance : pd.Series or dict
        Feature importance scores from SHAP (higher = more important).
    lime_importance : pd.Series or dict
        Feature importance scores from LIME.
    top_k : int
        Number of top features considered.

    Returns
    -------
    float in [0, 1] — 1 means perfect agreement, 0 means maximal disagreement.
    """
    shap_series = _to_series(shap_importance)
    lime_series = _to_series(lime_importance)

    all_features = shap_series.index.union(lime_series.index)
    n = len(all_features)
    fallback = n + 1

    shap_ranked = _rank_series(shap_series, fallback)
    lime_ranked = _rank_series(lime_series, fallback)

    top_features = shap_ranked.sort_values().head(top_k).index
    rank_diff = sum(
        abs(shap_ranked.get(f, fallback) - lime_ranked.get(f, fallback))
        for f in top_features
    )
    # Normalise: maximum possible disagreement = K * (n - 1)
    max_disagreement = top_k * max(n - 1, 1)
    return max(0.0, 1.0 - rank_diff / max_disagreement)


def spearman_consistency(
    shap_importance: Union[pd.Series, Dict[str, float]],
    lime_importance: Union[pd.Series, Dict[str, float]],
) -> Tuple[float, float]:
    """
    Spearman rank correlation between SHAP and LIME importances.

    Parameters
    ----------
    shap_importance, lime_importance : pd.Series or dict

    Returns
    -------
    (rho, p_value)
    """
    shap_series = _to_series(shap_importance)
    lime_series = _to_series(lime_importance)
    common = shap_series.index.intersection(lime_series.index)
    if len(common) < 3:
        return (float('nan'), float('nan'))
    rho, p = stats.spearmanr(shap_series[common], lime_series[common])
    return float(rho), float(p)


def top_k_overlap(
    shap_importance: Union[pd.Series, Dict[str, float]],
    lime_importance: Union[pd.Series, Dict[str, float]],
    top_k: int = 10,
) -> float:
    """
    Jaccard similarity of the top-K feature sets from SHAP and LIME.

    Returns
    -------
    float in [0, 1]
    """
    shap_top = set(_to_series(shap_importance).nlargest(top_k).index)
    lime_top = set(_to_series(lime_importance).nlargest(top_k).index)
    if not shap_top and not lime_top:
        return 1.0
    return len(shap_top & lime_top) / len(shap_top | lime_top)


def sign_agreement(
    shap_importance: Union[pd.Series, Dict[str, float]],
    lime_importance: Union[pd.Series, Dict[str, float]],
) -> float:
    """
    Fraction of features where SHAP and LIME agree on the sign.

    Returns
    -------
    float in [0, 1]
    """
    shap_series = _to_series(shap_importance)
    lime_series = _to_series(lime_importance)
    common = shap_series.index.intersection(lime_series.index)
    if len(common) == 0:
        return float('nan')
    agree = (np.sign(shap_series[common]) == np.sign(lime_series[common])).sum()
    return float(agree / len(common))


# ---------------------------------------------------------------------------
# Composite report
# ---------------------------------------------------------------------------

def consistency_report(
    shap_importance: Union[pd.Series, Dict[str, float]],
    lime_importance: Union[pd.Series, Dict[str, float]],
    top_k: int = 10,
    model_name: str = "model",
) -> pd.DataFrame:
    """
    Produce a comprehensive consistency report.

    Parameters
    ----------
    shap_importance : pd.Series or dict
    lime_importance : pd.Series or dict
    top_k : int
    model_name : str

    Returns
    -------
    pd.DataFrame with one row containing all metrics.
    """
    rho, p_val = spearman_consistency(shap_importance, lime_importance)
    return pd.DataFrame([{
        'model': model_name,
        'rank_consistency': round(rank_consistency(shap_importance, lime_importance, top_k), 4),
        'spearman_rho': round(rho, 4) if not np.isnan(rho) else None,
        'spearman_p_value': round(p_val, 4) if not np.isnan(p_val) else None,
        f'top_{top_k}_overlap': round(top_k_overlap(shap_importance, lime_importance, top_k), 4),
        'sign_agreement': round(sign_agreement(shap_importance, lime_importance), 4),
    }])


def compare_models(
    results: List[Dict],
    top_k: int = 10,
) -> pd.DataFrame:
    """
    Compare consistency across multiple models.

    Parameters
    ----------
    results : list of dicts, each with keys:
        'model_name', 'shap_importance', 'lime_importance'
    top_k : int

    Returns
    -------
    pd.DataFrame sorted by rank_consistency descending.
    """
    frames = []
    for r in results:
        df = consistency_report(
            r['shap_importance'],
            r['lime_importance'],
            top_k=top_k,
            model_name=r['model_name'],
        )
        frames.append(df)
    return pd.concat(frames, ignore_index=True).sort_values('rank_consistency', ascending=False)


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

def plot_importance_comparison(
    shap_importance: Union[pd.Series, Dict[str, float]],
    lime_importance: Union[pd.Series, Dict[str, float]],
    top_k: int = 15,
    title: str = "SHAP vs. LIME Feature Importance",
    figsize: Tuple[int, int] = (10, 7),
    show: bool = True,
) -> plt.Figure:
    """
    Side-by-side horizontal bar chart comparing SHAP and LIME importances.

    Parameters
    ----------
    shap_importance, lime_importance : pd.Series or dict
    top_k : int
    title : str
    figsize : tuple
    show : bool

    Returns
    -------
    matplotlib Figure
    """
    shap_s = _to_series(shap_importance).nlargest(top_k)
    lime_s = _to_series(lime_importance)
    all_features = shap_s.index
    lime_s = lime_s.reindex(all_features).fillna(0.0)

    fig, axes = plt.subplots(1, 2, figsize=figsize, sharey=True)

    axes[0].barh(all_features[::-1], shap_s[::-1], color='steelblue', alpha=0.85)
    axes[0].set_title('SHAP Importance', fontweight='bold')
    axes[0].set_xlabel('Mean |SHAP value|')

    axes[1].barh(all_features[::-1], lime_s[::-1], color='coral', alpha=0.85)
    axes[1].set_title('LIME Importance', fontweight='bold')
    axes[1].set_xlabel('Mean |LIME weight|')

    fig.suptitle(title, fontsize=13, fontweight='bold')
    plt.tight_layout()

    if show:
        plt.show()
    return fig


def plot_rank_scatter(
    shap_importance: Union[pd.Series, Dict[str, float]],
    lime_importance: Union[pd.Series, Dict[str, float]],
    top_k: int = 20,
    title: str = "SHAP vs. LIME Rank Scatter",
    figsize: Tuple[int, int] = (6, 6),
    show: bool = True,
) -> plt.Figure:
    """
    Scatter plot of SHAP ranks vs LIME ranks for the top-K features.

    Perfect consistency lies on the diagonal y = x.
    """
    shap_s = _to_series(shap_importance)
    lime_s = _to_series(lime_importance)
    common = shap_s.index.intersection(lime_s.index)
    shap_r = _rank_series(shap_s, len(common) + 1)
    lime_r = _rank_series(lime_s, len(common) + 1)
    top_features = shap_r.sort_values().head(top_k).index

    xs = [shap_r.get(f, len(common) + 1) for f in top_features]
    ys = [lime_r.get(f, len(common) + 1) for f in top_features]
    labels = list(top_features)

    fig, ax = plt.subplots(figsize=figsize)
    ax.scatter(xs, ys, color='steelblue', zorder=3)
    for x, y, lbl in zip(xs, ys, labels):
        ax.annotate(lbl, (x, y), fontsize=7, ha='left', va='bottom')
    lim = max(max(xs), max(ys)) + 1
    ax.plot([1, lim], [1, lim], 'k--', linewidth=0.8, label='Perfect agreement')
    ax.set_xlabel('SHAP rank')
    ax.set_ylabel('LIME rank')
    ax.set_title(title, fontweight='bold')
    ax.legend(fontsize=8)
    plt.tight_layout()
    if show:
        plt.show()
    return fig


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _to_series(x: Union[pd.Series, Dict]) -> pd.Series:
    if isinstance(x, dict):
        return pd.Series(x)
    return x.copy()


def _rank_series(s: pd.Series, fallback: int) -> pd.Series:
    """Return rank series (1 = most important)."""
    return s.rank(ascending=False, method='min').rename(None)
