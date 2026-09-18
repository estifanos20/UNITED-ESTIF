from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")

DB = "united_estif.db"
DEMO_BALANCE = 1000.0
MAX_STAKE = 1000.0


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        balance REAL DEFAULT 1000
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS matches(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league TEXT,
        home TEXT,
        away TEXT,
        status TEXT,
        hs INTEGER DEFAULT 0,
        aws INTEGER DEFAULT 0,
        minute INTEGER DEFAULT 0,
        hodd REAL,
        draw REAL,
        aodd REAL,
        active INTEGER DEFAULT 1
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS favorites(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        match_id INTEGER,
        UNIQUE(user_id,match_id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS bets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        match_id INTEGER,
        selection TEXT,
        stake REAL,
        odds REAL,
        potential_return REAL,
        status TEXT DEFAULT 'PENDING',
        ticket TEXT UNIQUE
    )
    """)

    # Upgrade old V20 bets table
    cols = [
        r["name"]
        for r in conn.execute("PRAGMA table_info(bets)").fetchall()
    ]

    for name, definition in [
        ("match_id", "INTEGER"),
        ("selection", "TEXT"),
        ("potential_return", "REAL"),
        ("ticket", "TEXT")
    ]:
        if name not in cols:
            conn.execute(
                f"ALTER TABLE bets ADD COLUMN {name} {definition}"
            )

    # Seed matches if database is empty
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM matches"
    ).fetchone()["c"]

    if count == 0:
        data = [
            (
                "Premier League",
                "Manchester United",
                "Manchester City",
                "SCHEDULED",
                0, 0, 0,
                2.25, 3.45, 2.55, 1
            ),
            (
                "La Liga",
                "Real Madrid",
                "Barcelona",
                "LIVE",
                1, 1, 67,
                2.10, 3.60, 2.75, 1
            ),
            (
                "Serie A",
                "Inter",
                "Milan",
                "SCHEDULED",
                0, 0, 0,
                2.00, 3.40, 3.10, 1
            ),
            (
                "Bundesliga",
                "Bayern Munich",
                "Dortmund",
                "FINISHED",
                3, 1, 90,
                1.55, 4.50, 5.20, 1
            )
        ]

        conn.executemany("""
        INSERT INTO matches
        (league,home,away,status,hs,aws,minute,
         hodd,draw,aodd,active)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """, data)

    conn.commit()
    conn.close()


init_db()


@app.route("/")
def home():
    conn = db()

    matches = conn.execute("""
    SELECT * FROM matches
    WHERE active=1
    ORDER BY id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        matches=matches
    )


@app.route("/live")
def live():
    conn = db()

    matches = conn.execute("""
    SELECT * FROM matches
    WHERE status='LIVE'
    AND active=1
    """).fetchall()

    conn.close()

    return render_template(
        "live.html",
        matches=matches
    )


@app.route("/api/live")
def api_live():
    conn = db()

    matches = conn.execute("""
    SELECT * FROM matches
    WHERE status='LIVE'
    AND active=1
    """).fetchall()

    conn.close()

    return jsonify([
        dict(m) for m in matches
    ])


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()

    conn = db()

    if q:
        matches = conn.execute("""
        SELECT * FROM matches
        WHERE active=1
        AND (
            home LIKE ?
            OR away LIKE ?
            OR league LIKE ?
        )
        """, (
            f"%{q}%",
            f"%{q}%",
            f"%{q}%"
        )).fetchall()
    else:
        matches = []

    conn.close()

    return render_template(
        "search.html",
        matches=matches,
        q=q
    )


@app.route("/favorites")
def favorites():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = db()

    matches = conn.execute("""
    SELECT m.*
    FROM matches m
    JOIN favorites f
    ON f.match_id=m.id
    WHERE f.user_id=?
    ORDER BY m.id DESC
    """, (
        session["user_id"],
    )).fetchall()

    conn.close()

    return render_template(
        "favorites.html",
        matches=matches
    )


@app.route("/api/favorite/<int:mid>", methods=["POST"])
def favorite(mid):
    if "user_id" not in session:
        return jsonify({
            "error": "login_required"
        }), 401

    uid = session["user_id"]

    conn = db()

    existing = conn.execute("""
    SELECT id FROM favorites
    WHERE user_id=?
    AND match_id=?
    """, (uid, mid)).fetchone()

    if existing:
        conn.execute(
            "DELETE FROM favorites WHERE id=?",
            (existing["id"],)
        )
        saved = False
    else:
        conn.execute("""
        INSERT OR IGNORE INTO favorites
        (user_id,match_id)
        VALUES(?,?)
        """, (uid, mid))
        saved = True

    conn.commit()
    conn.close()

    return jsonify({
        "saved": saved
    })


@app.route("/match/<int:mid>")
def match(mid):
    conn = db()

    m = conn.execute("""
    SELECT * FROM matches
    WHERE id=?
    """, (mid,)).fetchone()

    conn.close()

    if not m:
        return "Match not found", 404

    return render_template(
        "match.html",
        m=m
    )


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        password = request.form.get(
            "password", ""
        )

        conn = db()

        user = conn.execute("""
        SELECT * FROM users
        WHERE username=?
        """, (username,)).fetchone()

        conn.close()

        if user and check_password_hash(
            user["password"],
            password
        ):
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("home"))

        return render_template(
            "login.html",
            error="Invalid username or password"
        )

    return render_template("login.html")


