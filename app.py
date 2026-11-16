import os
import sqlite3
import csv
import io
from datetime import datetime
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for, send_file
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("ECOSAVE_SECRET_KEY") or os.urandom(32)
app.config["DATABASE"] = os.path.join(os.path.dirname(__file__), "ecosave.db")
# Demonstration assumption only; this is not presented as an official current India grid factor.
app.config["DEFAULT_EMISSION_FACTOR"] = 0.82

POINTS_BY_DIFFICULTY = {
    "Easy": 20,
    "Moderate": 35,
    "High": 50,
}


def get_db_connection():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            preferred_unit TEXT DEFAULT 'kWh',
            is_demo INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS consumption_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            record_month INTEGER NOT NULL,
            record_year INTEGER NOT NULL,
            consumption_kwh REAL NOT NULL,
            bill_inr REAL,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, record_month, record_year)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL,
            why_important TEXT NOT NULL,
            potential_savings_kwh REAL NOT NULL,
            carbon_reduction_kg REAL NOT NULL,
            category TEXT NOT NULL,
            difficulty TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            recommendation_id INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            energy_saving_kwh REAL DEFAULT 0,
            saving_type TEXT NOT NULL DEFAULT 'user_reported',
            note TEXT,
            completed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, recommendation_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            UNIQUE(user_id, key)
        )
        """
    )

    migrate_schema(conn)
    seed_recommendations(conn)
    conn.commit()
    conn.close()


def migrate_schema(conn):
    user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "is_demo" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN is_demo INTEGER NOT NULL DEFAULT 0")

    recommendation_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(user_recommendations)")
    }
    if "saving_type" not in recommendation_columns:
        conn.execute(
            "ALTER TABLE user_recommendations ADD COLUMN saving_type TEXT NOT NULL DEFAULT 'user_reported'"
        )


def seed_recommendations(conn):
    recommendations = [
        {
            "title": "Switch off lights when leaving rooms",
            "description": "Turn off lights and fans when rooms are vacant to reduce unnecessary usage.",
            "why_important": "Idle lighting and fan usage is a common source of wasted electricity in homes and hostels.",
            "potential_savings_kwh": 12.0,
            "carbon_reduction_kg": 9.84,
            "category": "Lighting",
            "difficulty": "Easy",
        },
        {
            "title": "Use LED bulbs instead of conventional lamps",
            "description": "Replace older incandescent or CFL bulbs with energy-efficient LEDs.",
            "why_important": "LED lamps reduce electricity use while providing the same or better brightness.",
            "potential_savings_kwh": 18.5,
            "carbon_reduction_kg": 15.17,
            "category": "Lighting",
            "difficulty": "Moderate",
        },
        {
            "title": "Set AC temperature to a balanced level",
            "description": "Keep your air conditioner at 24-26°C and use timers or eco mode when available.",
            "why_important": "Lower set temperatures significantly increase cooling power consumption.",
            "potential_savings_kwh": 25.0,
            "carbon_reduction_kg": 20.5,
            "category": "Cooling",
            "difficulty": "Moderate",
        },
        {
            "title": "Avoid standby power drains",
            "description": "Switch off televisions, chargers, and other electronics completely when not in use.",
            "why_important": "Standby loads are often ignored but collectively add to monthly consumption.",
            "potential_savings_kwh": 10.0,
            "carbon_reduction_kg": 8.2,
            "category": "Appliances",
            "difficulty": "Easy",
        },
        {
            "title": "Use natural daylight during the day",
            "description": "Open curtains and work near windows to reduce daytime artificial lighting.",
            "why_important": "Natural light reduces electricity demand during daylight hours.",
            "potential_savings_kwh": 9.0,
            "carbon_reduction_kg": 7.38,
            "category": "General electricity usage",
            "difficulty": "Easy",
        },
        {
            "title": "Use energy-efficient appliances",
            "description": "Prioritize appliances with higher energy ratings when replacing old equipment.",
            "why_important": "Modern efficient appliances use less electricity for the same output.",
            "potential_savings_kwh": 22.0,
            "carbon_reduction_kg": 18.04,
            "category": "Appliances",
            "difficulty": "High",
        },
        {
            "title": "Reduce water-heater usage",
            "description": "Take shorter showers and use water heaters more selectively.",
            "why_important": "Water heating can account for a large share of home electricity use.",
            "potential_savings_kwh": 15.0,
            "carbon_reduction_kg": 12.3,
            "category": "General electricity usage",
            "difficulty": "Moderate",
        },
        {
            "title": "Clean AC filters and appliances regularly",
            "description": "Maintain cooling and other equipment by cleaning or servicing them regularly.",
            "why_important": "Clean equipment runs more efficiently and consumes less power.",
            "potential_savings_kwh": 14.0,
            "carbon_reduction_kg": 11.48,
            "category": "Cooling",
            "difficulty": "Moderate",
        },
        {
            "title": "Run full laundry loads",
            "description": "Wait for a full load and use an energy-efficient wash setting when suitable.",
            "why_important": "Fewer wash cycles reduce electricity and hot-water demand.",
            "potential_savings_kwh": 8.0,
            "carbon_reduction_kg": round(8.0 * app.config["DEFAULT_EMISSION_FACTOR"], 2),
            "category": "Appliances",
            "difficulty": "Easy",
        },
        {
            "title": "Unplug chargers when not in use",
            "description": "Disconnect chargers and small electronics after charging is complete.",
            "why_important": "This reduces avoidable standby use and reinforces efficient routines.",
            "potential_savings_kwh": 5.0,
            "carbon_reduction_kg": round(5.0 * app.config["DEFAULT_EMISSION_FACTOR"], 2),
            "category": "General electricity usage",
            "difficulty": "Easy",
        },
    ]

    for rec in recommendations:
        existing = conn.execute(
            "SELECT id FROM recommendations WHERE title = ?",
            (rec["title"],),
        ).fetchone()
        if not existing:
            conn.execute(
                """
                INSERT INTO recommendations (title, description, why_important, potential_savings_kwh, carbon_reduction_kg, category, difficulty)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec["title"],
                    rec["description"],
                    rec["why_important"],
                    rec["potential_savings_kwh"],
                    rec["carbon_reduction_kg"],
                    rec["category"],
                    rec["difficulty"],
                ),
            )


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def get_user_records(user_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM consumption_records WHERE user_id = ? ORDER BY record_year ASC, record_month ASC",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def get_consecutive_month_comparisons(records):
    comparisons = []
    for previous, current in zip(records, records[1:]):
        previous_period = previous["record_year"] * 12 + previous["record_month"]
        current_period = current["record_year"] * 12 + current["record_month"]
        if current_period - previous_period != 1:
            continue

        previous_value = float(previous["consumption_kwh"])
        current_value = float(current["consumption_kwh"])
        comparisons.append({
            "label": (
                f"{previous['record_month']:02d}/{previous['record_year']} to "
                f"{current['record_month']:02d}/{current['record_year']}"
            ),
            "previous_month": f"{previous['record_month']:02d}/{previous['record_year']}",
            "current_month": f"{current['record_month']:02d}/{current['record_year']}",
            "previous_kwh": previous_value,
            "current_kwh": current_value,
            "difference_kwh": round(previous_value - current_value, 2),
            "change_percent": round(
                ((current_value - previous_value) / previous_value) * 100, 2
            ) if previous_value else 0,
        })
    return comparisons


def get_user_setting(user_id, key, default=""):
    conn = get_db_connection()
    value = conn.execute(
        "SELECT value FROM settings WHERE user_id = ? AND key = ?",
        (user_id, key),
    ).fetchone()
    conn.close()
    return value["value"] if value else default


def set_user_setting(user_id, key, value):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO settings (user_id, key, value) VALUES (?, ?, ?) ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
        (user_id, key, str(value)),
    )
    conn.commit()
    conn.close()


