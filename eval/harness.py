"""
Walk-forward evaluation harness for WBGT forecasting.

Defines the comparison every forecasting experiment is scored against, and
is structured so that temporal leakage (training on data from after the
forecast date) is difficult to introduce by accident.

Baselines:
  - Persistence: WBGT at t + lead equals WBGT at t.
  - Climatology: the historical average for the day-of-year and hour,
    computed only from data strictly before the forecast date.
  - Raw signal passthrough: the model's input before any correction, for
    checking whether a correction improves on the uncorrected forecast.

Metrics:
  - RMSE and MAE on WBGT.
  - Hit rate and false-negative rate at the regulatory threshold (32.1 C,
    Qatar Decision 17/2021). For heat safety the false-negative rate
    matters more than average error.
"""

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from src.wbgt import QATAR_WBGT_STOP_WORK_THRESHOLD_C


@dataclass
class EvalResult:
    name: str
    rmse: float
    mae: float
    hit_rate: float  # of true threshold-exceedance hours, fraction correctly flagged
    false_negative_rate: float  # of true exceedance hours, fraction MISSED (the dangerous error)
    false_positive_rate: float  # of true non-exceedance hours, fraction wrongly flagged
    n_exceedance_hours: int
    n_total_hours: int


def evaluate(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    threshold_c: float = QATAR_WBGT_STOP_WORK_THRESHOLD_C,
    name: str = "unnamed",
) -> EvalResult:
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    y_true, y_pred = y_true[mask], y_pred[mask]

    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y_true - y_pred)))

    true_exceed = y_true > threshold_c
    pred_exceed = y_pred > threshold_c

    n_exceed = int(true_exceed.sum())
    if n_exceed > 0:
        hit_rate = float((true_exceed & pred_exceed).sum() / n_exceed)
        fnr = float((true_exceed & ~pred_exceed).sum() / n_exceed)
    else:
        hit_rate, fnr = float("nan"), float("nan")

    n_non_exceed = int((~true_exceed).sum())
    fpr = (
        float((~true_exceed & pred_exceed).sum() / n_non_exceed)
        if n_non_exceed > 0
        else float("nan")
    )

    return EvalResult(
        name=name,
        rmse=rmse,
        mae=mae,
        hit_rate=hit_rate,
        false_negative_rate=fnr,
        false_positive_rate=fpr,
        n_exceedance_hours=n_exceed,
        n_total_hours=len(y_true),
    )


def baseline_persistence(df: pd.DataFrame, target_col: str, lead_hours: int) -> np.ndarray:
    """Predict WBGT at t+lead_hours as equal to WBGT at t."""
    return df[target_col].shift(lead_hours).values


def baseline_climatology_walk_forward(
    df: pd.DataFrame, target_col: str, time_col: str = "time"
) -> np.ndarray:
    """
    Predict WBGT for a given (month, day, hour) as the historical average
    for that (month, day, hour) computed ONLY from rows strictly before
    the current row's date. This is the walk-forward-safe version, a
    naive full-period average would leak future information into early
    predictions.

    This is O(n^2) in a naive form; fine for a single-station hourly
    series over a decade (under ~100k rows), revisit if you scale up
    to many stations.
    """
    df = df.copy()
    df["doy_hour"] = df[time_col].dt.strftime("%m-%d-%H")
    keys = df["doy_hour"].values
    targets = df[target_col].values
    preds = np.full(len(df), np.nan)
    seen: dict[str, list[float]] = {}
    for i in range(len(df)):
        key = keys[i]
        history = seen.get(key)
        if history:
            preds[i] = float(np.mean(history))
        seen.setdefault(key, []).append(targets[i])
    return preds


def walk_forward_splits(n: int, n_folds: int = 5, min_train_frac: float = 0.4):
    """
    Yields (train_idx, test_idx) tuples for expanding-window walk-forward
    validation: fold k trains on everything before a cutoff and tests on
    the next contiguous block, cutoff moves forward each fold. Never
    shuffles, never lets test-fold data appear in any earlier train set.
    """
    min_train = int(n * min_train_frac)
    remaining = n - min_train
    fold_size = remaining // n_folds
    for k in range(n_folds):
        train_end = min_train + k * fold_size
        test_end = min(train_end + fold_size, n)
        if train_end >= test_end:
            continue
        yield np.arange(0, train_end), np.arange(train_end, test_end)


def run_baseline_comparison(
    df: pd.DataFrame,
    target_col: str = "wbgt_c",
    time_col: str = "time",
    lead_hours: int = 24,
) -> list[EvalResult]:
    """
    Runs persistence and walk-forward climatology against the target
    column and returns EvalResult for each. This is the harness your
    Layer 1 model's predictions get plugged into and compared against,
    same evaluate() function, same metrics, no special treatment.
    """
    results = []

    persistence_pred = baseline_persistence(df, target_col, lead_hours)
    results.append(
        evaluate(df[target_col].values, persistence_pred, name=f"persistence_{lead_hours}h")
    )

    climatology_pred = baseline_climatology_walk_forward(df, target_col, time_col)
    results.append(evaluate(df[target_col].values, climatology_pred, name="climatology_walkforward"))

    return results
