from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from db import fetchall


@dataclass
class Product:
    code: str
    type: str
    size: Optional[str]
    style: Optional[str]
    sale_price: float
    cost_price: float
    description: str
    area_cm2: Optional[float]


OBJECTIVES = {"mas_piezas", "mayor_area", "mejor_margen"}


def load_products(include_prints: bool, include_frames: bool) -> List[Product]:
    clauses = []
    params: List = []

    if not include_prints:
        clauses.append("type NOT IN ('print')")
    if not include_frames:
        clauses.append("type NOT IN ('combo', 'frame')")

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

    products: List[Product] = []
    for row in rows:
        products.append(
            Product(
                code=row["code"],
                type=row["type"],
                size=row.get("size"),
                style=row.get("style"),
                sale_price=float(row["sale_price"] or 0),
                cost_price=float(row["cost_price"] or 0),
                description=row.get("description", ""),
                area_cm2=float(row["area_cm2"]) if row.get("area_cm2") is not None else None,
            )
        )
    return products


def compute_combos(
    products: List[Product],
    budget: float,
    objective: str,
    max_items: int,
    limit: int = 30,
) -> Dict[str, object]:
    combos: List[Dict] = []

    def backtrack(index: int, remaining_items: int, items: List[Dict], totals: Dict[str, float]) -> None:
        if items and totals["total_price"] <= budget:
            combos.append(
                {
                    "total_price": round(totals["total_price"], 2),
                    "total_cost": round(totals["total_cost"], 2),
                    "margin": round(totals["total_price"] - totals["total_cost"], 2),
                    "total_items": int(totals["total_items"]),
                    "total_area": round(totals["total_area"], 2) if totals["total_area"] is not None else None,
                    "items": [dict(item) for item in items],
                }
            )
            if len(combos) >= 200:
                return

        if remaining_items == 0 or index >= len(products):
            return

        product = products[index]
        max_qty = remaining_items
        if product.sale_price > 0:
            max_qty = min(remaining_items, int(budget // product.sale_price))
        if max_qty == 0:
            backtrack(index + 1, remaining_items, items, totals)
            return

        # Option without taking this product
        backtrack(index + 1, remaining_items, items, totals)

        for qty in range(1, max_qty + 1):
            new_total_price = totals["total_price"] + product.sale_price * qty
            if new_total_price > budget:
                break
            new_total_cost = totals["total_cost"] + product.cost_price * qty
            area_increment = (product.area_cm2 * qty) if product.area_cm2 is not None else 0.0
            new_total_area = (totals["total_area"] or 0.0) + area_increment
            new_items = items + [
                {
                    "product_code": product.code,
                    "name": product.description,
                    "size": product.size,
                    "style": product.style,
                    "qty": qty,
                    "unit_price": round(product.sale_price, 2),
                    "total_price_item": round(product.sale_price * qty, 2),
                }
            ]
            new_totals = {
                "total_price": new_total_price,
                "total_cost": new_total_cost,
                "total_items": totals["total_items"] + qty,
                "total_area": new_total_area,
            }
            backtrack(index + 1, remaining_items - qty, new_items, new_totals)

    backtrack(0, max_items, [], {"total_price": 0.0, "total_cost": 0.0, "total_items": 0, "total_area": 0.0})

    def sort_key(combo: Dict) -> tuple:
        total_area = combo.get("total_area") or 0.0
        margin = combo.get("margin") or 0.0
        total_items = combo.get("total_items") or 0
        total_price = combo.get("total_price") or 0.0
        if objective == "mayor_area":
            return (-total_area, -total_items, total_price)
        if objective == "mejor_margen":
            return (-margin, -total_items, total_price)
        # mas_piezas
        return (-total_items, -total_area, total_price)

    combos_sorted = sorted(combos, key=sort_key)

    # Deduplicate by signature (products and qty) to avoid repeats
    unique: Dict[str, Dict] = {}
    for combo in combos_sorted:
        signature = "|".join(
            sorted(f"{item['product_code']}:{item['qty']}" for item in combo["items"])
        )
        if signature not in unique:
            unique[signature] = combo
        if len(unique) >= limit:
            break

    final_combos: List[Dict] = []
    for idx, combo in enumerate(unique.values(), start=1):
        combo_id = f"C{idx}"
        combo["combo_id"] = combo_id
        final_combos.append(combo)

    reason = None
    if not final_combos:
        reason = "Presupuesto insuficiente o filtros sin productos disponibles"

    return {"combos": final_combos, "reason": reason}