def get_user_emission_factor(user_id):
    value = get_user_setting(user_id, "emission_factor_kg_per_kwh", app.config["DEFAULT_EMISSION_FACTOR"])
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(app.config["DEFAULT_EMISSION_FACTOR"])


def get_recommendation_status(user_id, recommendation_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM user_recommendations WHERE user_id = ? AND recommendation_id = ?",
        (user_id, recommendation_id),
    ).fetchone()
    conn.close()
    return row


def get_dashboard_metrics(user_id):
    records = get_user_records(user_id)
    if not records:
        return {
            "current_total": 0,
            "previous_total": 0,
            "consumption_saved_kwh": 0,
            "emissions_kg": 0,
            "emissions_avoided_kg": 0,
            "completed_actions": 0,
            "eco_points": 0,
            "current_month_label": "No data",
            "previous_month_label": "No data",
            "monthly_change_percent": 0,
            "comparison_available": False,
            "records": [],
            "month_labels": [],
            "month_values": [],
        }

    current_record = records[-1]
    previous_record = records[-2] if len(records) > 1 else None
    current_total = float(current_record["consumption_kwh"])
    previous_total = float(previous_record["consumption_kwh"]) if previous_record else 0.0
    comparisons = get_consecutive_month_comparisons(records)
    latest_label = f"{current_record['record_month']:02d}/{current_record['record_year']}"
    latest_comparison = (
        comparisons[-1]
        if comparisons and comparisons[-1]["current_month"] == latest_label
        else None
    )
    consumption_saved_kwh = (
        max(0.0, latest_comparison["difference_kwh"])
        if latest_comparison else 0.0
    )
    factor = get_user_emission_factor(user_id)
    emissions_kg = round(current_total * factor, 2)
    emissions_avoided_kg = round(consumption_saved_kwh * factor, 2)

    conn = get_db_connection()
    completed_actions = conn.execute(
        "SELECT COUNT(*) AS count FROM user_recommendations WHERE user_id = ? AND status = 'completed'",
        (user_id,),
    ).fetchone()["count"]
    eco_points = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN ur.status = 'completed' THEN r.potential_savings_kwh * 0.0 + (CASE r.difficulty WHEN 'Easy' THEN 20 WHEN 'Moderate' THEN 35 WHEN 'High' THEN 50 ELSE 0 END) ELSE 0 END), 0) AS total FROM user_recommendations ur JOIN recommendations r ON r.id = ur.recommendation_id WHERE ur.user_id = ?",
        (user_id,),
    ).fetchone()["total"]
    conn.close()

    current_month_label = f"{current_record['record_month']:02d}/{current_record['record_year']}"
    previous_month_label = f"{previous_record['record_month']:02d}/{previous_record['record_year']}" if previous_record else "N/A"

    monthly_change_percent = 0.0
    if latest_comparison:
        monthly_change_percent = latest_comparison["change_percent"]

    month_labels = [f"{record['record_month']:02d}/{record['record_year']}" for record in records]
    month_values = [float(record["consumption_kwh"]) for record in records]

    return {
        "current_total": round(current_total, 2),
        "previous_total": round(previous_total, 2),
        "consumption_saved_kwh": round(consumption_saved_kwh, 2),
        "emissions_kg": emissions_kg,
        "emissions_avoided_kg": emissions_avoided_kg,
        "completed_actions": completed_actions,
        "eco_points": int(eco_points),
        "current_month_label": current_month_label,
        "previous_month_label": previous_month_label,
        "monthly_change_percent": round(monthly_change_percent, 2),
        "comparison_available": bool(latest_comparison),
        "records": records,
        "month_labels": month_labels,
        "month_values": month_values,
    }


