import argparse
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "astrowater_yolov8s_cls_best.pt"
DEFAULT_CONFIDENCE_THRESHOLD = 0.45


@dataclass(frozen=True)
class VisualFeatures:
    brightness: float
    saturation: float
    hue: float
    contrast: float
    particle_count: int
    visual_turbidity_score: float
    dominant_color: str
    visual_class: str


@dataclass(frozen=True)
class DeepLearningPrediction:
    model_name: str
    model_class: str
    model_confidence: float
    mapped_visual_class: str
    pollution_score: float


def capture_with_libcamera(output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "libcamera-still",
        "--nopreview",
        "--timeout",
        "1000",
        "-o",
        str(output_path),
    ]
    subprocess.run(command, check=True)
    return output_path


def load_image(path: Path) -> np.ndarray:
    image_bytes = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Nao foi possivel carregar a imagem: {path}")
    return image


def water_sample_crop(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    if width / max(height, 1) >= 1.45:
        y1 = int(height * 0.44)
        return image[y1:height, :]
    return center_crop(image)


def center_crop(image: np.ndarray, ratio: float = 0.72) -> np.ndarray:
    height, width = image.shape[:2]
    crop_w = int(width * ratio)
    crop_h = int(height * ratio)
    x1 = max((width - crop_w) // 2, 0)
    y1 = max((height - crop_h) // 2, 0)
    return image[y1 : y1 + crop_h, x1 : x1 + crop_w]


def estimate_particles(gray: np.ndarray, hsv: np.ndarray) -> int:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    local_background = cv2.GaussianBlur(gray, (31, 31), 0)
    local_delta = cv2.subtract(local_background, blurred)

    saturation = hsv[:, :, 1]
    dark_candidate = (blurred < 115) & (local_delta > 16)
    low_chroma_candidate = saturation < 115
    mask = np.where(dark_candidate & low_chroma_candidate, 255, 0).astype(np.uint8)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    particles = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if not 14 <= area <= 520:
            continue
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = max(w, h) / max(min(w, h), 1)
        extent = area / max(w * h, 1)
        if circularity >= 0.28 and aspect_ratio <= 2.8 and extent >= 0.28:
            particles += 1
    return particles


def color_name(hue: float, saturation: float, brightness: float) -> str:
    if saturation < 18 and brightness > 180:
        return "incolor"
    if 85 <= hue <= 130:
        return "azul claro"
    if 18 <= hue <= 45:
        return "amarelo claro"
    if 5 <= hue < 18:
        return "marrom claro"
    if brightness < 120 and saturation < 70:
        return "cinza claro"
    return "neutro"


def classify_visual(
    *,
    brightness: float,
    saturation: float,
    hue: float,
    turbidity_score: float,
    particle_count: int,
    dominant_color: str,
) -> str:
    blue_water = dominant_color == "azul claro" and saturation >= 45
    if particle_count >= 25 and not blue_water:
        return "com sedimentos"
    if particle_count >= 45:
        return "com sedimentos"
    if turbidity_score >= 78 and not blue_water and particle_count >= 8:
        return "com sedimentos"
    if dominant_color == "azul claro" and saturation >= 35 and turbidity_score < 35:
        return "azulada"
    if turbidity_score >= 45 or brightness < 135:
        return "turva"
    if dominant_color == "amarelo claro" and saturation >= 35:
        return "amarelada"
    if saturation < 15 and brightness > 235 and particle_count <= 2:
        return "transparente"
    return "limpa"


def map_model_class_to_visual_class(model_class: str) -> str:
    normalized = model_class.strip().lower().replace(" ", "_")
    if normalized in {"plastic_bags", "plastic_straws", "plastic_water_bottle", "combined"}:
        return "com sedimentos"
    if normalized in {"leaves", "bird_feathers", "birds"}:
        return "turva"
    return "limpa"


def pollution_score_for_model_class(model_class: str, confidence: float) -> float:
    normalized = model_class.strip().lower().replace(" ", "_")
    base_scores = {
        "plastic_bags": 92,
        "plastic_straws": 90,
        "plastic_water_bottle": 94,
        "combined": 88,
        "birds": 72,
        "bird_feathers": 62,
        "leaves": 56,
    }
    base_score = base_scores.get(normalized, 35)
    return round(float(np.clip(base_score * confidence, 0, 100)), 2)


def run_deep_learning_model(image_path: Path, model_path: Path) -> DeepLearningPrediction | None:
    if not model_path.exists():
        return None

    runtime_dir = PROJECT_ROOT / ".runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(runtime_dir / "ultralytics"))
    os.environ.setdefault("TMP", str(runtime_dir / "tmp"))
    os.environ.setdefault("TEMP", str(runtime_dir / "tmp"))
    os.environ.setdefault("TMPDIR", str(runtime_dir / "tmp"))
    os.environ.setdefault("ULTRALYTICS_CONFIG_DIR", str(runtime_dir / "ultralytics"))
    Path(os.environ["YOLO_CONFIG_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["TMP"]).mkdir(parents=True, exist_ok=True)
    try:
        from ultralytics import YOLO
    except Exception as exc:
        print(f"[VISION] Ultralytics indisponivel, usando OpenCV: {exc}")
        return None

    model = YOLO(str(model_path))
    result = model.predict(source=str(image_path), verbose=False)[0]
    if result.probs is None:
        return None

    top_index = int(result.probs.top1)
    confidence = float(result.probs.top1conf)
    model_class = str(result.names[top_index])
    return DeepLearningPrediction(
        model_name=model_path.stem,
        model_class=model_class,
        model_confidence=round(confidence, 4),
        mapped_visual_class=map_model_class_to_visual_class(model_class),
        pollution_score=pollution_score_for_model_class(model_class, confidence),
    )


def analyze_image(image: np.ndarray) -> VisualFeatures:
    sample = water_sample_crop(image)
    hsv = cv2.cvtColor(sample, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)

    brightness = float(np.mean(gray))
    saturation = float(np.mean(hsv[:, :, 1]))
    hue = float(np.mean(hsv[:, :, 0]))
    contrast = float(np.std(gray))
    particle_count = estimate_particles(gray, hsv)
    dominant_color = color_name(hue, saturation, brightness)

    blue_water = dominant_color == "azul claro" and saturation >= 45
    if blue_water and particle_count < 15:
        particle_count = 0
    turbidity_from_brightness = 0 if blue_water else np.interp(255 - brightness, [0, 160], [0, 70])
    turbidity_from_contrast = np.interp(contrast, [5, 75], [0, 18 if blue_water else 35])
    turbidity_from_particles = min(particle_count * 1.25, 32)
    visual_turbidity_score = float(
        np.clip(turbidity_from_brightness + turbidity_from_contrast + turbidity_from_particles, 0, 100)
    )

    visual_class = classify_visual(
        brightness=brightness,
        saturation=saturation,
        hue=hue,
        turbidity_score=visual_turbidity_score,
        particle_count=particle_count,
        dominant_color=dominant_color,
    )

    return VisualFeatures(
        brightness=round(brightness, 2),
        saturation=round(saturation, 2),
        hue=round(hue, 2),
        contrast=round(contrast, 2),
        particle_count=particle_count,
        visual_turbidity_score=round(visual_turbidity_score, 2),
        dominant_color=dominant_color,
        visual_class=visual_class,
    )


def build_payload(
    *,
    features: VisualFeatures,
    image_path: Path,
    community_id: int,
    device_id: str,
    prediction: DeepLearningPrediction | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict:
    use_deep_learning = prediction is not None and prediction.model_confidence >= confidence_threshold
    visual_class = prediction.mapped_visual_class if use_deep_learning else features.visual_class
    visual_turbidity_score = max(
        features.visual_turbidity_score,
        prediction.pollution_score if prediction is not None else 0,
    )
    source = "raspberry-pi-camera+yolov8s-cls" if use_deep_learning else "raspberry-pi-camera+opencv"

    return {
        "deviceId": device_id,
        "communityId": community_id,
        "imageName": image_path.name,
        "visualClass": visual_class,
        "visualTurbidityScore": round(visual_turbidity_score, 2),
        "particlesDetected": features.particle_count,
        "dominantColor": features.dominant_color,
        "modelName": prediction.model_name if prediction else "opencv-heuristic",
        "modelClass": prediction.model_class if prediction else features.visual_class,
        "modelConfidence": prediction.model_confidence if prediction else None,
        "pollutionScore": prediction.pollution_score if prediction else features.visual_turbidity_score,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "features": {
            **asdict(features),
            "analysis_mode": "deep-learning" if use_deep_learning else "opencv-fallback",
            "confidence_threshold": confidence_threshold,
        },
    }


def save_payload(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def post_to_backend(backend_url: str, payload: dict) -> None:
    response = requests.post(f"{backend_url.rstrip('/')}/visual-analyses", json=payload, timeout=10)
    response.raise_for_status()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analisa amostra de agua com OpenCV e deep learning opcional.")
    parser.add_argument("--image", type=Path, help="Imagem local da amostra.")
    parser.add_argument("--capture", action="store_true", help="Captura imagem usando libcamera-still.")
    parser.add_argument("--output", type=Path, default=Path("captures/latest.jpg"), help="Saida da captura/JSON.")
    parser.add_argument("--community-id", type=int, default=1)
    parser.add_argument("--device-id", default="ASTRO-RPI-CAM-001")
    parser.add_argument("--backend-url", help="URL do backend para enviar resultado.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH, help="Peso .pt do modelo YOLO de classificacao.")
    parser.add_argument("--disable-deep-learning", action="store_true", help="Usa apenas OpenCV.")
    parser.add_argument("--confidence-threshold", type=float, default=DEFAULT_CONFIDENCE_THRESHOLD)
    parser.add_argument("--save-json", type=Path, help="Salva o payload localmente antes de enviar ao backend.")
    parser.add_argument("--benchmark-runs", type=int, default=1, help="Quantidade de inferencias para medir tempo local.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_path = args.image

    if args.capture:
        image_path = capture_with_libcamera(args.output)
    if image_path is None:
        raise SystemExit("Informe --image ou use --capture no Raspberry Pi.")

    image = load_image(image_path)
    started_at = time.perf_counter()
    features = analyze_image(image)

    prediction = None
    inference_times = []
    if not args.disable_deep_learning:
        runs = max(args.benchmark_runs, 1)
        for _ in range(runs):
            inference_started_at = time.perf_counter()
            prediction = run_deep_learning_model(image_path, args.model)
            inference_times.append(round((time.perf_counter() - inference_started_at) * 1000, 2))

    payload = build_payload(
        features=features,
        image_path=image_path,
        community_id=args.community_id,
        device_id=args.device_id,
        prediction=prediction,
        confidence_threshold=args.confidence_threshold,
    )
    payload["edgeDecision"] = {
        "decisionTakenOnEdge": True,
        "totalProcessingMs": round((time.perf_counter() - started_at) * 1000, 2),
        "inferenceTimesMs": inference_times,
        "averageInferenceMs": round(float(np.mean(inference_times)), 2) if inference_times else None,
        "sentToBackendAfterDecision": bool(args.backend_url),
    }

    if args.save_json:
        save_payload(args.save_json, payload)

    if args.backend_url:
        post_to_backend(args.backend_url, payload)

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
