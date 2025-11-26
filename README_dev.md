# Calculadora Cuadros - San Luis Pro (dev)

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