def get_analysis_data(user_id):
    records = get_user_records(user_id)
    if not records:
        return {
            "average": 0,
            "highest": 0,
            "lowest": 0,
            "total": 0,
            "trend": "Add consumption records to generate analysis.",
            "high_consumption_months": [],
            "month_labels": [],
            "month_values": [],
            "highest_month": "—",
            "lowest_month": "—",
            "comparisons": [],
        }

    values = [float(record["consumption_kwh"]) for record in records]
    average = sum(values) / len(values)
    highest = max(values)
    lowest = min(values)
    totals = sum(values)

    comparisons = get_consecutive_month_comparisons(records)
    latest_label = f"{records[-1]['record_month']:02d}/{records[-1]['record_year']}"
    latest_comparison = (
        comparisons[-1]
        if comparisons and comparisons[-1]["current_month"] == latest_label
        else None
    )
    trend = "Add consecutive monthly records to compare usage."
    if latest_comparison:
        if latest_comparison["difference_kwh"] < 0:
            trend = (
                f"Consumption increased by {abs(latest_comparison['change_percent'])}% "
                f"({abs(latest_comparison['difference_kwh'])} kWh) from the previous month."
            )
        elif latest_comparison["difference_kwh"] > 0:
            trend = (
                f"Consumption reduced by {latest_comparison['change_percent'] * -1}% "
                f"({latest_comparison['difference_kwh']} kWh) from the previous month."
            )
        else:
            trend = "Consumption was unchanged from the previous month."

    high_consumption_months = []
    for record in records:
        if float(record["consumption_kwh"]) >= average:
            high_consumption_months.append({
                "label": f"{record['record_month']:02d}/{record['record_year']}",
                "value": float(record["consumption_kwh"]),
            })

    month_labels = [f"{record['record_month']:02d}/{record['record_year']}" for record in records]
    month_values = [float(record["consumption_kwh"]) for record in records]
    highest_record = max(records, key=lambda record: float(record["consumption_kwh"]))
    lowest_record = min(records, key=lambda record: float(record["consumption_kwh"]))

    return {
        "average": round(average, 2),
        "highest": round(highest, 2),
        "lowest": round(lowest, 2),
        "total": round(totals, 2),
        "trend": trend,
        "high_consumption_months": high_consumption_months,
        "month_labels": month_labels,
        "month_values": month_values,
        "highest_month": f"{highest_record['record_month']:02d}/{highest_record['record_year']}",
        "lowest_month": f"{lowest_record['record_month']:02d}/{lowest_record['record_year']}",
        "comparisons": comparisons,
    }


