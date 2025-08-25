# app.py
import os
import datetime as dt
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template, send_file
from flask_cors import CORS
import sqlite3
import pandas as pd
import requests

# -----------------------------
# Config
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_DIR = BASE_DIR / "data"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "nutrition.db"

load_dotenv()

NUTRITIONIX_APP_ID = os.getenv("NUTRITIONIX_APP_ID", "YOUR_APP_ID_HERE")
NUTRITIONIX_API_KEY = os.getenv("NUTRITIONIX_API_KEY", "YOUR_API_KEY_HERE")

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# -----------------------------
# DB helpers
# -----------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT DEFAULT 'demo',
                log_date TEXT NOT NULL,
                food_name TEXT NOT NULL,
                quantity REAL DEFAULT 1.0,
                calories REAL DEFAULT 0,
                protein REAL DEFAULT 0,
                fat REAL DEFAULT 0,
                carbs REAL DEFAULT 0
            );
        """)
        conn.commit()

init_db()

def today_str():
    return dt.date.today().strftime("%Y-%m-%d")

def to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default

# -----------------------------
# Nutritionix API helpers
# -----------------------------
NUTRITIONIX_HEADERS = {
    "x-app-id": NUTRITIONIX_APP_ID,
    "x-app-key": NUTRITIONIX_API_KEY,
    "Content-Type": "application/json",
}

def nutritionix_instant_search(query: str, limit=5):
    url = "https://trackapi.nutritionix.com/v2/search/instant"
    params = {"query": query, "detailed": "true"}
    r = requests.get(url, params=params, headers=NUTRITIONIX_HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    return [item.get("food_name") for item in (data.get("common") or [])[:limit]]

def nutritionix_nutrients_for(query_text: str):
    url = "https://trackapi.nutritionix.com/v2/natural/nutrients"
    payload = {"query": query_text}
    r = requests.post(url, json=payload, headers=NUTRITIONIX_HEADERS, timeout=12)
    r.raise_for_status()
    data = r.json()
    items = []
    for f in data.get("foods", []):
        items.append({
            "food_name": f.get("food_name"),
            "calories": f.get("nf_calories") or 0,
            "protein": f.get("nf_protein") or 0,
            "fat": f.get("nf_total_fat") or 0,
            "carbs": f.get("nf_total_carbohydrate") or 0,
        })
    return items

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.get("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"error": "Missing query"}), 400
    names = nutritionix_instant_search(q, limit=5)
    results = []
    for name in names:
        enriched = nutritionix_nutrients_for(f"1 serving {name}")
        if enriched:
            item = enriched[0]
            results.append({
                "name": item["food_name"],
                "calories": item["calories"],
                "protein": item["protein"],
                "fat": item["fat"],
                "carbs": item["carbs"],
            })
    return jsonify({"results": results})

@app.post("/api/log")
def api_log():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Missing name"}), 400

    quantity = to_float(data.get("quantity", 1))
    log_date = data.get("log_date") or today_str()

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO logs (user_id, log_date, food_name, quantity, calories, protein, fat, carbs) VALUES (?,?,?,?,?,?,?,?)",
            ("demo", log_date, name, quantity,
             to_float(data.get("calories", 0)),
             to_float(data.get("protein", 0)),
             to_float(data.get("fat", 0)),
             to_float(data.get("carbs", 0)))
        )
        conn.commit()
    return jsonify({"status": "ok"})

@app.get("/api/logs/by-date")
def api_logs_by_date_route():
    date_str = request.args.get("date")
    if not date_str:
        return jsonify({"error": "Missing date"}), 400
    return get_logs_for_date(date_str)

@app.get("/api/logs/today")
def api_logs_today():
    return get_logs_for_date(today_str())

def get_logs_for_date(date_str):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM logs WHERE user_id=? AND log_date=? ORDER BY id DESC", ("demo", date_str)).fetchall()
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return jsonify({"date": date_str, "entries": [], "totals": {"calories":0,"protein":0,"fat":0,"carbs":0}})
    df["t_calories"] = df["calories"] * df["quantity"]
    df["t_protein"] = df["protein"] * df["quantity"]
    df["t_fat"] = df["fat"] * df["quantity"]
    df["t_carbs"] = df["carbs"] * df["quantity"]
    totals = {
        "calories": float(df["t_calories"].sum()),
        "protein": float(df["t_protein"].sum()),
        "fat": float(df["t_fat"].sum()),
        "carbs": float(df["t_carbs"].sum())
    }
    return jsonify({"date": date_str, "entries": df.to_dict(orient="records"), "totals": totals})

@app.get("/api/logs/aggregate")
def api_logs_aggregate():
    mode = request.args.get("mode", "week")  # "week" or "month"
    with get_conn() as conn:
        df = pd.read_sql("SELECT * FROM logs WHERE user_id='demo'", conn)
    if df.empty:
        return jsonify([])
    df["log_date"] = pd.to_datetime(df["log_date"])
    df["t_calories"] = df["calories"] * df["quantity"]
    if mode == "month":
        grouped = df.groupby(df["log_date"].dt.to_period("M")).agg({"t_calories":"sum"}).reset_index()
        grouped["log_date"] = grouped["log_date"].astype(str)
    else:  # daily (week)
        grouped = df.groupby(df["log_date"]).agg({"t_calories":"sum"}).reset_index()
        grouped["log_date"] = grouped["log_date"].dt.strftime("%Y-%m-%d")
    return jsonify(grouped.to_dict(orient="records"))

@app.get("/api/logs/export")
def api_logs_export():
    with get_conn() as conn:
        df = pd.read_sql("SELECT * FROM logs", conn)
    if df.empty:
        return jsonify({"error":"No logs"}), 400
    filepath = DB_DIR / "logs_export.csv"
    df.to_csv(filepath, index=False)
    return send_file(filepath, as_attachment=True)

@app.delete("/api/logs/<int:log_id>")
def api_delete_log(log_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM logs WHERE id=?", (log_id,))
        conn.commit()
    return jsonify({"status":"deleted","id":log_id})

if __name__ == "__main__":
    app.run(debug=True)