@app.route("/register", methods=["POST"])
def register():

    username = request.form.get(
        "username", ""
    ).strip()

    password = request.form.get(
        "password", ""
    )

    if not username or not password:
        return "Username and password are required", 400

    conn = db()

    try:

        cur = conn.execute("""
        INSERT INTO users
        (username,password,balance)
        VALUES(?,?,?)
        """, (
            username,
            generate_password_hash(password),
            DEMO_BALANCE
        ))

        conn.commit()

        uid = cur.lastrowid

    except sqlite3.IntegrityError:

        conn.close()

        return "Username already exists", 400

    conn.close()

    session["user_id"] = uid
    session["username"] = username

    return redirect(url_for("home"))


@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("home"))


@app.route("/profile")
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = db()
    user = conn.execute(
        "SELECT id, username, balance FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()
    conn.close()

    if user is None:
        return redirect(url_for("login"))

    return render_template("profile.html", user=user)


# =========================
# V22 MULTIPLE BET API
# =========================

@app.route("/api/demo-bet", methods=["POST"])
def demo_bet():

    if "user_id" not in session:
        return jsonify({
            "error": "login_required"
        }), 401

    data = request.get_json(
        silent=True
    ) or {}

    try:
        match_id = int(
            data.get("match_id")
        )

        stake = float(
            data.get("stake")
        )

        selections = data.get(
            "selections"
        )

        # Backward compatibility
        if not selections:
            old_selection = data.get(
                "selection"
            )

            old_odds = float(
                data.get("odds")
            )

            selections = [{
                "selection": old_selection,
                "odds": old_odds
            }]

    except (TypeError, ValueError):

        return jsonify({
            "error": "Invalid bet information"
        }), 400


    if not isinstance(
        selections,
        list
    ) or len(selections) == 0:

        return jsonify({
            "error": "No selections"
        }), 400


    if stake <= 0:

        return jsonify({
            "error": "Stake must be greater than 0"
        }), 400


    if stake > MAX_STAKE:

        return jsonify({
            "error":
            "Maximum demo stake is ETB 1000"
        }), 400


    combined_odds = 1.0

    clean = []


    for item in selections:

        selection = str(
            item.get("selection", "")
        ).strip()

        try:
            odds = float(
                item.get("odds")
            )
        except (TypeError, ValueError):
            return jsonify({
                "error": "Invalid odds"
            }), 400

        if not selection:
            return jsonify({
                "error": "Invalid selection"
            }), 400

        if odds <= 1:
            return jsonify({
                "error": "Invalid odds"
            }), 400

        combined_odds *= odds

        clean.append({
            "selection": selection,
            "odds": odds
        })


    combined_odds = round(
        combined_odds,
        2
    )

    potential_return = round(
        stake * combined_odds,
        2
    )


    conn = db()


    match_row = conn.execute("""
    SELECT * FROM matches
    WHERE id=?
    AND active=1
    """, (
        match_id,
    )).fetchone()


    if not match_row:

        conn.close()

        return jsonify({
            "error":
            "Match is not available"
        }), 400


    user = conn.execute("""
    SELECT * FROM users
    WHERE id=?
    """, (
        session["user_id"],
    )).fetchone()


    if not user:

        conn.close()

        return jsonify({
            "error": "User not found"
        }), 400


    if user["balance"] < stake:

        conn.close()

        return jsonify({
            "error":
            "Insufficient demo balance"
        }), 400


    ticket = (
        "UE-" +
        secrets.token_hex(4).upper()
    )


    selection_text = " | ".join(
        [
            f"{x['selection']} @ {x['odds']:.2f}"
            for x in clean
        ]
    )


    conn.execute("""
    UPDATE users
    SET balance=balance-?
    WHERE id=?
    """, (
        stake,
        session["user_id"]
    ))


    conn.execute("""
    INSERT INTO bets
    (user_id,match_id,selection,
     stake,odds,potential_return,
     status,ticket)
    VALUES(?,?,?,?,?,?,?,?)
    """, (
        session["user_id"],
        match_id,
        selection_text,
        stake,
        combined_odds,
        potential_return,
        "PENDING",
        ticket
    ))


    conn.commit()


    new_balance = conn.execute("""
    SELECT balance FROM users
    WHERE id=?
    """, (
        session["user_id"],
    )).fetchone()["balance"]


    conn.close()


    return jsonify({

        "success": True,

        "ticket": ticket,

        "selections": clean,

        "combined_odds":
            combined_odds,

        "stake":
            stake,

        "potential_return":
            potential_return,

        "balance":
            round(new_balance, 2)
    })


@app.route("/my-bets")
def my_bets():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = db()

    bets = conn.execute("""
    SELECT
        b.*,
        m.league,
        m.home,
        m.away,
        m.status AS match_status
    FROM bets b
    LEFT JOIN matches m
    ON b.match_id=m.id
    WHERE b.user_id=?
    ORDER BY b.id DESC
    """, (
        session["user_id"],
    )).fetchall()

    conn.close()

    return render_template(
        "my_bets.html",
        bets=bets
    )


# =========================
# DEMO ADMIN
# =========================

@app.route("/admin")
def admin():

    conn = db()

    matches = conn.execute(
        "SELECT * FROM matches ORDER BY id DESC"
    ).fetchall()

    users = conn.execute(
        "SELECT id,username,balance FROM users"
    ).fetchall()

    bets = conn.execute("""
    SELECT
        b.*,
        u.username,
        m.home,
        m.away
    FROM bets b
    LEFT JOIN users u
    ON b.user_id=u.id
    LEFT JOIN matches m
    ON b.match_id=m.id
    ORDER BY b.id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin.html",
        matches=matches,
        users=users,
        bets=bets
    )


@app.route(
    "/admin/match/<int:mid>",
    methods=["POST"]
)
def admin_match(mid):

    status = request.form.get(
        "status"
    )

    hs = request.form.get(
        "hs", 0
    )

    aws = request.form.get(
        "aws", 0
    )

    minute = request.form.get(
        "minute", 0
    )

    hodd = request.form.get(
        "hodd"
    )

    draw = request.form.get(
        "draw"
    )

    aodd = request.form.get(
        "aodd"
    )

    conn = db()

    conn.execute("""
    UPDATE matches
    SET
        status=?,
        hs=?,
        aws=?,
        minute=?,
        hodd=?,
        draw=?,
        aodd=?
    WHERE id=?
    """, (
        status,
        hs,
        aws,
        minute,
        hodd,
        draw,
        aodd,
        mid
    ))

    conn.commit()
    conn.close()

    return redirect(
        url_for("admin")
    )


if __name__ == "__main__":
    app.run(debug=True)