def get_user_points_details(user_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN ur.status = 'completed' THEN CASE r.difficulty WHEN 'Easy' THEN 20 WHEN 'Moderate' THEN 35 WHEN 'High' THEN 50 ELSE 0 END ELSE 0 END), 0) AS total_points, COUNT(CASE WHEN ur.status = 'completed' THEN 1 END) AS completed_count FROM user_recommendations ur JOIN recommendations r ON r.id = ur.recommendation_id WHERE ur.user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    total_points = int(row["total_points"])
    completed_count = int(row["completed_count"])

    if total_points < 50:
        level = "Beginner"
        next_level = 50
        progress = min(100, (total_points / 50) * 100)
    elif total_points < 150:
        level = "Energy Saver"
        next_level = 150
        progress = min(100, ((total_points - 50) / 100) * 100)
    else:
        level = "Eco Champion"
        next_level = None
        progress = 100

    return {
        "total_points": total_points,
        "completed_count": completed_count,
        "level": level,
        "next_level": next_level,
        "progress": round(progress, 1),
        "beginner_earned": total_points > 0,
        "energy_saver_earned": total_points >= 50,
        "eco_champion_earned": total_points >= 150,
    }


@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not name or not email or not password:
            flash("Please fill in all fields.", "danger")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "danger")
            return redirect(url_for("register"))

        conn = get_db_connection()
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone()

        if existing:
            conn.close()
            flash("A user with that username or email already exists.", "danger")
            return redirect(url_for("register"))

        conn.execute(
            "INSERT INTO users (username, name, email, password_hash) VALUES (?, ?, ?, ?)",
            (username, name, email, generate_password_hash(password)),
        )
        conn.commit()
        conn.close()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username_or_email = request.form.get("username_or_email", "").strip()
        password = request.form.get("password", "")

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ? OR email = ?",
            (username_or_email, username_or_email),
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["is_demo"] = bool(user["is_demo"])
            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username/email or password.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    metrics = get_dashboard_metrics(user["id"])
    analysis_data = get_analysis_data(user["id"])
    recommendations = get_recommendations_for_display(user["id"])
    factor = get_user_emission_factor(user["id"])
    return render_template(
        "dashboard.html",
        user=user,
        metrics=metrics,
        analysis_data=analysis_data,
        recommendations=recommendations,
        factor=factor,
    )


