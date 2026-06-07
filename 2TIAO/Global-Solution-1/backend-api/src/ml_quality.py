import json
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Any

from .schemas import WaterReadingCreate


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = BACKEND_ROOT / "models"
MODEL_PATH = MODEL_DIR / "astrowater_potability_model.joblib"
METADATA_PATH = MODEL_DIR / "astrowater_potability_model_metadata.json"
MIN_CONFIDENT_PROBABILITY = 0.65

FEATURE_TO_FIELD = {
    "ph": "ph",
    "Hardness": "hardness",
    "Solids": "solids",
    "Chloramines": "chloramines",
    "Sulfate": "sulfate",
    "Conductivity": "conductivity",
    "Organic_carbon": "organicCarbon",
    "Trihalomethanes": "trihalomethanes",
    "Turbidity": "mlTurbidity",
}


def predict_potability(payload: WaterReadingCreate) -> dict[str, Any]:
    """Executa o modelo tabular de potabilidade e retorna predicao, confianca e rotulo."""
    values = _feature_values(payload)
    if values is None:
        return {
            "mlPotabilityPrediction": None,
            "mlPotabilityProbability": None,
            "mlQualityLabel": "dados_insuficientes",
            "mlModelName": None,
        }

    model_bundle = _load_model_bundle()
    if model_bundle is None:
        return {
            "mlPotabilityPrediction": None,
            "mlPotabilityProbability": None,
            "mlQualityLabel": "modelo_indisponivel",
            "mlModelName": None,
        }

    model, metadata = model_bundle
    features = metadata["features"]
    model_name = metadata.get("best_model", "modelo_ml")

    try:
        import pandas as pd

        sample = pd.DataFrame([{feature: values[feature] for feature in features}])
        prediction = int(model.predict(sample)[0])
        probability = _predict_probability(model, sample, prediction)
    except Exception:
        return {
            "mlPotabilityPrediction": None,
            "mlPotabilityProbability": None,
            "mlQualityLabel": "erro_inferencia",
            "mlModelName": model_name,
        }

    quality_label = "potavel" if prediction == 1 else "nao_potavel"
    if probability is None or probability < MIN_CONFIDENT_PROBABILITY:
        quality_label = "baixa_confianca"

    return {
        "mlPotabilityPrediction": prediction,
        "mlPotabilityProbability": probability,
        "mlQualityLabel": quality_label,
        "mlModelName": model_name,
    }


def _feature_values(payload: WaterReadingCreate) -> dict[str, float] | None:
    """Extrai os parametros exigidos pelo modelo ML a partir da leitura recebida."""
    values: dict[str, float] = {}
    for feature, field_name in FEATURE_TO_FIELD.items():
        value = getattr(payload, field_name)
        if value is None:
            return None
        values[feature] = float(value)
    return values


@lru_cache(maxsize=1)
def _load_model_bundle():
    """Carrega e guarda em cache o modelo treinado e seus metadados."""
    if not MODEL_PATH.exists() or not METADATA_PATH.exists():
        return None
    try:
        import joblib

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = joblib.load(MODEL_PATH)
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        return model, metadata
    except Exception:
        return None


def _predict_probability(model, sample, prediction: int) -> float | None:
    """Calcula a probabilidade associada a classe prevista quando o modelo suporta."""
    if not hasattr(model, "predict_proba"):
        return None
    probabilities = model.predict_proba(sample)[0]
    classes = list(getattr(model, "classes_", [0, 1]))
    class_index = classes.index(prediction) if prediction in classes else prediction
    return round(float(probabilities[class_index]), 4)
