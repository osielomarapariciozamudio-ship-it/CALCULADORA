from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, validator

from combos import OBJECTIVES, compute_combos, load_products
from db import fetchall, execute, get_setting  # Added execute, get_setting
from init_db import ensure_db

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# Env vars serve as defaults, but DB settings override or supplement
ENV_OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "moonshotai/kimi-k2")
OPENROUTER_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER")
OPENROUTER_X_TITLE = os.getenv("OPENROUTER_X_TITLE", "Calculadora Cuadros San Luis Pro")

app = FastAPI(title="Calculadora Cuadros San Luis Pro", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProductOut(BaseModel):
    code: str
    type: str
    size: Optional[str]
    style: Optional[str]
    sale_price: float
    cost_price: float | None = None
    description: str | None = None
    area_cm2: float | None = None


class CalcRequest(BaseModel):
    budget: float = Field(..., gt=0, description="Presupuesto en MXN")
    objective: str = Field("mas_piezas")
    include_prints: bool = True
    include_frames: bool = True
    max_items: int = Field(3, ge=1, le=10)

    @validator("objective")
    def validate_objective(cls, value: str) -> str:
        if value not in OBJECTIVES:
            raise ValueError(f"objective must be one of {OBJECTIVES}")
        return value


class CalcResponse(BaseModel):
    budget: float
    objective: str
    combos: List[Dict[str, Any]]
    reason: Optional[str] = None


class ChatRequest(BaseModel):
    user_message: str
    calc_context: Dict[str, Any]
    selected_combo_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str
    used_combo_ids: List[str]
    source: str


class ApiKeyRequest(BaseModel):
    api_key: str


@app.on_event("startup")
async def startup_event() -> None:
    ensure_db(seed=True, verbose=False)


@app.get("/", include_in_schema=False)
async def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)


@app.get("/api/products", response_model=List[ProductOut])
async def get_products(type: Optional[str] = Query(None), size: Optional[str] = Query(None)):
    clauses = []
    params: List[Any] = []
    if type:
        clauses.append("p.type = ?")
        params.append(type)
    if size:
        clauses.append("p.size = ?")
        params.append(size)
    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)

    rows = fetchall(
        f"""
        SELECT p.code, p.type, p.size, p.style, p.sale_price, p.cost_price, p.description, pr.area_cm2
        FROM products p
        LEFT JOIN prints pr ON pr.size = p.size
        {where}
        ORDER BY p.sale_price ASC
        """,
        params,
    )
    return [ProductOut(**row) for row in rows]


@app.post("/api/calc-combos", response_model=CalcResponse)
async def calc_combos(payload: CalcRequest):
    if not payload.include_prints and not payload.include_frames:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos impresiones o cuadros con marco")

    products = load_products(include_prints=payload.include_prints, include_frames=payload.include_frames)
    if not products:
        return CalcResponse(
            budget=payload.budget, objective=payload.objective, combos=[], reason="No hay productos con estos filtros"
        )

    computed = compute_combos(
        products=products,
        budget=payload.budget,
        objective=payload.objective,
        max_items=payload.max_items,
    )

    return CalcResponse(
        budget=payload.budget,
        objective=payload.objective,
        combos=computed["combos"],
        reason=computed["reason"],
    )


def summarize_combos(calc_context: Dict[str, Any], max_lines: int = 6) -> str:
    combos = calc_context.get("combos", []) or []
    lines: List[str] = []
    for combo in combos[:max_lines]:
        header = f"Combo {combo.get('combo_id', '?')}: ${combo.get('total_price', 0)} - piezas {combo.get('total_items', 0)}"
        parts = []
        for item in combo.get("items", []):
            label = f"{item.get('qty', 1)}x {item.get('name', '')} ({item.get('product_code')})"
            parts.append(label)
        lines.append(header + " | " + "; ".join(parts))
    if not lines:
        return "Sin combos disponibles."
    return "\n".join(lines)


def get_active_api_key() -> Optional[str]:
    # Prioritize DB setting, fallback to Env
    db_key = get_setting("openrouter_api_key")
    if db_key and db_key.strip():
        return db_key.strip()
    return ENV_OPENROUTER_API_KEY


def get_active_model() -> str:
    # Prioritize DB setting, fallback to Env, then default
    db_model = get_setting("openrouter_model")
    if db_model and db_model.strip():
        return db_model.strip()
    return OPENROUTER_MODEL