@app.route("/consumption", methods=["GET", "POST"])
@login_required
def consumption():
    user = get_current_user()
    records = get_user_records(user["id"])

    if request.method == "POST":
        month = request.form.get("record_month")
        year = request.form.get("record_year")
        consumption = request.form.get("consumption_kwh")
        bill_inr = request.form.get("bill_inr")
        notes = request.form.get("notes", "").strip()

        try:
            month_int = int(month)
            year_int = int(year)
            consumption_float = float(consumption)
            bill_value = float(bill_inr) if bill_inr else None
        except (TypeError, ValueError):
            flash("Please enter valid numeric values.", "danger")
            return redirect(url_for("consumption"))

        if month_int < 1 or month_int > 12 or consumption_float <= 0:
            flash("Please provide a valid month and a positive consumption value.", "danger")
            return redirect(url_for("consumption"))

        conn = get_db_connection()
        existing = conn.execute(
            "SELECT id FROM consumption_records WHERE user_id = ? AND record_month = ? AND record_year = ?",
            (user["id"], month_int, year_int),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE consumption_records SET consumption_kwh = ?, bill_inr = ?, notes = ?, updated_at = ? WHERE id = ?",
                (consumption_float, bill_value, notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), existing["id"]),
            )
            flash("Consumption record updated successfully.", "success")
        else:
            conn.execute(
                "INSERT INTO consumption_records (user_id, record_month, record_year, consumption_kwh, bill_inr, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (user["id"], month_int, year_int, consumption_float, bill_value, notes),
            )
            flash("Consumption record added successfully.", "success")

        conn.commit()
        conn.close()
        return redirect(url_for("consumption"))

    return render_template("consumption.html", user=user, records=records)


@app.route("/consumption/<int:record_id>/delete", methods=["POST"])
@login_required
def delete_consumption(record_id):
    user = get_current_user()
    conn = get_db_connection()
    conn.execute(
        "DELETE FROM consumption_records WHERE id = ? AND user_id = ?",
        (record_id, user["id"]),
    )
    conn.commit()
    conn.close()
    flash("Consumption record deleted.", "success")
    return redirect(url_for("consumption"))


@app.route("/analysis")
@login_required
def analysis():
    user = get_current_user()
    data = get_analysis_data(user["id"])
    factor = get_user_emission_factor(user["id"])
    emission_values = [round(value * factor, 2) for value in data["month_values"]]
    return render_template(
        "analysis.html",
        user=user,
        data=data,
        factor=factor,
        emission_values=emission_values,
    )


@app.route("/recommendations")
@login_required
def recommendations():
    user = get_current_user()
    rows = get_recommendations_for_display(user["id"])
    return render_template("recommendations.html", user=user, recommendations=rows)


