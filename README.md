# Vigía

Vigía es una aplicación web local para revisar grabaciones de cámaras de seguridad y extraer solamente los fragmentos donde aparecen personas u objetos en movimiento dentro de una o varias regiones de interés (ROI).

El video se procesa íntegramente en la computadora del usuario: no se envían imágenes ni grabaciones a servicios externos.

## Funciones principales

- Carga de videos MP4, MKV, AVI, MOV y TS.
- Selección visual de múltiples ROI sobre un frame del video.
- Vista previa de detección sobre los primeros segundos.
- Detección en cascada de movimiento y objetos.
- Seguimiento del progreso mediante WebSocket sin bloquear la interfaz.
- Padding y fusión automática de eventos cercanos.
- Clips individuales o video concatenado.
- Timeline interactiva y previsualización de cada evento.
- Exportación de resultados en CSV, JSON y ZIP.
- Cancelación de trabajos en curso.
- Ejecución local en CPU o GPU NVIDIA CUDA.

## Cómo funciona

```text
Video
  └─ PyAV: decodificación y timestamps reales, incluso en VFR
      └─ Muestreo temporal configurable, 3 fps por defecto
          └─ Resize y recorte de las ROI
              └─ MOG2 + morfología: filtro de movimiento económico
                  └─ YOLO11n: clasificación solo de candidatos
                      └─ Padding, duración mínima y fusión
                          └─ FFmpeg: clips, concatenado, CSV, JSON y ZIP
```

La inferencia de YOLO es el paso más costoso. Vigía evita ejecutarla sobre todos los frames: primero reduce resolución, muestrea el video y descarta mediante MOG2 las imágenes sin movimiento. Cada análisis corre en un proceso separado para mantener FastAPI y la interfaz responsivos.

## Requisitos

- Python 3.10–3.13; se recomienda Python 3.11.
- FFmpeg y ffprobe disponibles en `PATH`.
- Aproximadamente 1 GB libre para el entorno CPU, además del espacio requerido por videos y resultados.
- Pesos locales de YOLO11n.

Instalación de FFmpeg:

- Ubuntu/Debian: `sudo apt install ffmpeg`
- macOS: `brew install ffmpeg`
- Windows: `winget install Gyan.FFmpeg`

## Instalación local en CPU

```bash
git clone https://github.com/RodriCamio/Vigia.git
cd Vigia

python3.11 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements-cpu.txt
```

Descargue una vez los pesos oficiales y muévalos al directorio local de modelos:

```bash
python -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"
mv yolo11n.pt models/yolo11n.pt       # Windows: move yolo11n.pt models\yolo11n.pt
```

Durante el análisis, el pipeline exige que el modelo exista localmente y no intenta descargarlo.

## Ejecución

```bash
source .venv/bin/activate
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Abra [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Docker

Coloque `yolo11n.pt` en `models/` y ejecute:

```bash
docker compose up --build
```

La configuración incluida usa PyTorch CPU para máxima compatibilidad. El directorio `models/` se monta como volumen y los videos/resultados permanecen fuera de la imagen.

## Flujo de uso

1. Cargue una grabación y revise sus metadatos.
2. Dibuje una o varias ROI sobre el frame de referencia.
3. Ejecute la previsualización de 10 segundos.
4. Ajuste sensibilidad, clases, confianza, padding y modo de salida.
5. Inicie el análisis y siga progreso, ETA y eventos detectados.
6. Explore la timeline y descargue clips, CSV, JSON o ZIP.

### Calibración recomendada

- Comience con 3 fps, 640 px, confianza YOLO `0.4` y área mínima `300 px²`.
- Dibuje ROI ajustadas; menos fondo implica menos falsos candidatos y mayor velocidad.
- Si lluvia, sombras o insectos disparan demasiado movimiento, aumente el área mínima o el umbral.
- Si se pierden objetos pequeños o rápidos, aumente FPS o resolución; esto incrementa el costo.
- El modo rápido `stream-copy` corta cerca de keyframes. Active recodificación exacta cuando necesite precisión temporal mayor.

## Resultados

Cada trabajo crea bajo `outputs/`:

- `event_001.mp4`, `event_002.mp4`, etc.
- `video_recortado.mp4`, cuando se solicita concatenación.
- `eventos.csv` con inicio, fin, duración, clases y confianza.
- `metadata.json` con configuración, estadísticas y advertencias.
- `resultados.zip` para descargar todo junto.

Los videos, resultados, pesos y configuraciones locales están excluidos de Git y del contexto de Docker.

## Rendimiento y limitaciones

El rendimiento depende del códec, tamaño de las ROI, porcentaje de movimiento, almacenamiento y hardware. Como referencia orientativa, una GPU moderna puede superar 4–10× tiempo real y una CPU moderna de ocho o más núcleos alrededor de 1.5–4× con los valores predeterminados. No son garantías universales.

MOG2, morfología y YOLO reducen falsos positivos por sombras, lluvia e insectos, pero ninguna detección es perfecta. Los cambios fuertes de luminancia se registran y se ignoran como muestras. Videos dañados se procesan hasta el último frame válido.

El corte con `-c copy` es rápido pero depende de los keyframes del códec. Si falla o se solicita exactitud, Vigía recodifica únicamente el tramo afectado con H.264.

## Desarrollo y pruebas

```bash
source .venv/bin/activate
pytest -q
```

Las pruebas cubren padding/fusión de intervalos y exportación real con un video sintético generado por FFmpeg. La arquitectura detallada está en [docs/architecture.md](docs/architecture.md).

## Privacidad

No incluya grabaciones reales, resultados, modelos ni credenciales en commits. Consulte [SECURITY.md](SECURITY.md). El `.gitignore` y `.dockerignore` incluidos bloquean estos artefactos de forma predeterminada.

## Licencia

Este proyecto se distribuye bajo la licencia incluida en [LICENSE](LICENSE).
