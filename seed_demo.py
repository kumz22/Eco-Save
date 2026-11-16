"""Idempotently add a separate academic demonstration account to EcoSave."""

import calendar
from datetime import date, datetime

from werkzeug.security import generate_password_hash

from app import app, get_db_connection, init_db


DEMO_EMAIL = "demo@ecosave.local"
DEMO_USERNAME = "ecosave_demo"
DEMO_NAME = "EcoSave Demo User"
DEMO_PASSWORD = "EcoSave@123"
DEMO_FACTOR = 0.82

MONTHLY_CONSUMPTION_KWH = {
    1: 242,
    2: 225,
    3: 238,
    4: 276,
    5: 315,
    6: 342,
    7: 328,
    8: 301,
    9: 287,
    10: 264,
    11: 248,
    12: 232,
}

DEMO_ACTIONS = [
    ("Switch off lights when leaving rooms", "completed", 12.0, "user_reported", 10, "Lights and fans switched off when rooms are empty."),
    ("Use LED bulbs instead of conventional lamps", "completed", 18.5, "estimated", 9, "Estimated from replacing frequently used bulbs."),
    ("Set AC temperature to a balanced level", "completed", 15.0, "user_reported", 7, "AC timer and 24-26°C setting used during warmer evenings."),
    ("Avoid standby power drains", "completed", 8.0, "user_reported", 5, "Entertainment devices and chargers switched off at the power strip."),
    ("Use natural daylight during the day", "completed", 6.5, "estimated", 3, "Estimated saving from reducing daytime lighting."),
    ("Clean AC filters and appliances regularly", "completed", 7.0, "estimated", 4, "Estimated saving after cleaning the AC filter and checking airflow."),
    ("Use energy-efficient appliances", "in_progress", 0.0, "user_reported", 0, "Comparing appliance efficiency labels before replacement."),
    ("Run full laundry loads", "in_progress", 0.0, "user_reported", 0, "Trialling full-load wash cycles."),
    ("Reduce water-heater usage", "pending", 0.0, "user_reported", 0, ""),
    ("Unplug chargers when not in use", "pending", 0.0, "user_reported", 0, ""),
]


def month_for_offset(today, months_ago):
    month_index = today.year * 12 + today.month - 1 - months_ago
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    return year, month


def ensure_demo_user(conn):
    by_email = conn.execute("SELECT * FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone()
    by_username = conn.execute(
        "SELECT * FROM users WHERE username = ?", (DEMO_USERNAME,)
    ).fetchone()

    for existing in (by_email, by_username):
        if existing and not existing["is_demo"]:
            raise RuntimeError(
                "The requested demo email or username belongs to a non-demo account. "
                "No user data was changed; resolve that identity conflict manually."
            )

    if by_email and by_username and by_email["id"] != by_username["id"]:
        raise RuntimeError(
            "The demo email and username belong to different demo accounts. "
            "No user data was changed."
        )

    existing = by_email or by_username
    password_hash = generate_password_hash(DEMO_PASSWORD)
    if existing:
        conn.execute(
            "UPDATE users SET username = ?, name = ?, email = ?, password_hash = ?, is_demo = 1 WHERE id = ?",
            (DEMO_USERNAME, DEMO_NAME, DEMO_EMAIL, password_hash, existing["id"]),
        )
        return existing["id"]

    cursor = conn.execute(
        "INSERT INTO users (username, name, email, password_hash, is_demo) VALUES (?, ?, ?, ?, 1)",
        (DEMO_USERNAME, DEMO_NAME, DEMO_EMAIL, password_hash),
    )
    return cursor.lastrowid


def seed_consumption(conn, user_id):
    today = date.today()
    for months_ago in reversed(range(12)):
        year, month = month_for_offset(today, months_ago)
        consumption = MONTHLY_CONSUMPTION_KWH[month]
        bill = round(consumption * 7.25 + 135, 2)
        note = f"DEMO SIMULATED: seasonal household usage pattern for {calendar.month_name[month]}."
        conn.execute(
            """
            INSERT OR IGNORE INTO consumption_records
                (user_id, record_month, record_year, consumption_kwh, bill_inr, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, month, year, consumption, bill, note),
        )


def seed_actions(conn, user_id):
    now = date.today()
    for title, status, saving, saving_type, months_ago, note in DEMO_ACTIONS:
        recommendation = conn.execute(
            "SELECT id FROM recommendations WHERE title = ?", (title,)
        ).fetchone()
        if not recommendation:
            raise RuntimeError(f"Required recommendation is missing: {title}")

        completed_at = None
        if status == "completed":
            action_date = month_for_offset(now, months_ago)
            action_year, action_month = action_date
            action_day = min(12, calendar.monthrange(action_year, action_month)[1])
            completed_at = datetime(action_year, action_month, action_day, 10, 0).strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO user_recommendations
                (user_id, recommendation_id, status, energy_saving_kwh, saving_type, note, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                recommendation["id"],
                status,
                saving,
                saving_type,
                f"DEMO SIMULATED: {note}" if note else "DEMO SIMULATED: Action not started.",
                completed_at,
            ),
        )


def seed_settings(conn, user_id):
    demo_settings = [
        ("emission_factor_kg_per_kwh", str(DEMO_FACTOR)),
        (
            "emission_factor_source",
            "Demonstration assumption only; not a verified CEA or regional official factor",
        ),
        ("emission_factor_year", "2026 demo assumption"),
        ("preferred_unit", "kWh"),
    ]
    for key, value in demo_settings:
        conn.execute(
            "INSERT OR IGNORE INTO settings (user_id, key, value) VALUES (?, ?, ?)",
            (user_id, key, value),
        )


def main():
    app.config["DEFAULT_EMISSION_FACTOR"] = DEMO_FACTOR
    init_db()
    conn = get_db_connection()
    try:
        with conn:
            user_id = ensure_demo_user(conn)
            seed_consumption(conn, user_id)
            seed_actions(conn, user_id)
            seed_settings(conn, user_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("EcoSave demo data is ready.")
    print(f"Login email: {DEMO_EMAIL}")
    print(f"Login password: {DEMO_PASSWORD}")
    print("Seeded 12 simulated monthly records and a mix of recommendation statuses.")


if __name__ == "__main__":
    main()
