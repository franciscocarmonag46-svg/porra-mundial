import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from seed_data import MATCHES

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "porra.db")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave-en-produccion")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def calculate_points(pred_home, pred_away, real_home, real_away):
    if pred_home is None or pred_away is None or real_home is None or real_away is None:
        return 0
    if pred_home == real_home and pred_away == real_away:
        return 3

    def outcome(h, a):
        if h > a:
            return "H"
        if h < a:
            return "A"
        return "D"

    return 2 if outcome(pred_home, pred_away) == outcome(real_home, real_away) else 0


def init_db():
    conn = db()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_no INTEGER UNIQUE NOT NULL,
            stage TEXT NOT NULL,
            group_name TEXT,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            kickoff TEXT NOT NULL,
            venue TEXT,
            home_goals INTEGER,
            away_goals INTEGER,
            status TEXT DEFAULT 'scheduled'
        );

        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            match_id INTEGER NOT NULL,
            pred_home INTEGER NOT NULL,
            pred_away INTEGER NOT NULL,
            points INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, match_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(match_id) REFERENCES matches(id)
        );
        """
    )
    # Admin por defecto
    admin = cur.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
    if not admin:
        cur.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            ("admin", generate_password_hash("admin123")),
        )
    # Cargar partidos solo si no existen
    count = cur.execute("SELECT COUNT(*) AS c FROM matches").fetchone()["c"]
    if count == 0:
        cur.executemany(
            """
            INSERT INTO matches (match_no, stage, group_name, home_team, away_team, kickoff, venue)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            MATCHES,
        )
    conn.commit()
    conn.close()


def current_user():
    if "user_id" not in session:
        return None
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    return user


@app.context_processor
def inject_user():
    return {"user": current_user()}


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Inicia sesión para continuar.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or not user["is_admin"]:
            flash("No tienes permisos de administrador.", "danger")
            return redirect(url_for("matches"))
        return fn(*args, **kwargs)

    return wrapper


def is_locked(kickoff_text):
    try:
        kickoff = datetime.strptime(kickoff_text, "%Y-%m-%d %H:%M")
        return datetime.now() >= kickoff
    except Exception:
        return False


@app.route("/")
def index():
    return redirect(url_for("matches" if "user_id" in session else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Rellena usuario y contraseña.", "warning")
            return redirect(url_for("register"))
        conn = db()
        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (username, generate_password_hash(password)),
            )
            conn.commit()
            session["user_id"] = cur.lastrowid
            flash("Cuenta creada correctamente.", "success")
            return redirect(url_for("matches"))
        except sqlite3.IntegrityError:
            flash("Ese usuario ya existe.", "danger")
        finally:
            conn.close()
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            flash("Sesión iniciada.", "success")
            return redirect(url_for("matches"))
        flash("Usuario o contraseña incorrectos.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("login"))


@app.route("/matches", methods=["GET", "POST"])
@login_required
def matches():
    user_id = session["user_id"]
    conn = db()
    if request.method == "POST":
        match_id = int(request.form["match_id"])
        match = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
        if not match:
            flash("Partido no encontrado.", "danger")
        elif is_locked(match["kickoff"]):
            flash("Ese partido ya ha empezado: no puedes cambiar la predicción.", "warning")
        else:
            pred_home = int(request.form["pred_home"])
            pred_away = int(request.form["pred_away"])
            points = calculate_points(pred_home, pred_away, match["home_goals"], match["away_goals"])
            conn.execute(
                """
                INSERT INTO predictions (user_id, match_id, pred_home, pred_away, points, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, match_id)
                DO UPDATE SET pred_home=excluded.pred_home, pred_away=excluded.pred_away,
                              points=excluded.points, updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, match_id, pred_home, pred_away, points),
            )
            conn.commit()
            flash("Predicción guardada.", "success")
        return redirect(url_for("matches"))

    rows = conn.execute(
        """
        SELECT m.*, p.pred_home, p.pred_away, p.points
        FROM matches m
        LEFT JOIN predictions p ON p.match_id = m.id AND p.user_id = ?
        ORDER BY m.match_no
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return render_template("matches.html", matches=rows, is_locked=is_locked)


@app.route("/leaderboard")
@login_required
def leaderboard():
    conn = db()
    rows = conn.execute(
        """
        SELECT u.username,
               COALESCE(SUM(p.points), 0) AS total_points,
               COUNT(p.id) AS predictions_count,
               SUM(CASE WHEN p.points = 3 THEN 1 ELSE 0 END) AS exacts,
               SUM(CASE WHEN p.points = 2 THEN 1 ELSE 0 END) AS signs
        FROM users u
        LEFT JOIN predictions p ON p.user_id = u.id
        WHERE u.is_admin = 0
        GROUP BY u.id
        ORDER BY total_points DESC, exacts DESC, signs DESC, username ASC
        """
    ).fetchall()
    conn.close()
    return render_template("leaderboard.html", rows=rows)


@app.route("/admin", methods=["GET", "POST"])
@login_required
@admin_required
def admin():
    conn = db()
    if request.method == "POST":
        match_id = int(request.form["match_id"])
        home_goals = request.form.get("home_goals")
        away_goals = request.form.get("away_goals")
        if home_goals == "" or away_goals == "":
            conn.execute(
                "UPDATE matches SET home_goals=NULL, away_goals=NULL, status='scheduled' WHERE id=?",
                (match_id,),
            )
        else:
            hg, ag = int(home_goals), int(away_goals)
            conn.execute(
                "UPDATE matches SET home_goals=?, away_goals=?, status='finished' WHERE id=?",
                (hg, ag, match_id),
            )
            preds = conn.execute("SELECT * FROM predictions WHERE match_id=?", (match_id,)).fetchall()
            for p in preds:
                pts = calculate_points(p["pred_home"], p["pred_away"], hg, ag)
                conn.execute("UPDATE predictions SET points=? WHERE id=?", (pts, p["id"]))
        conn.commit()
        flash("Resultado guardado y puntos recalculados.", "success")
        return redirect(url_for("admin"))

    rows = conn.execute("SELECT * FROM matches ORDER BY match_no").fetchall()
    conn.close()
    return render_template("admin.html", matches=rows)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
