# EcoSave

EcoSave is a local Flask and SQLite application for tracking household electricity use, understanding energy patterns, and encouraging practical carbon-reduction actions. It supports regular accounts and a separate, clearly identified academic demonstration account.

## Run on Windows

From PowerShell in the project directory:

```powershell
python -m pip install -r requirements.txt
python seed_demo.py
python app.py
```

Open `http://127.0.0.1:5000`.

For sessions that remain valid after restarting the app, set a persistent secret key before starting it:

```powershell
$env:ECOSAVE_SECRET_KEY = "<a-long-random-secret>"
python app.py
```

If unset, the app generates a temporary key at startup, so sessions expire when it restarts.

Optional virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python seed_demo.py
python app.py
```

## Demo account

- Email: `demo@ecosave.local`
- Password: `EcoSave@123`

The demo account is separate from regular accounts. Its seed script adds 12 simulated monthly consumption records, bills and notes, recommendation statuses, completed actions, savings classifications, and calculation settings. Consumption and action inserts are idempotent and do not delete or overwrite existing records. If the demo email or username is already owned by a non-demo account, the script stops without modifying that account.

All pages for this account display a demonstration notice. The monthly usage values are simulated (about 225–342 kWh) and represent seasonal variation; they are not utility-bill data.

## Carbon calculation assumptions

The app calculates estimated electricity emissions as:

`CO2 emissions (kg CO2e) = electricity use (kWh) x grid emission factor (kg CO2e/kWh)`

The demo account uses **0.82 kg CO2e/kWh**, explicitly configured as a **2026 demonstration assumption**, not an official or verified current India-specific factor. No exact official publication value has been verified for this demo configuration. Before using results for research or a final submission, select the appropriate CEA grid factor (or a suitable regional source), document its publication year and methodology, and update the value in Profile & Settings. All calculated emissions remain estimates.

## Savings definitions

- **Potential savings:** estimated opportunities from recommendations; not achieved savings.
- **User-reported savings:** energy values recorded for completed actions; not utility-meter measurements.
- **Estimated action savings:** action estimates entered separately from user-reported values.
- **Measured reduction:** a reduction between consecutive monthly consumption records. Carbon avoidance based on it is still an estimate using the configured grid factor.

Eco points are derived from a user's unique completed recommendation rows. Changing a status does not create an additional recommendation record or accumulate duplicate points.

## Features

- User registration/login with password hashing and per-user records
- Monthly consumption entry and history
- Dashboard KPIs, 12-month charts, and energy analysis
- Ten rule-based energy-saving recommendations
- Savings tracking with separate potential, reported, estimated, and measured values
- Configurable carbon calculator and monthly emissions
- Eco points, achievement levels, and badges
- Reports and CSV export for monthly consumption and completed actions
- Profile and application settings

## Stack

Python, Flask, SQLite, Jinja2, Bootstrap 5, JavaScript, and Chart.js. The application is intended for local academic demonstration and does not use a paid API or cloud database.