async def call_openrouter(
    user_message: str, calc_context: Dict[str, Any], selected_combo_id: Optional[str]
) -> ChatResponse:
    combos = calc_context.get("combos", []) or []
    if not combos:
        raise HTTPException(
            status_code=400, detail="Primero calcula opciones con presupuesto antes de usar el chat"
        )

    used_combo_ids = []
    if selected_combo_id:
        used_combo_ids.append(selected_combo_id)

    summary = summarize_combos(calc_context)
    
    # Fetch API Key dynamically
    api_key = get_active_api_key()
    # Fetch Model dynamically
    model = get_active_model()

    if not api_key:
        reply = (
            "⚠️ No hay API Key configurada. Ve a 'Configuración' y agrega tu llave de OpenRouter para activar el chat.\n\n"
            "Resumen local:\n" + summary
        )
        return ChatResponse(reply=reply, used_combo_ids=used_combo_ids, source="local-fallback")

    system_prompt = (
        "Eres un asistente experto en recomendaciones de venta de cuadros e impresiones. "
        "No inventas precios ni productos. Solo explicas y recomiendas entre las opciones calculadas. "
        "Usa lenguaje claro en espanol."
    )

    context_prompt = (
        f"Presupuesto: {calc_context.get('budget')} | Objetivo: {calc_context.get('objective')}\n" +
        "Opciones calculadas (no alteres precios ni cantidades):\n" + summary
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context_prompt},
        {"role": "user", "content": user_message},
    ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if OPENROUTER_HTTP_REFERER:
        headers["HTTP-Referer"] = OPENROUTER_HTTP_REFERER
    if OPENROUTER_X_TITLE:
        headers["X-Title"] = OPENROUTER_X_TITLE

    payload = {"model": model, "messages": messages}

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers
            )
            if resp.status_code == 401:
                 return ChatResponse(reply="❌ Error de autenticación: La API Key es inválida.", used_combo_ids=used_combo_ids, source="error")
            if resp.status_code == 402:
                 return ChatResponse(reply="❌ Error de Pago (402): Tu cuenta de OpenRouter no tiene créditos suficientes. Recarga saldo o cambia a un modelo gratuito en Configuración.", used_combo_ids=used_combo_ids, source="error")
            resp.raise_for_status()
            data = resp.json()
            reply_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return ChatResponse(reply=reply_text, used_combo_ids=used_combo_ids, source="openrouter")
    except httpx.HTTPError as exc:
        # Return error as chat message to avoid UI crash
        return ChatResponse(reply=f"❌ Error de conexión con IA: {str(exc)}", used_combo_ids=used_combo_ids, source="error")


@app.post("/api/chat-combos", response_model=ChatResponse)
async def chat_combos(payload: ChatRequest):
    return await call_openrouter(payload.user_message, payload.calc_context, payload.selected_combo_id)


# Settings Endpoints

class ModelRequest(BaseModel):
    model: str

@app.get("/api/settings/status")
async def get_settings_status():
    key = get_active_api_key()
    model = get_active_model()
    return {"has_api_key": bool(key), "current_model": model}


@app.post("/api/settings/apikey")
async def set_api_key(payload: ApiKeyRequest):
    try:
        execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("openrouter_api_key", payload.api_key))
        return {"status": "ok", "message": "API Key guardada correctamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/model")
async def set_model(payload: ModelRequest):
    try:
        execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("openrouter_model", payload.model))
        return {"status": "ok", "message": "Modelo actualizado correctamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/openrouter/models")
async def get_openrouter_models():
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://openrouter.ai/api/v1/models")
            resp.raise_for_status()
            data = resp.json().get("data", [])
            
            # Filter for FREE models (pricing = "0")
            free_models = []
            for m in data:
                pricing = m.get("pricing", {})
                # Check if strictly 0 (some might be string "0" or "0.0")
                p_prompt = float(pricing.get("prompt", 0))
                p_compl = float(pricing.get("completion", 0))
                
                if p_prompt == 0 and p_compl == 0:
                    free_models.append({
                        "id": m.get("id"),
                        "name": m.get("name", m.get("id")),
                        "context_length": m.get("context_length", 0)
                    })
            
            # Sort by name for easier reading
            free_models.sort(key=lambda x: x["name"])
            return free_models
    except Exception as e:
        # Fallback list if API fails
        return [
            {"id": "google/gemini-2.0-flash-exp:free", "name": "Google Gemini 2.0 Flash (Fallback)"},
            {"id": "meta-llama/llama-3-8b-instruct:free", "name": "Llama 3 8B (Fallback)"},
        ]


# Minimal health
@app.get("/api/health", include_in_schema=False)
async def health():
    return {"status": "ok"}


# Static assets
@app.get("/frontend/{path:path}", include_in_schema=False)
async def serve_static(path: str):
    target = FRONTEND_DIR / path
    if not target.exists():
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(target)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)