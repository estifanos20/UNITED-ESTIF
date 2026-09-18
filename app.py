from flask import Flask, render_template, jsonify, request, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os
app=Flask(__name__); app.secret_key=os.environ.get("UNITED_ESTIF_SECRET","change-this-secret")
DB="united_estif.db"
def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init():
    c=db()
    c.executescript("""CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE,password TEXT,balance REAL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS matches(id INTEGER PRIMARY KEY,league TEXT,home TEXT,away TEXT,status TEXT,minute INTEGER DEFAULT 0,hs INTEGER DEFAULT 0,aws INTEGER DEFAULT 0,hodd REAL,draw REAL,aodd REAL,active INTEGER DEFAULT 1);
    CREATE TABLE IF NOT EXISTS favorites(user_id INTEGER,match_id INTEGER,UNIQUE(user_id,match_id));
    CREATE TABLE IF NOT EXISTS bets(id INTEGER PRIMARY KEY, user_id INTEGER, stake REAL, odds REAL, status TEXT DEFAULT 'PENDING');""")
    if c.execute("SELECT COUNT(*) n FROM matches").fetchone()["n"]==0:
        data=[("Premier League","Manchester United","Manchester City","SCHEDULED",0,0,0,2.25,3.45,2.55),
        ("La Liga","Real Madrid","Barcelona","LIVE",67,1,1,2.10,3.60,2.75),
        ("Serie A","Inter","Milan","SCHEDULED",0,0,0,2.00,3.40,3.10),
        ("Bundesliga","Bayern Munich","Dortmund","FINISHED",90,3,1,1.55,4.50,5.20)]
        c.executemany("INSERT INTO matches(league,home,away,status,minute,hs,aws,hodd,draw,aodd) VALUES(?,?,?,?,?,?,?,?,?,?)",data)
    c.commit(); c.close()
init()

@app.get("/")
def home():
    return render_template("index.html",matches=db().execute("SELECT * FROM matches WHERE active=1 ORDER BY CASE status WHEN 'LIVE' THEN 0 ELSE 1 END,id").fetchall(), user=session.get("user"))
@app.get("/live")
def live(): return render_template("live.html")
@app.get("/api/live")
def api_live(): return jsonify(matches=[dict(x) for x in db().execute("SELECT * FROM matches WHERE active=1 AND status='LIVE'").fetchall()])
@app.get("/search")
def search():
    q=request.args.get("q","").strip(); like=f"%{q}%"
    rows=db().execute("SELECT * FROM matches WHERE active=1 AND (home LIKE ? OR away LIKE ? OR league LIKE ?)",(like,like,like)).fetchall()
    return render_template("search.html",matches=rows,q=q)
@app.get("/favorites")
def favorites():
    if not session.get("uid"): return redirect("/login")
    rows=db().execute("SELECT m.* FROM matches m JOIN favorites f ON f.match_id=m.id WHERE f.user_id=?",(session["uid"],)).fetchall()
    return render_template("favorites.html",matches=rows)
@app.post("/api/favorite/<int:mid>")
def fav(mid):
    if not session.get("uid"): return jsonify(error="login_required"),401
    c=db(); row=c.execute("SELECT 1 FROM favorites WHERE user_id=? AND match_id=?",(session["uid"],mid)).fetchone()
    if row: c.execute("DELETE FROM favorites WHERE user_id=? AND match_id=?",(session["uid"],mid)); saved=False
    else: c.execute("INSERT OR IGNORE INTO favorites VALUES(?,?)",(session["uid"],mid)); saved=True
    c.commit(); return jsonify(saved=saved)
@app.get("/match/<int:mid>")
def match(mid):
    m=db().execute("SELECT * FROM matches WHERE id=?",(mid,)).fetchone()
    return render_template("match.html",m=m)
@app.get("/login")
def login(): return render_template("login.html")
@app.post("/login")
def do_login():
    u=request.form["username"]; p=request.form["password"]; row=db().execute("SELECT * FROM users WHERE username=?",(u,)).fetchone()
    if row and check_password_hash(row["password"],p): session["uid"]=row["id"]; session["user"]=u; return redirect("/")
    return render_template("login.html",error="Invalid login")
@app.post("/register")
def register():
    u=request.form["username"]; p=request.form["password"]; c=db()
    try:
        c.execute("INSERT INTO users(username,password,balance) VALUES(?,?,?)",(u,generate_password_hash(p),1000)); c.commit()
    except sqlite3.IntegrityError: return render_template("login.html",error="Username already exists")
    session["uid"]=c.execute("SELECT id FROM users WHERE username=?",(u,)).fetchone()["id"]; session["user"]=u; return redirect("/")
@app.get("/logout")
def logout(): session.clear(); return redirect("/")
@app.get("/profile")
def profile():
    if not session.get("uid"): return redirect("/login")
    u=db().execute("SELECT * FROM users WHERE id=?",(session["uid"],)).fetchone()
    return render_template("profile.html",u=u)
@app.get("/admin")
def admin():
    return render_template("admin.html",matches=db().execute("SELECT * FROM matches ORDER BY id").fetchall())
@app.post("/admin/match/<int:mid>")
def admin_match(mid):
    f=request.form; c=db()
    c.execute("UPDATE matches SET status=?,minute=?,hs=?,aws=?,hodd=?,draw=?,aodd=? WHERE id=?",
              (f["status"],int(f["minute"]),int(f["hs"]),int(f["aws"]),float(f["hodd"]),float(f["draw"]),float(f["aodd"]),mid)); c.commit()
    return redirect("/admin")
if __name__=="__main__": app.run(debug=True)
