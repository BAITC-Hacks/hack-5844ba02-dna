"""Incoming-profile model for fourth-generation traversal truncation."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

LOG = logging.getLogger(__name__)
FEATURE_NAMES = ("log1p_in_kzt", "log1p_in_amount", "in_deg", "log1p_in_tx", "first_in_day", "last_in_day")


def _add_incoming_profile(features: pd.DataFrame, transactions: pd.DataFrame) -> pd.DataFrame:
    """Add input-only values which remain observable at the depth-four frontier."""
    incoming = transactions.copy()
    incoming["day"] = pd.to_datetime(incoming["date"]).dt.day.astype(float)
    days = incoming.groupby("dst").agg(first_in_day=("day", "min"), last_in_day=("day", "max"))
    result = features.merge(days, how="left", left_on="gid", right_index=True)
    result[["first_in_day", "last_in_day"]] = result[["first_in_day", "last_in_day"]].fillna(0.0)
    result["log1p_in_kzt"] = np.log1p(result["in_kzt"])
    result["log1p_in_amount"] = np.log1p((result["in_kzt"] / result["in_tx"].replace(0, np.nan)).fillna(0.0))
    result["log1p_in_tx"] = np.log1p(result["in_tx"])
    return result


def add_frontier_probability(features: pd.DataFrame, transactions: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, dict]:
    """Score depth-four truncation against an early-depth terminal proxy.

    The result is a model similarity score, not a calibrated probability that money
    stopped: outgoing data beyond the traversal frontier are unavailable.
    """
    result = _add_incoming_profile(features, transactions)
    settings = cfg["roles"]["frontier"]
    train = result.loc[(~result.is_seed.astype(bool)) & result.depth.isin(settings["train_depths"]) & result.in_deg.ge(1)]
    x_train, y_train = train.loc[:, FEATURE_NAMES], train.out_deg.eq(0).astype(int)
    folds = min(int(settings["cv_folds"]), int(y_train.value_counts().min()))
    if folds < 2 or y_train.nunique() < 2:
        raise ValueError("Недостаточно классов для обучения frontier-модели")
    model = make_pipeline(StandardScaler(), LogisticRegression(random_state=cfg["seed"], max_iter=settings["max_iter"]))
    oof = np.zeros(len(train), dtype=float)
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=cfg["seed"])
    for fit_idx, test_idx in cv.split(x_train, y_train):
        model.fit(x_train.iloc[fit_idx], y_train.iloc[fit_idx])
        oof[test_idx] = model.predict_proba(x_train.iloc[test_idx])[:, 1]
    auc = float(roc_auc_score(y_train, oof))
    model.fit(x_train, y_train)
    truncated = result.depth.eq(cfg["data"]["max_depth"]) & result.out_deg.eq(0)
    result["p_terminal"] = np.where(result.out_deg.eq(0), 1.0, 0.0)
    result.loc[truncated, "p_terminal"] = model.predict_proba(result.loc[truncated, FEATURE_NAMES])[:, 1]
    coefficients = dict(zip(FEATURE_NAMES, (float(v) for v in model.named_steps["logisticregression"].coef_[0]), strict=True))
    metadata = {"auc": auc, "coefficients": coefficients, "n_train": int(len(train)), "target": "proxy: out_deg == 0 at depths 1–3", "scope": "model similarity only; not observed retention"}
    LOG.info("Frontier-модель: AUC %.3f, обучающих узлов %d", auc, len(train))
    return result, metadata
