"""Estatística sem dependências externas (numpy/pandas): Pearson, Spearman e IC via Fisher z."""
from __future__ import annotations

import math
from typing import Dict, Optional

import numpy as np
import pandas as pd


def _normal_two_sided_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def correlation(x: pd.Series, y: pd.Series, method: str = "pearson") -> Dict[str, Optional[float]]:
    data = pd.DataFrame({"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}).dropna()
    n = int(len(data))
    if n < 3 or data["x"].nunique() < 2 or data["y"].nunique() < 2:
        return {"method": method, "r": None, "n": n, "ci95": None, "p_value_approx": None}
    if method == "spearman":
        a, b = data["x"].rank(method="average"), data["y"].rank(method="average")
    else:
        a, b = data["x"], data["y"]
    r = float(np.corrcoef(a.to_numpy(float), b.to_numpy(float))[0, 1])
    ci = None
    p = None
    if n > 3 and abs(r) < 1:
        z = math.atanh(r)
        se = 1 / math.sqrt(n - 3)
        ci = [round(math.tanh(z - 1.96 * se), 4), round(math.tanh(z + 1.96 * se), 4)]
        p = round(_normal_two_sided_p(z / se), 6)  # aproximação normal (adequada para n grande)
    return {"method": method, "r": round(r, 4), "n": n, "ci95": ci, "p_value_approx": p}


def strength_label(r: Optional[float]) -> str:
    if r is None:
        return "indeterminada"
    a = abs(r)
    if a < 0.1:
        return "desprezível"
    if a < 0.3:
        return "fraca"
    if a < 0.5:
        return "moderada"
    return "forte"