@app.route("/recommendations/<int:recommendation_id>/update", methods=["POST"])
@login_required
def update_recommendation(recommendation_id):
    user = get_current_user()
    status = request.form.get("status", "pending")
    saving_type = request.form.get("saving_type", "user_reported")
    note = request.form.get("note", "").strip()
    energy_saving = request.form.get("energy_saving_kwh", "0").strip()

    if status not in {"pending", "in_progress", "completed"}:
        flash("Choose a valid recommendation status.", "danger")
        return redirect(url_for("recommendations"))
    if saving_type not in {"user_reported", "estimated"}:
        flash("Choose a valid savings classification.", "danger")
        return redirect(url_for("recommendations"))

    try:
        energy_saving_value = float(energy_saving) if energy_saving else 0.0
        if energy_saving_value < 0:
            raise ValueError
    except ValueError:
        flash("Savings must be a non-negative number of kWh.", "danger")
        return redirect(url_for("recommendations"))

    conn = get_db_connection()
    recommendation = conn.execute(
        "SELECT id FROM recommendations WHERE id = ?",
        (recommendation_id,),
    ).fetchone()
    if not recommendation:
        conn.close()
        flash("Recommendation not found.", "danger")
        return redirect(url_for("recommendations"))

    existing = conn.execute(
        "SELECT * FROM user_recommendations WHERE user_id = ? AND recommendation_id = ?",
        (user["id"], recommendation_id),
    ).fetchone()
    completed_at = None
    if status == "completed":
        completed_at = (
            existing["completed_at"]
            if existing and existing["status"] == "completed" and existing["completed_at"]
            else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    if existing:
        conn.execute(
            "UPDATE user_recommendations SET status = ?, energy_saving_kwh = ?, saving_type = ?, note = ?, updated_at = ?, completed_at = ? WHERE id = ?",
            (
                status,
                energy_saving_value,
                saving_type,
                note,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                completed_at,
                existing["id"],
            ),
        )
    else:
        conn.execute(
            "INSERT INTO user_recommendations (user_id, recommendation_id, status, energy_saving_kwh, saving_type, note, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user["id"],
                recommendation_id,
                status,
                energy_saving_value,
                saving_type,
                note,
                completed_at,
            ),
        )
    conn.commit()
    conn.close()
    flash("Recommendation status updated.", "success")
    return redirect(url_for("recommendations"))


@app.route("/savings")
@login_required
def savings():
    user = get_current_user()
    conn = get_db_connection()
    completed_rows = conn.execute(
        "SELECT ur.*, r.title, r.category, r.difficulty, r.potential_savings_kwh FROM user_recommendations ur JOIN recommendations r ON r.id = ur.recommendation_id WHERE ur.user_id = ? AND ur.status = 'completed' ORDER BY ur.completed_at DESC",
        (user["id"],),
    ).fetchall()
    total_reported = round(sum(
        float(row["energy_saving_kwh"])
        for row in completed_rows if row["saving_type"] == "user_reported"
    ), 2)
    total_estimated = round(sum(
        float(row["energy_saving_kwh"])
        for row in completed_rows if row["saving_type"] == "estimated"
    ), 2)
    potential_savings = round(sum(float(row["potential_savings_kwh"]) for row in get_recommendations_for_display(user["id"])), 2)
    factor = get_user_emission_factor(user["id"])
    emissions_avoided = round(total_reported * factor, 2)
    estimated_emissions_avoided = round(total_estimated * factor, 2)

    records = get_user_records(user["id"])
    comparisons = get_consecutive_month_comparisons(records)
    measured_savings = round(sum(
        max(0, comparison["difference_kwh"]) for comparison in comparisons
    ), 2)
    measured_emissions = round(measured_savings * factor, 2)
    conn.close()
    return render_template(
        "savings.html",
        user=user,
        completed_rows=completed_rows,
        potential_savings=potential_savings,
        total_reported=total_reported,
        total_estimated=total_estimated,
        emissions_avoided=emissions_avoided,
        estimated_emissions_avoided=estimated_emissions_avoided,
        measured_savings=measured_savings,
        measured_emissions=measured_emissions,
        monthly_savings=comparisons,
    )


