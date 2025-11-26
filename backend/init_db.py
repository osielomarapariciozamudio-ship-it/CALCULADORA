from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

from db import DB_PATH, get_connection, get_setting

INCH_TO_CM = 2.54

PRINT_SIZES = [
    "4x6",
    "5x7",
    "6x8",
    "6x9",
    "8x10",
    "8x12",
    "8x16",
    "8x20",
    "8x24",
    "10x12",
    "11x14",
    "11x16",
    "12x16",
    "12x18",
    "12x24",
    "16x20",
    "16x24",
    "20x24",
    "20x30",
    "24x30",
    "24x36",
]

FRAME_MAP: Dict[str, List[str]] = {
    "A1": ["11x14", "16x20", "16x24", "20x24", "20x30", "24x30", "24x36"],
    "B2": ["8x10", "11x14", "11x16", "16x20", "16x24", "20x24", "20x30", "24x30", "24x36"],
    "C1": ["8x10", "8x12", "11x14", "11x16", "12x18", "16x20", "16x24", "20x24", "20x30"],
}


def parse_size_to_cm(size: str) -> Tuple[float, float, float, float]:
    width_in, height_in = [float(part) for part in size.lower().split("x")]
    width_cm = round(width_in * INCH_TO_CM, 2)
    height_cm = round(height_in * INCH_TO_CM, 2)
    area_cm2 = round(width_cm * height_cm, 2)
    area_in2 = round(width_in * height_in, 2)
    return width_cm, height_cm, area_cm2, area_in2


def create_tables() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS prints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                size TEXT UNIQUE,
                width_cm REAL,
                height_cm REAL,
                area_cm2 REAL,
                print_price REAL,
                cost_price REAL,
                has_frame_A1 INTEGER DEFAULT 0,
                has_frame_B2 INTEGER DEFAULT 0,
                has_frame_C1 INTEGER DEFAULT 0
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                style TEXT,
                size TEXT,
                frame_price REAL,
                cost_price REAL,
                color TEXT,
                UNIQUE(style, size)
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                type TEXT,
                size TEXT,
                style TEXT,
                sale_price REAL,
                cost_price REAL,
                description TEXT
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT
            );
            """
        )
        conn.commit()


def seed_data(verbose: bool = False) -> None:
    with get_connection() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM prints").fetchone()[0]
        if existing:
            if verbose:
                print(f"Database already populated with {existing} prints. Skipping seed.")
            return

        conn.executemany(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES (?, ?)
            """,
            [
                ("print_price_multiplier", "1.4"),
                ("print_price_min", "80.0"),
                ("frame_price_multiplier", "0.7"),
                ("frame_price_min", "120.0"),
                ("print_cost_ratio", "0.55"),
                ("frame_cost_ratio", "0.55"),
            ],
        )

        # Fetch settings for dynamic pricing
        settings = {}
        for key in [
            "print_price_multiplier",
            "print_price_min",
            "frame_price_multiplier",
            "frame_price_min",
            "print_cost_ratio",
            "frame_cost_ratio",
        ]:
            settings[key] = float(get_setting(key, conn))

        prints_rows = []
        frame_rows = []
        products_rows = []

        # Build prints and flag availability
        for size in PRINT_SIZES:
            width_cm, height_cm, area_cm2, area_in2 = parse_size_to_cm(size)
            print_price = round(max(settings["print_price_min"], area_in2 * settings["print_price_multiplier"]), 2)
            cost_price = round(print_price * settings["print_cost_ratio"], 2)
            has_frame_A1 = 1 if size in FRAME_MAP.get("A1", []) else 0
            has_frame_B2 = 1 if size in FRAME_MAP.get("B2", []) else 0
            has_frame_C1 = 1 if size in FRAME_MAP.get("C1", []) else 0
            prints_rows.append(
                (
                    size,
                    width_cm,
                    height_cm,
                    area_cm2,
                    print_price,
                    cost_price,
                    has_frame_A1,
                    has_frame_B2,
                    has_frame_C1,
                )
            )

        print_lookup = {row[0]: {"price": row[4], "cost": row[5]} for row in prints_rows}

        for style, sizes in FRAME_MAP.items():
            for size in sizes:
                _, _, _, area_in2 = parse_size_to_cm(size)
                frame_price = round(max(settings["frame_price_min"], area_in2 * settings["frame_price_multiplier"]), 2)
                frame_cost = round(frame_price * settings["frame_cost_ratio"], 2)
                frame_rows.append((style, size, frame_price, frame_cost, "nogal"))

        # Products: prints
        for size, _, _, _, print_price, cost_price, *_ in prints_rows:
            code = f"PRINT_{size}"
            products_rows.append((code, "print", size, None, print_price, cost_price, f"Impresion {size}"))

        # Products: frames and combos
        frame_lookup = {(style, size): {"price": price, "cost": cost} for style, size, price, cost, _ in frame_rows}
        for (style, size), info in frame_lookup.items():
            code = f"FRAME_{size}_{style}"
            products_rows.append((code, "frame", size, style, info["price"], info["cost"], f"Marco {style} para {size}"))

        for style, sizes in FRAME_MAP.items():
            for size in sizes:
                if size not in print_lookup:
                    continue
                combo_price = round(print_lookup[size]["price"] + frame_lookup[(style, size)]["price"], 2)
                combo_cost = round(print_lookup[size]["cost"] + frame_lookup[(style, size)]["cost"], 2)
                code = f"CUADRO_{size}_{style}"
                products_rows.append(
                    (
                        code,
                        "combo",
                        size,
                        style,
                        combo_price,
                        combo_cost,
                        f"Cuadro {size} con marco {style}",
                    )
                )

        conn.executemany(
            """
            INSERT OR IGNORE INTO prints (size, width_cm, height_cm, area_cm2, print_price, cost_price, has_frame_A1, has_frame_B2, has_frame_C1)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            prints_rows,
        )

        conn.executemany(
            """
            INSERT OR IGNORE INTO frames (style, size, frame_price, cost_price, color)
            VALUES (?, ?, ?, ?, ?)
            """,
            frame_rows,
        )

        conn.executemany(
            """
            INSERT OR IGNORE INTO products (code, type, size, style, sale_price, cost_price, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            products_rows,
        )

        conn.commit()
        if verbose:
            print(f"Seed complete: {len(prints_rows)} prints, {len(frame_rows)} frames, {len(products_rows)} products.")


def ensure_db(seed: bool = True, verbose: bool = False) -> None:
    create_tables()
    if seed:
        seed_data(verbose=verbose)


if __name__ == "__main__":
    ensure_db(seed=True, verbose=True)
    print(f"Database ready at {DB_PATH}")
