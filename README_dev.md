# Calculadora Cuadros - San Luis Pro (dev)

## Opinión rápida del estado actual
- El backend usa FastAPI con endpoints claros para productos, cálculo de combos y chat, lo que facilita extender lógica de precios o métricas.
- La base de datos SQLite se inicializa con `init_db.py`, así que levantar un entorno nuevo es sencillo siempre que se ejecute antes de probar.
- El frontend vive en `frontend/index.html` sin dependencias pesadas, ideal para iterar rápido en estilos o copiar la app a otro host.
- Sugerencia: agregar pruebas automatizadas o scripts de validación de datos ayudaría a detectar cambios en precios antes de subirlos.

## Requisitos rapidos
- Python 3.10+
- Dependencias: `pip install -r requirements.txt`
- Variable: `OPENROUTER_API_KEY` (opcional para probar chat real)

## Inicializar BD
```
cd backend
python init_db.py
```
Esto crea `data.db` con tablas prints/frames/products y datos de ejemplo.

## Correr el servidor
```
cd backend
uvicorn main:app --reload --port 8000
```
Abre `http://localhost:8000/` para ver la UI (calculadora izquierda, chat derecha).

## Endpoints
- `GET /api/products` (query opcional `type`, `size`).
- `POST /api/calc-combos` con JSON `{budget, objective, include_prints, include_frames, max_items}`.
- `POST /api/chat-combos` con `{user_message, calc_context, selected_combo_id?}`. Necesita `calc_context` de `calc-combos`.

## Notas
- Datos de precios son ejemplos generados por area; reemplaza en `backend/init_db.py` con tus precios reales antes de usar en produccion.
- El chat usa OpenRouter (`OPENROUTER_MODEL`, `OPENROUTER_HTTP_REFERER`, `OPENROUTER_X_TITLE` en `.env.example`). Sin API key devuelve un mensaje local de fallback.
- Maximo de piezas permitido en UI/endpoint es 10 por combo.