def get_completed_action_rows(user_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT ur.*, r.title, r.category, r.difficulty, r.potential_savings_kwh FROM user_recommendations ur JOIN recommendations r ON r.id = ur.recommendation_id WHERE ur.user_id = ? AND ur.status = 'completed' ORDER BY ur.completed_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


@app.route("/carbon")
@login_required
def carbon():
    user = get_current_user()
    factor = get_user_emission_factor(user["id"])
    records = get_user_records(user["id"])
    monthly_emissions = [
        {
            "label": f"{record['record_month']:02d}/{record['record_year']}",
            "consumption_kwh": float(record["consumption_kwh"]),
            "emissions_kg": round(float(record["consumption_kwh"]) * factor, 2),
        }
        for record in records
    ]
    recent_records = records[-12:]
    recent_comparisons = get_consecutive_month_comparisons(recent_records)
    annual_emissions = None
    if len(recent_records) == 12 and len(recent_comparisons) == 11:
        annual_emissions = round(
            sum(float(record["consumption_kwh"]) * factor for record in recent_records),
            2,
        )
    comparisons = get_consecutive_month_comparisons(records)
    measured_reduction_kwh = sum(
        max(0, item["difference_kwh"]) for item in comparisons
    )
    reported_savings_rows = get_completed_action_rows(user["id"])
    reported_savings_kwh = sum(
        float(row["energy_saving_kwh"])
        for row in reported_savings_rows if row["saving_type"] == "user_reported"
    )
    estimated_action_savings_kwh = sum(
        float(row["energy_saving_kwh"])
        for row in reported_savings_rows if row["saving_type"] == "estimated"
    )
    return render_template(
        "carbon.html",
        user=user,
        factor=factor,
        monthly_emissions=monthly_emissions,
        annual_emissions=annual_emissions,
        estimated_avoided_kg=round(measured_reduction_kwh * factor, 2),
        reported_avoided_kg=round(reported_savings_kwh * factor, 2),
        estimated_action_avoided_kg=round(estimated_action_savings_kwh * factor, 2),
        factor_source=get_user_setting(
            user["id"], "emission_factor_source",
            "Configurable demonstration placeholder; not an official current factor",
        ),
        factor_year=get_user_setting(user["id"], "emission_factor_year", "2026 demo assumption"),
    )


@app.route("/rewards")
@login_required
def rewards():
    user = get_current_user()
    details = get_user_points_details(user["id"])
    return render_template("rewards.html", user=user, details=details)


@app.route("/reports")
@login_required
def reports():
    user = get_current_user()
    records = get_user_records(user["id"])
    conn = get_db_connection()
    completed_rows = conn.execute(
        "SELECT ur.*, r.title, r.category FROM user_recommendations ur JOIN recommendations r ON r.id = ur.recommendation_id WHERE ur.user_id = ? AND ur.status = 'completed' ORDER BY ur.completed_at DESC",
        (user["id"],),
    ).fetchall()
    conn.close()
    factor = get_user_emission_factor(user["id"])
    comparisons = get_consecutive_month_comparisons(records)
    comparisons_by_month = {
        comparison["current_month"]: comparison for comparison in comparisons
    }
    report_rows = [
        dict(record) | {
            "emissions_kg": round(float(record["consumption_kwh"]) * factor, 2),
            "measured_reduction_kwh": max(
                0,
                comparisons_by_month.get(
                    f"{record['record_month']:02d}/{record['record_year']}", {}
                ).get("difference_kwh", 0),
            ),
        }
        for record in records
    ]
    summary = {
        "total_consumption": round(sum(float(record["consumption_kwh"]) for record in records), 2),
        "total_emissions": round(sum(row["emissions_kg"] for row in report_rows), 2),
        "completed_actions": len(completed_rows),
        "reported_savings": round(sum(
            float(row["energy_saving_kwh"])
            for row in completed_rows if row["saving_type"] == "user_reported"
        ), 2),
        "estimated_savings": round(sum(
            float(row["energy_saving_kwh"])
            for row in completed_rows if row["saving_type"] == "estimated"
        ), 2),
        "measured_reduction": round(sum(
            max(0, item["difference_kwh"]) for item in comparisons
        ), 2),
    }
    return render_template(
        "reports.html",
        user=user,
        records=report_rows,
        completed_rows=completed_rows,
        summary=summary,
        factor=factor,
    )


@app.route("/reports/download")
@login_required
def download_reports_csv():
    user = get_current_user()
    records = get_user_records(user["id"])
    factor = get_user_emission_factor(user["id"])
    conn = get_db_connection()
    actions = conn.execute(
        "SELECT ur.*, r.title FROM user_recommendations ur JOIN recommendations r ON r.id = ur.recommendation_id WHERE ur.user_id = ? AND ur.status = 'completed' ORDER BY ur.completed_at",
        (user["id"],),
    ).fetchall()
    conn.close()
    comparisons_by_month = {
        comparison["current_month"]: comparison
        for comparison in get_consecutive_month_comparisons(records)
    }

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "record_type", "month", "year", "consumption_kwh", "emissions_kg_co2e",
        "bill_inr", "action", "completion_date", "saving_kwh", "saving_classification",
        "estimated_co2_avoided_kg", "notes",
    ])
    for record in records:
        month_label = f"{record['record_month']:02d}/{record['record_year']}"
        comparison = comparisons_by_month.get(month_label, {})
        measured_reduction = max(0, comparison.get("difference_kwh", 0))
        writer.writerow([
            "consumption",
            record["record_month"],
            record["record_year"],
            record["consumption_kwh"],
            round(float(record["consumption_kwh"]) * factor, 2),
            record["bill_inr"],
            "",
            "",
            measured_reduction if measured_reduction else "",
            "measured_consumption_comparison" if measured_reduction else "",
            round(measured_reduction * factor, 2) if measured_reduction else "",
            record["notes"],
        ])
    for action in actions:
        writer.writerow([
            "completed_action",
            "",
            "",
            "",
            "",
            "",
            action["title"],
            action["completed_at"],
            action["energy_saving_kwh"],
            action["saving_type"],
            round(float(action["energy_saving_kwh"]) * factor, 2),
            action["note"],
        ])

    output = buffer.getvalue().encode("utf-8")
    buffer.close()
    return send_file(
        io.BytesIO(output),
        mimetype="text/csv",
        as_attachment=True,
        download_name="ecosave_consumption_history.csv",
    )


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = get_current_user()
    if request.method == "POST":
        update_name = request.form.get("name", "").strip()
        new_password = request.form.get("new_password", "").strip()
        preferred_unit = request.form.get("preferred_unit", "kWh")
        emission_factor = request.form.get("emission_factor", "").strip()

        if update_name:
            conn = get_db_connection()
            conn.execute("UPDATE users SET name = ? WHERE id = ?", (update_name, user["id"]))
            conn.commit()
            conn.close()
            flash("Profile name updated.", "success")

        if new_password:
            if len(new_password) < 6:
                flash("New password must be at least 6 characters long.", "danger")
            else:
                conn = get_db_connection()
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new_password), user["id"]),
                )
                conn.commit()
                conn.close()
                flash("Password updated successfully.", "success")

        if preferred_unit:
            set_user_setting(user["id"], "preferred_unit", preferred_unit)
            flash("Preferred unit updated.", "success")

        if emission_factor:
            try:
                factor_value = float(emission_factor)
                if factor_value <= 0:
                    raise ValueError
                set_user_setting(user["id"], "emission_factor_kg_per_kwh", factor_value)
                set_user_setting(
                    user["id"],
                    "emission_factor_source",
                    "User-configured value; source requires account-owner verification",
                )
                set_user_setting(user["id"], "emission_factor_year", "User configured")
                flash("Emission factor updated successfully.", "success")
            except ValueError:
                flash("Emission factor must be a positive number.", "danger")

        return redirect(url_for("profile"))

    current_factor = get_user_emission_factor(user["id"])
    preferred_unit = get_user_setting(user["id"], "preferred_unit", "kWh")
    factor_source = get_user_setting(
        user["id"],
        "emission_factor_source",
        "Configurable demonstration placeholder; not an official current factor",
    )
    factor_year = get_user_setting(
        user["id"], "emission_factor_year", "2026 demo assumption"
    )
    return render_template(
        "profile.html",
        user=user,
        current_factor=current_factor,
        preferred_unit=preferred_unit,
        factor_source=factor_source,
        factor_year=factor_year,
    )


@app.route("/settings")
@login_required
def settings():
    return redirect(url_for("profile"))


def get_recommendations_for_display(user_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT r.*, ur.status, ur.energy_saving_kwh, ur.note, ur.completed_at FROM recommendations r LEFT JOIN user_recommendations ur ON ur.recommendation_id = r.id AND ur.user_id = ? ORDER BY r.id",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="127.0.0.1", port=5000)
