from pathlib import Path

import cv2
import numpy as np


SAMPLES = {
    "transparente": (238, 248, 250),
    "azulada": (235, 205, 120),
    "limpa": (224, 236, 235),
    "turva": (175, 170, 150),
    "amarelada": (135, 215, 235),
    "com_sedimentos": (110, 145, 165),
}


def add_sediments(image: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(42)
    for _ in range(36):
        x = int(rng.integers(35, image.shape[1] - 35))
        y = int(rng.integers(35, image.shape[0] - 35))
        radius = int(rng.integers(3, 10))
        cv2.circle(image, (x, y), radius, (55, 45, 38), -1)
    return image


def make_sample(label: str, bgr: tuple[int, int, int]) -> np.ndarray:
    image = np.full((360, 360, 3), bgr, dtype=np.uint8)
    cv2.circle(image, (180, 180), 150, (245, 248, 248), 12)
    if label == "turva":
        noise = np.random.default_rng(7).normal(0, 14, image.shape).astype(np.int16)
        image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    if label == "com_sedimentos":
        image = add_sediments(image)
    return image


def main() -> None:
    output_dir = Path(__file__).resolve().parents[1] / "captures" / "samples"
    output_dir.mkdir(parents=True, exist_ok=True)
    for label, bgr in SAMPLES.items():
        cv2.imwrite(str(output_dir / f"{label}.png"), make_sample(label, bgr))
    print(f"Amostras geradas em {output_dir}")


if __name__ == "__main__":
    main()
