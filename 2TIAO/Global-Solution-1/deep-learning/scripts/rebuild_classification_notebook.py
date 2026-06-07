import json
from pathlib import Path


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(True),
    }


cells = [
    md(
        """# AstroWater AI - Deep Learning para Classificacao Visual de Residuos em Agua

Este notebook usa o dataset `orvillethomas/dataset-for-surface-water-waste-objects` para treinar modelos de deep learning capazes de classificar o tipo de residuo/sinal visual de poluicao encontrado em aguas superficiais.

Importante: este dataset esta organizado por pastas de classe e nao possui bounding boxes. Portanto, ele e adequado para **classificacao de imagem**, nao para deteccao de objetos com caixas. Para deteccao real com YOLO detection seria necessario um dataset anotado com labels de bounding box.

Na narrativa da GS, o Raspberry Pi captura uma imagem e o modelo classifica o principal tipo de poluente visual, gerando um indice de poluicao visual para combinar com sensores e ML tabular.
"""
    ),
    md(
        """## 0. Instalacao opcional

Se ainda nao instalou as dependencias via `requirements.txt`, execute a linha comentada abaixo.
"""
    ),
    code(
        """# CPU / instalacao simples:
# !pip install kagglehub ultralytics pandas numpy matplotlib seaborn opencv-python pyyaml scikit-learn

# GPU NVIDIA no Windows:
# !pip install --upgrade --force-reinstall torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
"""
    ),
    md("## 1. Imports e configuracoes\n"),
    code(
        """from pathlib import Path
import json
import random
import re
import shutil
import sys
import warnings

import cv2
import kagglehub
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
from sklearn.metrics import classification_report, confusion_matrix
from ultralytics import YOLO

warnings.filterwarnings('ignore')
sns.set_theme(style='whitegrid')

RANDOM_STATE = 42
random.seed(RANDOM_STATE)
np.random.seed(RANDOM_STATE)

BASE_DIR = Path.cwd()
if (BASE_DIR / 'deep-learning' / 'surface_water_waste_detection.ipynb').exists():
    BASE_DIR = BASE_DIR / 'deep-learning'

DATA_DIR = BASE_DIR / 'data'
RAW_DIR = DATA_DIR / 'raw'
PREPARED_DATASET_DIR = DATA_DIR / 'prepared_surface_waste_cls'
REPORT_DIR = BASE_DIR / 'reports'
RUNS_DIR = BASE_DIR / 'runs'
MODEL_DIR = BASE_DIR / 'models'

for directory in [RAW_DIR, PREPARED_DATASET_DIR, REPORT_DIR, RUNS_DIR, MODEL_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp'}
BASE_DIR
"""
    ),
    md(
        """## 2. Download do dataset com KaggleHub

A celula abaixo usa exatamente o padrao solicitado para baixar a versao mais recente do dataset.
"""
    ),
    code(
        """def find_cached_kaggle_dataset(owner: str, dataset: str) -> Path | None:
    cache_root = Path.home() / '.cache' / 'kagglehub' / 'datasets' / owner / dataset / 'versions'
    if not cache_root.exists():
        return None
    versions = sorted(
        [path for path in cache_root.iterdir() if path.is_dir()],
        key=lambda path: int(path.name) if path.name.isdigit() else -1,
        reverse=True,
    )
    return versions[0] if versions else None

try:
    path = kagglehub.dataset_download('orvillethomas/dataset-for-surface-water-waste-objects')
    print('Path to dataset files:', path)
except Exception as error:
    cached_path = find_cached_kaggle_dataset('orvillethomas', 'dataset-for-surface-water-waste-objects')
    if cached_path is None:
        raise
    path = str(cached_path)
    print('KaggleHub falhou, usando cache local:', path)
    print('Erro original:', type(error).__name__, error)

DATASET_PATH = Path(path)
DATASET_PATH
"""
    ),
    md(
        """## 3. Inspecao da estrutura do dataset

O dataset vem separado por pastas de classe, como `Plastic Bags`, `Plastic Straws`, `Leaves`, etc. Vamos transformar essa estrutura em um dataset de classificacao com splits `train`, `val` e `test`.
"""
    ),
    code(
        """def find_class_root(dataset_path: Path) -> Path:
    candidates = [dataset_path / 'Datasets', dataset_path]
    for candidate in candidates:
        if not candidate.exists():
            continue
        class_dirs = [directory for directory in candidate.iterdir() if directory.is_dir()]
        image_counts = []
        for directory in class_dirs:
            count = sum(1 for file in directory.rglob('*') if file.suffix.lower() in IMAGE_EXTENSIONS)
            if count:
                image_counts.append(count)
        if len(image_counts) >= 2:
            return candidate
    raise FileNotFoundError('Nao encontrei pastas de classe com imagens no dataset baixado.')

CLASS_ROOT = find_class_root(DATASET_PATH)
print('Raiz das classes:', CLASS_ROOT)

class_dirs = [directory for directory in CLASS_ROOT.iterdir() if directory.is_dir()]
dataset_rows = []
for class_dir in class_dirs:
    for image_path in class_dir.rglob('*'):
        if image_path.suffix.lower() in IMAGE_EXTENSIONS:
            dataset_rows.append({'image': str(image_path), 'class_name': class_dir.name})

dataset_df = pd.DataFrame(dataset_rows)
display(dataset_df.head())
display(dataset_df['class_name'].value_counts().to_frame('images'))
print('Total de imagens:', len(dataset_df))
print('Total de classes:', dataset_df['class_name'].nunique())
"""
    ),
    md(
        """## 4. Exploracao de dados visuais

Nesta etapa avaliamos quantidade de imagens por classe, dimensoes das imagens e exemplos visuais. Isso ajuda a justificar tratamento, balanceamento e limitacoes.
"""
    ),
    code(
        """image_metadata = []
for row in dataset_df.itertuples(index=False):
    image = cv2.imread(row.image)
    if image is None:
        continue
    height, width = image.shape[:2]
    image_metadata.append({
        'image': row.image,
        'class_name': row.class_name,
        'width': width,
        'height': height,
        'aspect_ratio': width / height if height else np.nan,
    })

metadata_df = pd.DataFrame(image_metadata)
metadata_df.to_csv(REPORT_DIR / 'image_metadata.csv', index=False)
display(metadata_df.describe())

fig, axes = plt.subplots(1, 3, figsize=(17, 4))
class_order = dataset_df['class_name'].value_counts().index
sns.countplot(data=dataset_df, y='class_name', order=class_order, ax=axes[0], color='#2563eb')
axes[0].set_title('Quantidade de imagens por classe')
axes[0].set_xlabel('Imagens')
axes[0].set_ylabel('Classe')

sns.histplot(data=metadata_df, x='width', bins=30, ax=axes[1], color='#2f9e65')
axes[1].set_title('Distribuicao das larguras')

sns.histplot(data=metadata_df, x='height', bins=30, ax=axes[2], color='#9333ea')
axes[2].set_title('Distribuicao das alturas')

plt.tight_layout()
plt.savefig(REPORT_DIR / 'dataset_classification_overview.png', dpi=160)
plt.show()
"""
    ),
    code(
        """sample_rows = []
for _, group in dataset_df.groupby('class_name', sort=False):
    sample_rows.append(group.sample(min(2, len(group)), random_state=RANDOM_STATE))

sample_df = pd.concat(sample_rows, ignore_index=True)

n_samples = len(sample_df)
n_cols = 4
n_rows = int(np.ceil(n_samples / n_cols))
fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, max(4, 4 * n_rows)))
axes = np.array(axes).reshape(-1)

for axis, (_, row) in zip(axes, sample_df.iterrows()):
    image = cv2.imread(row['image'])
    if image is None:
        axis.axis('off')
        continue
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    axis.imshow(image)
    axis.set_title(row['class_name'])
    axis.axis('off')

for axis in axes[n_samples:]:
    axis.axis('off')

plt.tight_layout()
plt.savefig(REPORT_DIR / 'sample_images_by_class.png', dpi=160)
plt.show()
"""
    ),
    md(
        """## 5. Preparacao train/val/test

O Ultralytics classification espera uma estrutura do tipo:

```text
dataset/
  train/classe_x/imagem.jpg
  val/classe_x/imagem.jpg
  test/classe_x/imagem.jpg
```

Vamos criar essa estrutura por classe para preservar a proporcao sem quebrar em classes pequenas. A classe `Combined`, por exemplo, tem poucas imagens, entao o `train_test_split` estratificado em duas etapas pode falhar.
"""
    ),
    code(
        """def safe_class_name(name: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', name.strip())
    return cleaned.strip('_')

prepared_df = dataset_df.copy()
prepared_df['safe_class_name'] = prepared_df['class_name'].map(safe_class_name)
class_name_map = dict(zip(prepared_df['safe_class_name'], prepared_df['class_name']))

def split_class_group(group: pd.DataFrame) -> pd.DataFrame:
    group = group.sample(frac=1, random_state=RANDOM_STATE).reset_index(drop=True)
    total = len(group)

    if total >= 3:
        test_count = max(1, round(total * 0.15))
        val_count = max(1, round(total * 0.15))
        train_count = total - val_count - test_count
        if train_count < 1:
            train_count = 1
            remaining = total - train_count
            val_count = max(0, remaining // 2)
            test_count = remaining - val_count
    elif total == 2:
        train_count, val_count, test_count = 1, 1, 0
    else:
        train_count, val_count, test_count = 1, 0, 0

    split_labels = (
        ['train'] * train_count
        + ['val'] * val_count
        + ['test'] * test_count
    )
    split_labels = split_labels[:total]
    return group.assign(split=split_labels)

split_groups = []
for _, group in prepared_df.groupby('safe_class_name', sort=False):
    split_groups.append(split_class_group(group.copy()))

splits_df = pd.concat(split_groups, ignore_index=True)

display(
    splits_df
    .groupby(['split', 'safe_class_name'])
    .size()
    .to_frame('images')
    .reset_index()
    .sort_values(['safe_class_name', 'split'])
)

if PREPARED_DATASET_DIR.exists():
    shutil.rmtree(PREPARED_DATASET_DIR)

for row in splits_df.itertuples(index=False):
    source = Path(row.image)
    target_dir = PREPARED_DATASET_DIR / row.split / row.safe_class_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    if target.exists():
        target = target_dir / f'{source.stem}_{abs(hash(str(source))) % 100000}{source.suffix}'
    shutil.copy2(source, target)

splits_df.to_csv(REPORT_DIR / 'classification_splits.csv', index=False)
(REPORT_DIR / 'class_name_map.json').write_text(json.dumps(class_name_map, indent=2, ensure_ascii=False), encoding='utf-8')
print('Dataset preparado em:', PREPARED_DATASET_DIR)
"""
    ),
    md(
        """## 6. Treinamento comparativo de modelos

Vamos comparar arquiteturas de classificacao do Ultralytics. Modelos menores sao mais interessantes para rodar no Raspberry Pi, enquanto modelos maiores podem ter melhor desempenho no notebook.

Para teste rapido use `EPOCHS = 10`. Para resultado melhor, use 30, 50 ou mais.
"""
    ),
    code(
        """EPOCHS = 30
IMAGE_SIZE = 224
BATCH_SIZE = 16
DEVICE = 0 if torch.cuda.is_available() else 'cpu'

print('PyTorch:', torch.__version__)
print('Python usado:', sys.executable)
print('CUDA disponivel:', torch.cuda.is_available())
print('CUDA do PyTorch:', torch.version.cuda)
print('Dispositivos CUDA:', torch.cuda.device_count())
print('Dispositivo usado:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')

model_candidates = {
    'yolov8n-cls': 'yolov8n-cls.pt',
    'yolov8s-cls': 'yolov8s-cls.pt',
    'yolo11n-cls': 'yolo11n-cls.pt',
}

training_runs = []
for model_label, weights in model_candidates.items():
    print(f'\\nTreinando {model_label} usando {weights}')
    model = YOLO(weights)
    results = model.train(
        data=str(PREPARED_DATASET_DIR),
        epochs=EPOCHS,
        imgsz=IMAGE_SIZE,
        batch=BATCH_SIZE,
        device=DEVICE,
        project=str(RUNS_DIR / 'classify'),
        name=f'astrowater_{model_label}',
        seed=RANDOM_STATE,
        exist_ok=True,
        patience=10,
        plots=True,
    )
    training_runs.append({
        'model': model_label,
        'weights': weights,
        'run_dir': str(Path(results.save_dir)),
        'best_weights': str(Path(results.save_dir) / 'weights' / 'best.pt'),
    })

training_runs_df = pd.DataFrame(training_runs)
training_runs_df.to_csv(REPORT_DIR / 'classification_training_runs.csv', index=False)
display(training_runs_df)
"""
    ),
    md(
        """## 7. Curvas de treino

Cada modelo gera um `results.csv`. Vamos consolidar as curvas para comparar evolucao de loss e acuracia.
"""
    ),
    code(
        """def read_results_csv(run_dir: Path, model_name: str) -> pd.DataFrame:
    csv_path = run_dir / 'results.csv'
    if not csv_path.exists():
        return pd.DataFrame()
    data = pd.read_csv(csv_path)
    data.columns = [column.strip() for column in data.columns]
    data['model'] = model_name
    return data

curve_frames = [read_results_csv(Path(row.run_dir), row.model) for row in training_runs_df.itertuples(index=False)]
curves_df = pd.concat([frame for frame in curve_frames if not frame.empty], ignore_index=True)
curves_df.to_csv(REPORT_DIR / 'classification_training_curves.csv', index=False)
display(curves_df.tail())

metrics_to_plot = [column for column in curves_df.columns if any(term in column for term in ['loss', 'accuracy', 'top1', 'top5'])]
metrics_to_plot = [column for column in metrics_to_plot if column not in {'model'}]

n_cols = 2
n_rows = int(np.ceil(len(metrics_to_plot) / n_cols)) or 1
fig, axes = plt.subplots(n_rows, n_cols, figsize=(14, 4 * n_rows))
axes = np.array(axes).reshape(-1)
for axis, metric in zip(axes, metrics_to_plot):
    sns.lineplot(data=curves_df, x='epoch', y=metric, hue='model', ax=axis)
    axis.set_title(metric)
    axis.set_xlabel('Epoca')
for axis in axes[len(metrics_to_plot):]:
    axis.axis('off')
plt.tight_layout()
plt.savefig(REPORT_DIR / 'classification_training_curves.png', dpi=160)
plt.show()
"""
    ),
    md(
        """## 8. Avaliacao no conjunto de teste

O Ultralytics calcula acuracia top-1/top-5. Para deixar a avaliacao mais explicavel para a FIAP, tambem vamos montar matriz de confusao e classification report com precision, recall e F1 por classe.
"""
    ),
    code(
        """test_images = [file for file in (PREPARED_DATASET_DIR / 'test').rglob('*') if file.suffix.lower() in IMAGE_EXTENSIONS]
class_names = sorted([directory.name for directory in (PREPARED_DATASET_DIR / 'train').iterdir() if directory.is_dir()])
class_to_id = {name: index for index, name in enumerate(class_names)}

evaluation_rows = []
prediction_tables = {}

for row in training_runs_df.itertuples(index=False):
    best_weights = Path(row.best_weights)
    if not best_weights.exists():
        print('Pesos nao encontrados:', best_weights)
        continue
    model = YOLO(str(best_weights))
    predictions = model.predict(source=[str(file) for file in test_images], imgsz=IMAGE_SIZE, device=DEVICE, verbose=False)

    y_true = []
    y_pred = []
    confidence_rows = []
    for image_path, result in zip(test_images, predictions):
        true_class = image_path.parent.name
        predicted_id = int(result.probs.top1)
        predicted_class = result.names[predicted_id]
        confidence = float(result.probs.top1conf.cpu().numpy())
        y_true.append(class_to_id[true_class])
        y_pred.append(class_to_id[predicted_class])
        confidence_rows.append({
            'image': str(image_path),
            'true_class': true_class,
            'predicted_class': predicted_class,
            'confidence': confidence,
        })

    report = classification_report(
        y_true,
        y_pred,
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )
    evaluation_rows.append({
        'model': row.model,
        'accuracy': report['accuracy'],
        'macro_precision': report['macro avg']['precision'],
        'macro_recall': report['macro avg']['recall'],
        'macro_f1': report['macro avg']['f1-score'],
        'weighted_f1': report['weighted avg']['f1-score'],
        'best_weights': str(best_weights),
    })
    prediction_tables[row.model] = pd.DataFrame(confidence_rows)
    prediction_tables[row.model].to_csv(REPORT_DIR / f'{row.model}_test_predictions.csv', index=False)

evaluation_df = pd.DataFrame(evaluation_rows).sort_values('macro_f1', ascending=False)
evaluation_df.to_csv(REPORT_DIR / 'classification_model_comparison.csv', index=False)
display(evaluation_df)

best_classification_model = evaluation_df.iloc[0]['model']
best_classification_weights = Path(evaluation_df.iloc[0]['best_weights'])
print('Melhor modelo por macro F1:', best_classification_model)
print('Pesos:', best_classification_weights)
"""
    ),
    code(
        """plot_eval = evaluation_df.melt(
    id_vars='model',
    value_vars=['accuracy', 'macro_precision', 'macro_recall', 'macro_f1', 'weighted_f1'],
    var_name='metric',
    value_name='score',
)

plt.figure(figsize=(11, 5))
sns.barplot(data=plot_eval, x='model', y='score', hue='metric')
plt.title('Comparacao final dos modelos de classificacao')
plt.xlabel('Modelo')
plt.ylabel('Score no teste')
plt.ylim(0, 1)
plt.xticks(rotation=20, ha='right')
plt.tight_layout()
plt.savefig(REPORT_DIR / 'classification_model_comparison.png', dpi=160)
plt.show()
"""
    ),
    md(
        """## 9. Matrizes de confusao por modelo

A matriz de confusao mostra quais tipos de residuos o modelo confunde. Isso e importante para discutir risco e limitacao do sensor visual.
"""
    ),
    code(
        """n_models = len(evaluation_df)
n_cols = 2
n_rows = int(np.ceil(n_models / n_cols))
fig, axes = plt.subplots(n_rows, n_cols, figsize=(7 * n_cols, 6 * n_rows))
axes = np.array(axes).reshape(-1)

for axis, model_name in zip(axes, evaluation_df['model']):
    table = prediction_tables[model_name]
    cm = confusion_matrix(table['true_class'], table['predicted_class'], labels=class_names)
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=class_names, yticklabels=class_names, ax=axis)
    axis.set_title(model_name)
    axis.set_xlabel('Predito')
    axis.set_ylabel('Real')
    axis.tick_params(axis='x', rotation=45)

for axis in axes[n_models:]:
    axis.axis('off')

plt.tight_layout()
plt.savefig(REPORT_DIR / 'classification_confusion_matrices.png', dpi=160)
plt.show()
"""
    ),
    md(
        """## 10. Inferencia e indice visual de poluicao

Como este dataset e de classificacao, o indice visual pode combinar a classe prevista com a confianca do modelo. Classes plasticas recebem peso maior; classes naturais como folhas/penas recebem peso menor, mas ainda indicam material flutuante.
"""
    ),
    code(
        """pollution_weights = {
    'Plastic_Bags': 95,
    'Plastic_Straws': 90,
    'Plastic_Water_Bottle': 100,
    'Combined': 85,
    'Leaves': 45,
    'Bird_Feathers': 35,
    'Birds': 20,
}

best_model = YOLO(str(best_classification_weights))
sample_images = random.sample(test_images, min(8, len(test_images)))
sample_results = best_model.predict(source=[str(file) for file in sample_images], imgsz=IMAGE_SIZE, device=DEVICE, verbose=False)

pollution_rows = []
for image_path, result in zip(sample_images, sample_results):
    predicted_id = int(result.probs.top1)
    predicted_class = result.names[predicted_id]
    confidence = float(result.probs.top1conf.cpu().numpy())
    base_score = pollution_weights.get(predicted_class, 60)
    visual_pollution_score = round(base_score * confidence, 2)
    pollution_rows.append({
        'image': image_path.name,
        'true_class': image_path.parent.name,
        'predicted_class': predicted_class,
        'confidence': round(confidence, 4),
        'visual_pollution_score': visual_pollution_score,
    })

pollution_df = pd.DataFrame(pollution_rows).sort_values('visual_pollution_score', ascending=False)
pollution_df.to_csv(REPORT_DIR / 'sample_visual_pollution_scores.csv', index=False)
display(pollution_df)
"""
    ),
    md("## 11. Visualizacao das predicoes de exemplo\n"),
    code(
        """n_samples = len(sample_images)
n_cols = 4
n_rows = int(np.ceil(n_samples / n_cols))
fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
axes = np.array(axes).reshape(-1)

for axis, image_path, result in zip(axes, sample_images, sample_results):
    image = cv2.imread(str(image_path))
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    predicted_id = int(result.probs.top1)
    predicted_class = result.names[predicted_id]
    confidence = float(result.probs.top1conf.cpu().numpy())
    axis.imshow(image)
    axis.set_title(f'Real: {image_path.parent.name}\\nPred: {predicted_class} ({confidence:.2f})')
    axis.axis('off')

for axis in axes[n_samples:]:
    axis.axis('off')

plt.tight_layout()
plt.savefig(REPORT_DIR / 'sample_predictions_grid.png', dpi=160)
plt.show()
"""
    ),
    md(
        """## 12. Contrato de integracao com backend/Raspberry

O Raspberry Pi pode capturar uma imagem, rodar o modelo treinado e enviar um payload para o backend.
"""
    ),
    code(
        """example_backend_payload = {
    'deviceId': 'ASTRO-RPI-CAM-001',
    'community': 'Comunidade Aurora',
    'visualClass': 'residuo superficial',
    'pollutionClass': pollution_df.iloc[0]['predicted_class'] if 'pollution_df' in globals() else 'Plastic_Water_Bottle',
    'pollutionScore': float(pollution_df.iloc[0]['visual_pollution_score']) if 'pollution_df' in globals() else 82.0,
    'confidence': float(pollution_df.iloc[0]['confidence']) if 'pollution_df' in globals() else 0.91,
    'model': best_classification_model if 'best_classification_model' in globals() else 'yolov8n-cls',
    'source': 'raspberry-pi-camera',
}

print(json.dumps(example_backend_payload, indent=2, ensure_ascii=False))
"""
    ),
    md(
        """## Como explicar no PDF/video

> A visao computacional do AstroWater AI usa deep learning para classificar residuos visuais encontrados em aguas superficiais, como sacolas plasticas, canudos, garrafas, folhas e outros materiais. O modelo gera um indice visual de poluicao, combinado com sensores fisico-quimicos simulados no ESP32 e com o modelo tabular de potabilidade.

Limite tecnico:

> Este dataset publico e de classificacao de imagem. Para deteccao com caixas delimitadoras, seria necessario anotar bounding boxes manualmente ou usar outro dataset ja anotado.

Limite etico:

> O indice visual de poluicao nao substitui analise laboratorial. Ele serve como triagem remota para priorizar coleta, alerta e resposta operacional.
"""
    ),
]

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {
            "codemirror_mode": {"name": "ipython", "version": 3},
            "file_extension": ".py",
            "mimetype": "text/x-python",
            "name": "python",
            "nbconvert_exporter": "python",
            "pygments_lexer": "ipython3",
            "version": "3.12",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

Path("deep-learning/surface_water_waste_detection.ipynb").write_text(
    json.dumps(notebook, indent=1, ensure_ascii=False),
    encoding="utf-8",
)
print("classification notebook rebuilt")
