# Arquitectura

La ruta crítica es `PyAV → muestreo temporal → resize/ROI → MOG2 → YOLO → eventos → FFmpeg`.

- PyAV decodifica con timestamps reales, por lo que soporta VFR.
- El resize y el recorte ocurren antes del análisis. MOG2 y morfología son baratos y eliminan la mayoría de las muestras.
- YOLO es el cuello de botella dominante; solo recibe ROI con movimiento. CUDA se selecciona automáticamente.
- Cada análisis corre en un proceso `spawn` dedicado. Uvicorn conserva el event loop para HTTP/WebSocket.
- FFmpeg intenta `-c copy`; si el GOP/códec impide un tramo útil, recodifica solamente ese evento.

Los pesos de Ultralytics deben existir localmente para operación estrictamente offline. El valor predeterminado es `models/yolo11n.pt`; si no existe, el trabajo termina con un mensaje claro y no intenta descargarlo.
