"""MLflow tracking helpers for training and evaluation scripts."""
from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

DEFAULT_EXPERIMENT_NAME = "fh-mahjong-ai"


def default_tracking_uri() -> str:
    ai_root = Path(__file__).resolve().parents[2]
    return f"sqlite:///{ai_root / 'mlflow.db'}"


def default_artifact_uri() -> str:
    ai_root = Path(__file__).resolve().parents[2]
    return (ai_root / "mlartifacts").resolve().as_uri()


def start_run(
    enabled: bool,
    experiment_name: str = DEFAULT_EXPERIMENT_NAME,
    tracking_uri: Optional[str] = None,
    run_name: Optional[str] = None,
    tags: Optional[Mapping[str, str]] = None,
):
    if not enabled:
        return nullcontext(None)

    import mlflow

    mlflow.set_tracking_uri(tracking_uri or default_tracking_uri())
    client = mlflow.MlflowClient()
    if client.get_experiment_by_name(experiment_name) is None:
        client.create_experiment(experiment_name, artifact_location=default_artifact_uri())
    mlflow.set_experiment(experiment_name)
    return mlflow.start_run(run_name=run_name, tags=dict(tags or {}))


def log_params(params: Mapping[str, Any]) -> None:
    import mlflow

    clean = {key: _param_value(value) for key, value in params.items() if value is not None}
    if clean:
        mlflow.log_params(clean)


def log_metrics(metrics: Mapping[str, Any], step: Optional[int] = None) -> None:
    import mlflow

    clean = dict(_iter_numeric_metrics("", metrics))
    if clean:
        mlflow.log_metrics(clean, step=step)


def log_artifact(path: Optional[Path], artifact_path: Optional[str] = None) -> None:
    if path is None or not path.exists():
        return

    import mlflow

    mlflow.log_artifact(str(path), artifact_path=artifact_path)


def _iter_numeric_metrics(prefix: str, payload: Mapping[str, Any]) -> Iterator[tuple[str, float]]:
    for key, value in payload.items():
        metric_key = _metric_key(f"{prefix}.{key}" if prefix else str(key))
        if isinstance(value, Mapping):
            yield from _iter_numeric_metrics(metric_key, value)
        elif isinstance(value, bool):
            yield metric_key, float(value)
        elif isinstance(value, (int, float)):
            yield metric_key, float(value)


def _metric_key(key: str) -> str:
    return key.replace(" ", "_").replace("/", ".")


def _param_value(value: Any) -> str | int | float | bool:
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    return str(value)
