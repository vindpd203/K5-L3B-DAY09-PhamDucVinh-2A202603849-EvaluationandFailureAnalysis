"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats as sps

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError("human and judge must have the same length")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for h, j in zip(human, judge):
        if j == POS and h == POS:
            cm["tp"] += 1
        elif j == POS and h != POS:
            cm["fp"] += 1
        elif j != POS and h == POS:
            cm["fn"] += 1
        else:
            cm["tn"] += 1
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    precision = cm["tp"] / (cm["tp"] + cm["fp"]) if cm["tp"] + cm["fp"] else 0.0
    recall = cm["tp"] / (cm["tp"] + cm["fn"]) if cm["tp"] + cm["fn"] else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    if len(human) != len(judge) or not human:
        raise ValueError("need equal, non-empty label sequences")
    p_o = sum(h == j for h, j in zip(human, judge)) / len(human)
    p_e = 0.0
    for cat in {POS, "PASS"}:
        ph = sum(h == cat for h in human) / len(human)
        pj = sum(j == cat for j in judge) / len(judge)
        p_e += ph * pj
    if p_e == 1.0:
        raise ValueError("kappa undefined: expected agreement p_e == 1 (constant judge)")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1
    if denom <= 0:
        raise ValueError("sensitivity + specificity - 1 must be > 0")
    corrected = (observed_rate + specificity - 1) / denom
    return max(0.0, min(1.0, corrected))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    if len(a) != len(b) or not a:
        raise ValueError("need equal-length, non-empty per-item series")
    x = np.asarray(list(a), dtype=float)
    y = np.asarray(list(b), dtype=float)
    d = float(x.mean() - y.mean())
    if np.array_equal(x, y):
        return (0.0, 0.0, 0.0)

    def diff(x, y, axis=-1):
        return np.mean(x, axis=axis) - np.mean(y, axis=axis)

    res = sps.bootstrap(np.array([x, y]), diff, n_resamples=n_resamples, paired=True,
                        method="percentile", confidence_level=confidence,
                        rng=np.random.default_rng(rng))
    lo, hi = res.confidence_interval
    return (d, float(lo), float(hi))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    if not (1 <= k <= n) or not (0 <= c <= n):
        raise ValueError(f"need 1 <= k <= n and 0 <= c <= n, got n={n}, c={c}, k={k}")
    if n - c < k:
        return 1.0   # fewer than k failing runs -> at least one of k must pass
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    if not (1 <= k <= n) or not (0 <= c <= n):
        raise ValueError(f"need 1 <= k <= n and 0 <= c <= n, got n={n}, c={c}, k={k}")
    if c < k:
        return 0.0
    return math.comb(c, k) / math.comb(n, k)
