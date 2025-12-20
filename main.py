# main.py
from fastapi import FastAPI, Request, UploadFile, Form, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime, date
import qrcode
from email.mime.image import MIMEImage
from fastapi.responses import Response
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
import sqlite3, json, os
from fastapi import Form
# NEW: email + dotenv deps
import smtplib, ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

signature_block = """
<br><br>
--<br>
<strong>Hazmat Operations Team</strong><br>

<img src="cid:hazmatlogo" alt="HAZMAT Logo" style="width:200px; height:80px;;"><br>

HAZMAT Global Support Services<br>
Unit 3, North Lake Business Park
Malcolm Moodie Crescent, Jet Park
Boksburg 1459, Republic of South Africa<br><br>

📞 +27 11 397 2000
✉️ <a href="mailto:csd@hazglobal.com">csd@hazglobal.com</a><br>

<small style="color:green;">
Please consider the environment before printing this email.<br>
<small style="color:grey;">
Privileged or confidential information may be contained in this message. If you are not the addressee indicated, please delete this message and notify the sender.
</small>
"""

@app.get("/debug/smtp")
def debug_smtp():
    import socket

    tests = [
        ("smtp.gmail.com", 587),
        ("smtp.gmail.com", 465),
        ("smtp.gmail.com", 25),
        ("8.8.8.8", 53),  # DNS server test
    ]

    results = {}

    for host, port in tests:
        try:
            s = socket.create_connection((host, port), timeout=5)
            s.close()
            results[f"{host}:{port}"] = "✅ Reachable"
        except Exception as e:
            results[f"{host}:{port}"] = f"❌ {type(e).__name__}: {e}"

    return results


os.makedirs("static/waybills", exist_ok=True)
os.makedirs("static/qrcodes", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("static/backups", exist_ok=True)

# NEW: load SMTP configuration
load_dotenv()
SMTP_SERVER = os.getenv("SMTP_SERVER", "")
SMTP_PORT = int(os.getenv("SMTP_PORT") or "587")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
OPS_CC = os.getenv("OPS_CC", "")  # optional CC to ops


def init_db():
    if os.path.exists("hazmat.db"):
        print("✅ hazmat.db already exists")
        return

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()

    try:
        # Create tables
        cursor.execute("""CREATE TABLE IF NOT EXISTS updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ops TEXT,
            hmj TEXT,
            haz TEXT,
            company TEXT,
            date TEXT,
            time TEXT,
            "update" TEXT
        );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            name TEXT
        );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS completed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ops TEXT,
            company TEXT,
            delivery_date TEXT,
            time TEXT,
            signed_by TEXT,
            document TEXT,
            pod TEXT
        );""")

        cursor.execute("""CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_number TEXT,
            service_type TEXT,
            collection_company TEXT,
            collection_address TEXT,
            collection_person TEXT,
            collection_number TEXT,
            delivery_company TEXT,
            delivery_address TEXT,
            delivery_person TEXT,
            delivery_number TEXT,
            client_reference TEXT,
            pickup_date TEXT,
            inco_terms TEXT,
            client_notes TEXT,
            pdf_path TEXT,
            timestamp TEXT,
            assigned_driver TEXT,
            status TEXT
        );""")

        cursor.execute("""CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_number TEXT,
            driver_id TEXT,
            timestamp TEXT
        );""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            name TEXT
        );""")
        print("✅ clients table created")
        cursor.execute("""CREATE TABLE IF NOT EXISTS saved_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER,
            label TEXT,
            type TEXT,
            company TEXT,
            address TEXT,
            contact_person TEXT,
            contact_number TEXT,
            email TEXT,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );""")
        print("✅ saved_addresses table created")

        print("✅ Tables created")

        # Restore from JSON if backups exist
        def restore_table(json_path, table_name):
            if os.path.exists(json_path):
                with open(json_path) as f:
                    data = json.load(f)
                    for row in data:
                        cursor.execute(f"""
                            INSERT INTO {table_name} ({','.join(row.keys())})
                            VALUES ({','.join(['?'] * len(row))})
                        """, list(row.values()))
                print(f"✅ Restored {table_name} from {json_path}")

        restore_table("static/backups/requests.json", "requests")
        restore_table("static/backups/updates.json", "updates")
        restore_table("static/backups/completed.json", "completed")

        conn.commit()
        print("✅ hazmat.db initialized and restored")
    except Exception as e:
        print("❌ init_db() failed:", e)
    finally:
        conn.close()


init_db()


def get_next_reference_number():
    counter_path = "static/backups/ref_counter.txt"

    # Ensure the file exists
    if not os.path.exists(counter_path):
        with open(counter_path, "w") as f:
            f.write("0")

    # Read current value
    with open(counter_path, "r") as f:
        try:
            last_id = int(f.read().strip())
        except ValueError:
            last_id = 0

    # Increment and write back
    new_id = last_id + 1
    with open(counter_path, "w") as f:
        f.write(str(new_id))

    return f"HAZJNB{str(new_id).zfill(4)}"


def backup_database():
    os.makedirs("static/backups", exist_ok=True)
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()

    def dump_table(table_name, filename):
        cursor.execute(f"SELECT * FROM {table_name}")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        with open(f"static/backups/{filename}", "w") as f:
            json.dump([dict(zip(columns, row)) for row in rows], f, indent=2)

    dump_table("requests", "requests.json")
    dump_table("updates", "updates.json")
    dump_table("completed", "completed.json")

    # ✅ Backup ref_counter.txt
    counter_path = "static/backups/ref_counter.txt"
    if os.path.exists(counter_path):
        with open(counter_path) as f:
            ref_value = f.read().strip()
        with open("static/backups/ref_counter_backup.json", "w") as f:
            json.dump({"last_ref": ref_value}, f)

    conn.close()
    print("✅ Database and counter backed up to JSON")


@app.get("/signup", response_class=HTMLResponse)
def signup_form():
    return """
    <h2>Client Signup</h2>
    <form method="post" action="/signup">
      <label>Name</label><input type="text" name="name"><br>
      <label>Email</label><input type="email" name="email"><br>
      <label>Password</label><input type="password" name="password"><br>
      <button type="submit">Sign Up</button>
    </form>
    """


@app.post("/signup")
async def signup(request: Request, name: str = Form(None), email: str = Form(None), password: str = Form(None)):
    # If called via JSON, parse manually
    if not email or not password:
        payload = await request.json()
        name = payload.get("name")
        email = payload.get("email")
        password = payload.get("password")

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO clients (email, password, name) VALUES (?, ?, ?)", (email, password, name))
        conn.commit()
        client_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return {"status": "error", "message": "Email already registered"}
    conn.close()

    # ✅ Auto-login: set cookie and redirect to home
    response = RedirectResponse("/", status_code=302)
    response.set_cookie(key="client_id", value=str(client_id), httponly=True)
    return response


@app.post("/login")
async def login(request: Request, email: str = Form(None), password: str = Form(None)):
    # If called via JSON, parse manually
    if not email or not password:
        payload = await request.json()
        email = payload.get("email")
        password = payload.get("password")

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM clients WHERE email = ? AND password = ?", (email, password))
    row = cursor.fetchone()
    conn.close()

    if row:
        response = RedirectResponse("/", status_code=302)
        response.set_cookie(key="client_id", value=str(row[0]), httponly=True)
        return response
    return {"status": "error", "message": "Invalid credentials"}


@app.post("/login")
def login(payload: dict):
    email = payload.get("email")
    password = payload.get("password")

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM clients WHERE email = ? AND password = ?", (email, password))
    row = cursor.fetchone()
    conn.close()

    if row:
        response = JSONResponse({"status": "success", "client_id": row[0], "name": row[1]})
        # ✅ set cookie for auto-login
        response.set_cookie(key="client_id", value=str(row[0]), httponly=True)
        return response
    return {"status": "error", "message": "Invalid credentials"}


@app.get("/api/me")
def get_client_name(request: Request):
    client_id = request.cookies.get("client_id")
    if not client_id:
        return {"name": None}
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM clients WHERE id = ?", (client_id,))
    row = cursor.fetchone()
    conn.close()
    return {"name": row[0] if row else None}



@app.get("/", response_class=HTMLResponse)
def home():
    return """
        <style>
          html, body { margin:0; padding:0; height:100%; background:#F1F8E9; font-family:'Segoe UI',sans-serif; display:flex; flex-direction:column; }
          header { background:#2E7D32; color:white; padding:1rem 2rem; display:flex; align-items:center; justify-content:space-between; }
          header img { height:60px; }
          nav a { color:white; margin-left:1rem; text-decoration:none; font-weight:500; }
          nav a:hover { text-decoration:underline; }
          main { flex:1; max-width:960px; margin:2rem auto; padding:1rem; text-align:center; }
          h1 { color:#2E7D32; margin-bottom:1rem; }
          p { font-size:16px; line-height:1.6; }
          footer { background:#2E7D32; color:white; text-align:center; padding:1rem; font-size:14px; line-height:1.6; }
        </style>

        <header>
          <img src="/static/logo.png" alt="Hazmat Global Support Services Logo">
          <nav style="flex:1; display:flex; justify-content:flex-end; align-items:center;">
  <a href="/">Home</a>
  <a href="/embed/submit">Book a Collection</a>
  <a href="/embed/track">Track Shipments</a>
  <a href="/embed/complaint">File a Complaint</a>
  <a href="/embed/rate">Rate Our Services</a>
  <span id="client-nav" style="margin-left:auto; font-weight:600;"></span>
</nav>

<script>
  document.addEventListener("DOMContentLoaded", function() {
    fetch("/api/me")
      .then(res => res.json())
      .then(data => {
        const navSpan = document.getElementById("client-nav");
        if (data.name) {
          navSpan.innerText = data.name;   // ✅ show client’s name
        } else {
          navSpan.innerHTML = '<a href="/embed/login">Login / Sign Up</a>'; // ✅ fallback
        }
      })
      .catch(err => console.error("⚠️ Failed to fetch client info", err));
  });
</script>
        </header>

        <main>
          <h1>Welcome to Hazmat Global Support Services</h1>
          <p>Your trusted partner in hazardous materials logistics. Navigate above to book collections, track shipments, file complaints, or rate our services.</p>
        </main>

        <footer>
          <p><strong>Hazmat Global Support Services</strong></p>
          <p><strong>Contact Numbers:</strong> Johannesburg: +27 11 397 2000 | Port Elizabeth: +27 31 587 5241 | Durban: +27 55 897 5412 | Cape Town: +27 21 258 4587</p>
          <p><strong>Quotes & Support</strong> — Email: <a href="mailto:csd@hazglobal.com" style="color:white;">csd@hazglobal.com</a></p>
          <p>&copy; 2025 Hazmat Global Support Services. All rights reserved.</p>
        </footer>
        """




@app.get("/embed/login", response_class=HTMLResponse)
def embed_login():
    return """
    <style>
      html, body {
        margin: 0;
        padding: 0;
        height: 100%;
        background: #F1F8E9;
        font-family: 'Segoe UI', sans-serif;
        display: flex;
        flex-direction: column;
      }
      header {
        background: #2E7D32;
        color: white;
        padding: 1rem 2rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      header img { height: 60px; }
      nav a {
        color: white;
        margin-left: 1rem;
        text-decoration: none;
        font-weight: 500;
      }
      nav a:hover { text-decoration: underline; }
      main {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        max-width: 960px;
        margin: 0 auto;
        padding: 2rem 1rem;
      }
      footer {
        background: #2E7D32;
        color: white;
        text-align: center;
        padding: 1rem;
        font-size: 14px;
        line-height: 1.6;
      }
      .auth-wrapper {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 2rem;
        width: 100%;
      }
      @media (max-width: 768px) {
        .auth-wrapper { grid-template-columns: 1fr; }
      }
      .auth-block {
        background: #fff;
        border: 1px solid #C8E6C9;
        border-radius: 8px;
        padding: 2rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
      }
      h2 {
        text-align: center;
        color: #2E7D32;
        margin-bottom: 2rem;
      }
      h3 { margin-top: 0; color: #2E7D32; }
      input {
        width: 100%;
        margin-bottom: 12px;
        padding: 10px;
        border: 1px solid #B0BEC5;
        border-radius: 4px;
        font-size: 14px;
      }
      button {
        background: #2E7D32;
        color: white;
        border: none;
        padding: 0.6rem 1.2rem;
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
      }
      button:hover { background: #388E3C; }
    </style>

    <header>
      <img src="/static/logo.png" alt="Hazmat Global Support Services Logo">
      <nav style="flex:1; display:flex; justify-content:flex-end; align-items:center;">
        <a href="/">Home</a>
        <a href="/embed/submit">Book a Collection</a>
        <a href="/embed/track">Track Shipments</a>
        <a href="/embed/complaint">File a Complaint</a>
        <a href="/embed/rate">Rate Our Services</a>
        <span id="client-nav" style="margin-left:auto; font-weight:600;"></span>
      </nav>
      <script>
        document.addEventListener("DOMContentLoaded", function() {
          fetch("/api/me")
            .then(res => res.json())
            .then(data => {
              const navSpan = document.getElementById("client-nav");
              if (data.name) {
                navSpan.innerText = data.name;
              } else {
                navSpan.innerHTML = '<a href="/embed/login">Login / Sign Up</a>';
              }
            })
            .catch(err => console.error("⚠️ Failed to fetch client info", err));
        });
      </script>
    </header>

    <main>
      <h2>Client Access Portal</h2>
      <div class="auth-wrapper">
        <div class="auth-block">
          <h3>Sign Up</h3>
          <input type="text" id="signup-name" placeholder="Name">
          <input type="email" id="signup-email" placeholder="Email">
          <input type="password" id="signup-password" placeholder="Password">
          <button onclick="signup()">Sign Up</button>
          <p id="signup-status" style="color:green;"></p>
        </div>
        <div class="auth-block">
          <h3>Login</h3>
          <input type="email" id="email" placeholder="Email">
          <input type="password" id="password" placeholder="Password">
          <button onclick="login()">Login</button>
          <p id="login-status" style="color:red;"></p>
        </div>
      </div>
    </main>

    <footer>
      <div style="max-width: 960px; margin: 0 auto; padding: 1rem; display: flex; flex-direction: column; align-items: center; text-align: center; color: white;">
        <p style="font-weight: bold; font-size: 16px;">Hazmat Global Support Services</p>
        <p style="margin: 0.5rem 0;">
          <strong>Contact Numbers:</strong>
          Johannesburg: +27 11 397 2000 &nbsp;|&nbsp;
          Port Elizabeth: +27 31 587 5241 &nbsp;|&nbsp;
          Durban: +27 55 897 5412 &nbsp;|&nbsp;
          Cape Town: +27 21 258 4587
        </p>
        <p style="margin: 0.5rem 0;"><strong>Quotes & Support</strong></p>
        <p style="margin: 0.2rem 0;">Email: <a href="mailto:csd@hazglobal.com" style="color:white;">csd@hazglobal.com</a></p>
        <p style="margin-top: 1rem;">&copy; 2025 Hazmat Global Support Services. All rights reserved.</p>
      </div>
    </footer>

    <script>
    function signup() {
      const name = document.getElementById("signup-name").value;
      const email = document.getElementById("signup-email").value;
      const password = document.getElementById("signup-password").value;

      fetch("/api/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, password })
      })
      .then(res => res.json())
      .then(data => {
        if (data.status === "ok") {
          document.getElementById("signup-status").innerText = "✅ Account created!";
        } else {
          document.getElementById("signup-status").innerText = "⚠️ " + (data.message || "Signup failed");
        }
      })
      .catch(err => {
        console.error("Signup error", err);
        document.getElementById("signup-status").innerText = "⚠️ Error during signup";
      });
    }

    function login() {
      const email = document.getElementById("email").value;
      const password = document.getElementById("password").value;

      fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      })
      .then(res => res.json())
      .then(data => {
        if (data.status === "ok") {
          document.getElementById("login-status").innerText = "✅ Logged in!";
          window.location.href = "/embed/submit";
        } else {
          document.getElementById("login-status").innerText = "⚠️ " + (data.message || "Login failed");
        }
      })
      .catch(err => {
        console.error("Login error", err);
        document.getElementById("login-status").innerText = "⚠️ Error during login";
      });
    }
    </script>
    """
@app.post("/api/signup")
async def api_signup(payload: dict, response: Response):
    name = payload.get("name")
    email = payload.get("email")
    password = payload.get("password")

    if not name or not email or not password:
        return {"status": "error", "message": "Missing fields"}

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()

    # Ensure clients table exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT
        );
    """)

    try:
        cursor.execute(
            "INSERT INTO clients (name, email, password) VALUES (?, ?, ?)",
            (name, email, password)
        )
        conn.commit()
        client_id = cursor.lastrowid
        # set cookie so user stays logged in
        response.set_cookie(key="client_id", value=str(client_id))
        return {"status": "ok"}
    except sqlite3.IntegrityError:
        return {"status": "error", "message": "Email already exists"}
    finally:
        conn.close()

@app.get("/embed/track", response_class=HTMLResponse)
def embed_track():
    return """
    <style>
      html, body { margin:0; padding:0; height:100%; background:#F1F8E9; font-family:'Segoe UI',sans-serif; display:flex; flex-direction:column; }
      header { background:#2E7D32; color:white; padding:1rem 2rem; display:flex; align-items:center; justify-content:space-between; }
      header img { height:60px; }
      nav a { color:white; margin-left:1rem; text-decoration:none; font-weight:500; }
      nav a:hover { text-decoration:underline; }
      main { flex:1; max-width:960px; margin:2rem auto; padding:2rem; }
      h2 { color:#2E7D32; text-align:center; margin-bottom:1.5rem; }
      form { background:#fff; border:1px solid #C8E6C9; border-radius:8px; padding:2rem; box-shadow:0 4px 12px rgba(0,0,0,0.05); }
      label { display:block; margin-bottom:8px; font-weight:500; color:#2E7D32; }
      input { width:100%; margin-bottom:12px; padding:10px; border:1px solid #B0BEC5; border-radius:4px; font-size:14px; }
      button { background:#2E7D32; color:white; border:none; padding:0.6rem 1.2rem; border-radius:4px; cursor:pointer; font-size:14px; }
      button:hover { background:#388E3C; }
      footer { background:#2E7D32; color:white; text-align:center; padding:1rem; font-size:14px; line-height:1.6; }
    </style>

    <header>
      <img src="/static/logo.png" alt="Hazmat Global Support Services Logo">
      <nav style="flex:1; display:flex; justify-content:flex-end; align-items:center;">
  <a href="/">Home</a>
  <a href="/embed/submit">Book a Collection</a>
  <a href="/embed/track">Track Shipments</a>
  <a href="/embed/complaint">File a Complaint</a>
  <a href="/embed/rate">Rate Our Services</a>
  <span id="client-nav" style="margin-left:auto; font-weight:600;"></span>
</nav>

<script>
  document.addEventListener("DOMContentLoaded", function() {
    fetch("/api/me")
      .then(res => res.json())
      .then(data => {
        const navSpan = document.getElementById("client-nav");
        if (data.name) {
          navSpan.innerText = data.name;   // ✅ show client’s name
        } else {
          navSpan.innerHTML = '<a href="/embed/login">Login / Sign Up</a>'; // ✅ fallback
        }
      })
      .catch(err => console.error("⚠️ Failed to fetch client info", err));
  });
</script>
    </header>

    <main>
      <h2>Track Shipments</h2>
      <form action="/embed/track" method="post">
        <label for="tracking_number">Tracking Number</label>
        <input type="text" id="tracking_number" name="tracking_number" required>
        <button type="submit">Track Shipment</button>
      </form>
    </main>

    <footer>
      <p><strong>Hazmat Global Support Services</strong></p>
      <p><strong>Contact Numbers:</strong> Johannesburg: +27 11 397 2000 | Port Elizabeth: +27 31 587 5241 | Durban: +27 55 897 5412 | Cape Town: +27 21 258 4587</p>
      <p><strong>Quotes & Support</strong> — Email: <a href="mailto:csd@hazglobal.com" style="color:white;">csd@hazglobal.com</a></p>
      <p>&copy; 2025 Hazmat Global Support Services. All rights reserved.</p>
    </footer>
    """


@app.get("/embed/contact", response_class=HTMLResponse)
def embed_contact():
    return """
    <h2>Contact Us</h2>
    <p>📍 Johannesburg HQ: 123 Hazmat Lane, Rand West City</p>
    <p>📍 Cape Town Branch: 456 Coastal Drive</p>
    <p>📍 Durban Hub: 789 Portside Avenue</p>
    <p>📧 Email: support@hazmatglobal.com</p>
    <p>📞 Phone: +27 11 555 1234</p>
    """


@app.get("/embed/complaint", response_class=HTMLResponse)
def embed_complaint():
    return """
    <style>
      html, body { margin:0; padding:0; height:100%; background:#F1F8E9; font-family:'Segoe UI',sans-serif; display:flex; flex-direction:column; }
      header { background:#2E7D32; color:white; padding:1rem 2rem; display:flex; align-items:center; justify-content:space-between; }
      header img { height:60px; }
      nav a { color:white; margin-left:1rem; text-decoration:none; font-weight:500; }
      nav a:hover { text-decoration:underline; }
      main { flex:1; max-width:960px; margin:2rem auto; padding:2rem; }
      h2 { color:#2E7D32; text-align:center; margin-bottom:1.5rem; }
      form { background:#fff; border:1px solid #C8E6C9; border-radius:8px; padding:2rem; box-shadow:0 4px 12px rgba(0,0,0,0.05); }
      label { display:block; margin-bottom:8px; font-weight:500; color:#2E7D32; }
      input, textarea { width:100%; margin-bottom:12px; padding:10px; border:1px solid #B0BEC5; border-radius:4px; font-size:14px; }
      textarea { resize:vertical; }
      button { background:#2E7D32; color:white; border:none; padding:0.6rem 1.2rem; border-radius:4px; cursor:pointer; font-size:14px; }
      button:hover { background:#388E3C; }
      footer { background:#2E7D32; color:white; text-align:center; padding:1rem; font-size:14px; line-height:1.6; }
    </style>

    <header>
      <img src="/static/logo.png" alt="Hazmat Global Support Services Logo">
      <nav style="flex:1; display:flex; justify-content:flex-end; align-items:center;">
  <a href="/">Home</a>
  <a href="/embed/submit">Book a Collection</a>
  <a href="/embed/track">Track Shipments</a>
  <a href="/embed/complaint">File a Complaint</a>
  <a href="/embed/rate">Rate Our Services</a>
  <span id="client-nav" style="margin-left:auto; font-weight:600;"></span>
</nav>

<script>
  document.addEventListener("DOMContentLoaded", function() {
    fetch("/api/me")
      .then(res => res.json())
      .then(data => {
        const navSpan = document.getElementById("client-nav");
        if (data.name) {
          navSpan.innerText = data.name;   // ✅ show client’s name
        } else {
          navSpan.innerHTML = '<a href="/embed/login">Login / Sign Up</a>'; // ✅ fallback
        }
      })
      .catch(err => console.error("⚠️ Failed to fetch client info", err));
  });
</script>
    </header>

    <main>
      <h2>File a Complaint</h2>
      <form action="/embed/complaint" method="post">
        <label for="client_name">Your Name</label>
        <input type="text" id="client_name" name="client_name" required>

        <label for="client_email">Your Email</label>
        <input type="email" id="client_email" name="client_email" required>
        <label for="reference_number">Reference Number (optional)</label>
        <input type="text" id="reference_number" name="reference_number" placeholder="HAZJNB#">
        <label for="complaint">Complaint Details</label>
        <textarea id="complaint" name="complaint" rows="5" required></textarea>

        <button type="submit">Submit Complaint</button>
      </form>
    </main>

    <footer>
      <p><strong>Hazmat Global Support Services</strong></p>
      <p><strong>Contact Numbers:</strong> Johannesburg: +27 11 397 2000 | Port Elizabeth: +27 31 587 5241 | Durban: +27 55 897 5412 | Cape Town: +27 21 258 4587</p>
      <p><strong>Quotes & Support</strong> — Email: <a href="mailto:csd@hazglobal.com" style="color:white;">csd@hazglobal.com</a></p>
      <p>&copy; 2025 Hazmat Global Support Services. All rights reserved.</p>
    </footer>
    """


@app.post("/embed/rate", response_class=HTMLResponse)
async def submit_rating(request: Request):
    form = await request.form()
    client_name = form.get("client_name")
    client_email = form.get("client_email")
    rating = form.get("rating")
    comments = form.get("comments") or ""

    # Build email body
    body = f"""
    <html>
      <body>
        <p><strong>Service rating submitted by {client_name}</strong></p>
        <p><strong>Rating:</strong> {rating} / 5</p>
        {f"<p><strong>Comments:</strong> {comments}</p>" if comments else ""}
        <br>
        <p></p>
        {signature_block}
      </body>
    </html>
    """

    subject = f"Client Service Rating • {rating}/5"

    try:
        send_confirmation_email(
            to_email="hendrik.krueger@hazglobal.com",   # Ops Manager
            subject=subject,
            body=body,
            cc_email=client_email                      # Client copied
        )
    except Exception as e:
        print("❌ Rating email dispatch failed:", e)

    return HTMLResponse("""
    <html>
      <head>
        <title>Rating Submitted</title>
        <style>
          body { font-family: Segoe UI; background:#ECEFF1; text-align:center; padding:2rem; }
          .container { background:white; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.1); max-width:600px; margin:auto; padding:2rem; }
          h1 { color:#2E7D32; }
          .btn { display:inline-block; margin-top:1.5rem; padding:0.75rem 1.5rem; background-color:#388E3C; color:white; border:none; border-radius:6px; font-size:1rem; cursor:pointer; text-decoration:none; }
        </style>
      </head>
      <body>
        <div class="container">
          <h1>✅ Rating Submitted</h1>
          <p>Thank you for rating our services. Your feedback has been sent to our Operations Manager.</p>
          <p>You will receive a copy of the email for your records.</p>
          <a href="/" class="btn">Return to Home</a>
        </div>
      </body>
    </html>
    """)

@app.get("/embed/rate", response_class=HTMLResponse)
def embed_rate():
    return """
    <style>
      html, body { margin:0; padding:0; height:100%; background:#F1F8E9; font-family:'Segoe UI',sans-serif; display:flex; flex-direction:column; }
      header { background:#2E7D32; color:white; padding:1rem 2rem; display:flex; align-items:center; justify-content:space-between; }
      header img { height:60px; }
      nav a { color:white; margin-left:1rem; text-decoration:none; font-weight:500; }
      nav a:hover { text-decoration:underline; }
      main { flex:1; max-width:960px; margin:2rem auto; padding:2rem; }
      h2 { color:#2E7D32; text-align:center; margin-bottom:1.5rem; }
      form { background:#fff; border:1px solid #C8E6C9; border-radius:8px; padding:2rem; box-shadow:0 4px 12px rgba(0,0,0,0.05); }
      label { display:block; margin-bottom:8px; font-weight:500; color:#2E7D32; }
      input, select, textarea { width:100%; margin-bottom:12px; padding:10px; border:1px solid #B0BEC5; border-radius:4px; font-size:14px; }
      button { background:#2E7D32; color:white; border:none; padding:0.6rem 1.2rem; border-radius:4px; cursor:pointer; font-size:14px; }
      button:hover { background:#388E3C; }
      footer { background:#2E7D32; color:white; text-align:center; padding:1rem; font-size:14px; line-height:1.6; }
    </style>

    <header>
      <img src="/static/logo.png" alt="Hazmat Global Support Services Logo">
      <nav style="flex:1; display:flex; justify-content:flex-end; align-items:center;">
  <a href="/">Home</a>
  <a href="/embed/submit">Book a Collection</a>
  <a href="/embed/track">Track Shipments</a>
  <a href="/embed/complaint">File a Complaint</a>
  <a href="/embed/rate">Rate Our Services</a>
  <span id="client-nav" style="margin-left:auto; font-weight:600;"></span>
</nav>

<script>
  document.addEventListener("DOMContentLoaded", function() {
    fetch("/api/me")
      .then(res => res.json())
      .then(data => {
        const navSpan = document.getElementById("client-nav");
        if (data.name) {
          navSpan.innerText = data.name;   // ✅ show client’s name
        } else {
          navSpan.innerHTML = '<a href="/embed/login">Login / Sign Up</a>'; // ✅ fallback
        }
      })
      .catch(err => console.error("⚠️ Failed to fetch client info", err));
  });
</script>
    </header>

    <main>
      <h2>Rate Our Services</h2>
      <form action="/embed/rate" method="post">
      <label for="client_name">Your Name</label>
      <input type="text" id="client_name" name="client_name" required>
      <label for="client_email">Your Email</label>
      <input type="email" id="client_email" name="client_email" required>
        <label for="rating">Rating (1–5)</label>
        <select id="rating" name="rating" required>
          <option value="">Select a rating</option>
          <option value="1">1 - Very Poor</option>
          <option value="2">2 - Poor</option>
          <option value="3">3 - Average</option>
          <option value="4">4 - Good</option>
          <option value="5">5 - Excellent</option>
        </select>

        <label for="comments">Comments</label>
        <textarea id="comments" name="comments" rows="4" placeholder="Share your feedback..."></textarea>

        <button type="submit">Submit Rating</button>
      </form>
    </main>

    <footer>
      <p><strong>Hazmat Global Support Services</strong></p>
      <p><strong>Contact Numbers:</strong> Johannesburg: +27 11 397 2000 | Port Elizabeth: +27 31 587 5241 | Durban: +27 55 897 5412 | Cape Town: +27 21 258 4587</p>
      <p><strong>Quotes & Support</strong> — Email: <a href="mailto:csd@hazglobal.com" style="color:white;">csd@hazglobal.com</a></p>
      <p>&copy; 2025 Hazmat Global Support Services. All rights reserved.</p>
    </footer>
    """


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse("static/icon.png")


@app.get("/ping")
def ping():
    return {"status": "awake"}


@app.get("/ops/unassigned")
def get_unassigned():
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT reference_number, collection_company, collection_address, pickup_date
        FROM requests WHERE assigned_driver IS NULL AND status IS NOT 'Delivered'
        ORDER BY timestamp DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{"hazjnb_ref": r[0], "company": r[1], "address": r[2], "pickup_date": r[3]} for r in rows]


@app.post("/client/addresses")
async def save_address(request: Request, payload: dict):
    # get client_id from cookie
    client_id = request.cookies.get("client_id")
    if not client_id:
        return {"status": "error", "message": "Not logged in"}

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO saved_addresses (client_id, label, type, company, address, contact_person, contact_number, email)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (client_id, payload.get("label"), payload.get("type"),
         payload.get("company"), payload.get("address"),
         payload.get("contact_person"), payload.get("contact_number"), payload.get("email"))
    )
    conn.commit()
    conn.close()
    return {"status": "saved"}


@app.get("/client/addresses")
async def list_addresses(request: Request):
    client_id = request.cookies.get("client_id")
    if not client_id:
        return []

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, label, type, company, address, contact_person, contact_number, email FROM saved_addresses WHERE client_id=?",
        (client_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "label": r[1],
            "type": r[2],
            "company": r[3],
            "address": r[4],
            "contact_person": r[5],
            "contact_number": r[6],
            "email": r[7],
        }
        for r in rows
    ]


@app.get("/client/addresses/{address_id}")
async def get_address(address_id: int, request: Request):
    client_id = request.cookies.get("client_id")
    if not client_id:
        return {}

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, label, type, company, address, contact_person, contact_number, email FROM saved_addresses WHERE client_id=? AND id=?",
        (client_id, address_id)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {}
    return {
        "id": row[0],
        "label": row[1],
        "type": row[2],
        "company": row[3],
        "address": row[4],
        "contact_person": row[5],
        "contact_number": row[6],
        "email": row[7],
    }

@app.get("/ops/collections")
def get_available_collections():
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT reference_number, collection_company, collection_address, pickup_date
        FROM requests
        WHERE assigned_driver IS NULL AND status IS NOT 'Delivered'
        ORDER BY timestamp DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{
        "hazjnb_ref": r[0],
        "company": r[1],
        "address": r[2],
        "pickup_date": r[3]
    } for r in rows]


@app.get("/embed/submit", response_class=HTMLResponse)
def embed_submit_form():
    today = date.today().isoformat()
    return f"""
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
      html, body {{
        margin: 0;
        padding: 0;
        height: 100%;
        background: #F1F8E9;
        font-family: 'Inter', sans-serif;
        display: flex;
        flex-direction: column;
      }}
      header {{
        font-family: 'Segoe UI', sans-serif;
        font-size: 16px;
        line-height: 1.6; 
        background: #2E7D32;
        color: white;
        padding: 1rem 2rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }}
      header img {{ height: 60px; }}
      nav a {{
        color: white;
        margin-left: 1rem;
        text-decoration: none;
        font-weight: 500;
      }}
      nav a:hover {{ text-decoration: underline; }}
      main {{
        flex: 1;
        max-width: 1200px;
        margin: 2rem auto;
        padding: 1rem;
      }}
      h2 {{
        text-align: center;
        color: #2E7D32;
        margin-bottom: 2rem;
      }}
      .form-wrapper {{ width: 100%; box-sizing: border-box; }}
      .form-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }}
      .form-block {{
        background: #fff;
        border: 1px solid #C8E6C9;
        border-radius: 8px;
        padding: 2rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
      }}
      h3 {{ margin: 0 0 1rem 0; color: #2E7D32; }}
      label {{ display: block; margin-top: 1rem; font-weight: 600; color: #2E7D32; }}
      input, select, textarea {{
        width: 100%;
        padding: 0.5rem;
        margin-top: 0.5rem;
        border: 1px solid #B0BEC5;
        border-radius: 4px;
        background-color: #fff;
        font-size: 14px;
      }}
      textarea {{ resize: none; }}
      .address-block {{ height: 150px; resize: none; }}
      .shipment-block {{ grid-column: span 2; }}
      .piece-row {{ display: flex; gap: 1rem; margin-top: 1rem; flex-wrap: wrap; }}
      .piece-row input {{ flex: 1; min-width: 120px; }}
      .add-piece {{
        margin-top: 1rem;
        background: #2E7D32;
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        border-radius: 4px;
        cursor: pointer;
      }}
      button[type="submit"] {{
        margin-top: 2rem;
        padding: 0.75rem 1.5rem;
        background-color: #388E3C;
        color: white;
        border: none;
        border-radius: 4px;
        font-size: 1rem;
        cursor: pointer;
      }}
      button[type="submit"]:hover {{ background-color: #2E7D32; }}
      #collection_date {{ width: 200px; }}
      .missing-field {{
        border: 2px solid red !important;
        background-color: #fff8f8 !important;
      }}
      footer {{
        background: #2E7D32;
        color: white;
        text-align: center;
        padding: 1rem;
        font-size: 14px;
        line-height: 1.6;
      }}
    </style>

    <header>
      <img src="/static/logo.png" alt="Hazmat Global Support Services Logo">
      <nav style="flex:1; display:flex; justify-content:flex-end; align-items:center;">
        <a href="/">Home</a>
        <a href="/embed/submit">Book a Collection</a>
        <a href="/embed/track">Track Shipments</a>
        <a href="/embed/complaint">File a Complaint</a>
        <a href="/embed/rate">Rate Our Services</a>
        <span id="client-nav" style="margin-left:auto; font-weight:600;"></span>
      </nav>
      <script>
        document.addEventListener("DOMContentLoaded", function() {{
          fetch("/api/me")
            .then(res => res.json())
            .then(data => {{
              const navSpan = document.getElementById("client-nav");
              if (data.name) {{
                navSpan.innerText = data.name;
              }} else {{
                navSpan.innerHTML = '<a href="/embed/login">Login / Sign Up</a>';
              }}
            }})
            .catch(err => console.error("⚠️ Failed to fetch client info", err));
        }});
      </script>
    </header>

    <main>
      <h2>Book a Hazmat Collection</h2>
      <div class="form-wrapper">
        <form id="hazmat-form" action="/submit" method="post" enctype="multipart/form-data">
          <div class="form-grid">

            <!-- Shipment Section -->
            <div class="form-block shipment-block">
              <h3>Shipment Information</h3>
              <label for="saved_contact">Select Saved Contact</label>
              <select id="saved_contact" name="saved_contact">
                <option value="">-- Choose from saved contacts --</option>
              </select>
              <button type="button" onclick="loadContact()">Load Contact</button>
              <label>Shipment Type</label>
              <select name="shipment_type" id="shipment_type">
                <option value="local" selected>Local</option>
                <option value="export">Export</option>
                <option value="import">Import</option>
              </select>

              <label>Inco Terms</label>
              <select name="inco_terms_display" id="inco_terms" disabled>
                <option value="DTD" selected>DTD</option>
                <option value="DDU">DDU</option>
                <option value="DDP">DDP</option>
                <option value="DAP">DAP</option>
                <option value="CPT">CPT</option>
                <option value="FOB">FOB</option>
                <option value="CIP">CIP</option>
                <option value="CIF">CIF</option>
              </select>
              <input type="hidden" name="inco_terms" id="inco_terms_hidden" value="DTD">
              <label style="display: inline-flex; align-items: center; gap: 8px;">
              <input type="checkbox" id="quoted" name="quoted" onchange="toggleSalesRep()"> Quoted
              </label>

<div id="sales-rep-block" style="display:none; margin-top:10px;">
  <label for="sales_rep">Select Sales Rep</label>
  <select id="sales_rep" name="sales_rep">
    <option value="">-- Select a Sales Rep --</option>
    <option value="caitlin@hazglobal.com">Caitlin Kotze</option>
    <option value="maxine@hazglobal.com">Maxine Gomez</option>
    <option value="chane@hazglobal.com">Chane Botes</option>
    <option value="nicky@hazglobal.com">Nicky van der Westhuizen</option>
  </select>
</div>

<script>
function toggleSalesRep() {{
  const quoted = document.getElementById("quoted").checked;
  document.getElementById("sales-rep-block").style.display = quoted ? "block" : "none";
}}
</script>

              <label>Collection Date</label>
              <input type="date" id="collection_date" name="collection_date" value="{today}">

              <label>Shipment Details</label>
              <div id="pieces">
                <div class="piece-row">
                  <input type="number" name="length[]" placeholder="Length (cm)">
                  <input type="number" name="width[]" placeholder="Width (cm)">
                  <input type="number" name="height[]" placeholder="Height (cm)">
                  <input type="number" name="weight[]" placeholder="Weight (kg)">
                  <input type="number" name="quantity[]" placeholder="Quantity">
                </div>
              </div>
              <button type="button" class="add-piece" onclick="addPiece()">+ Add Piece</button>

              <label>Shipper Notes</label>
              <textarea name="shipper_notes"></textarea>

              <label>Upload Documents</label>
              <div class="file-wrapper">
                <input type="file" name="shipment_docs" multiple>
              </div>
            </div>

            <!-- Collection Section -->
            <div class="form-block">
              <h3>Collection Details</h3>
              <label>Company Name</label>
              <input type="text" name="collection_company">
              <label>Collection Address</label>
              <textarea name="collection_address" class="address-block"></textarea>
              <div id="collection_region_wrapper">
                <label>Region</label>
                <select id="collection_region" name="collection_region">
                  <option value="Johannesburg">Johannesburg</option>
                  <option value="Durban">Durban</option>
                  <option value="Cape Town">Cape Town</option>
                  <option value="Port Elizabeth">Port Elizabeth</option>
                </select>
                <input id="collection_region_import" type="text" value="Import" disabled style="background:#ECEFF1; display:none;">
              </div>
                            <label>Contact Name</label>
              <input type="text" name="collection_contact_name">
              <label>Contact Number</label>
              <input type="text" name="collection_contact_number">
              <label>Email Addresses (comma separated)</label>
              <input type="text" name="collection_email">
              <button type="button" onclick="saveContact('collection')">Save Collection Contact</button>
            </div>

            <!-- Delivery Section -->
            <div class="form-block">
              <h3>Delivery Details</h3>
              <label>Company Name</label>
              <input type="text" name="delivery_company">
              <label>Delivery Address</label>
              <textarea name="delivery_address" class="address-block"></textarea>
              <div id="delivery_region_wrapper" style="display:none;">
                <label>Region</label>
                <select id="delivery_region" name="delivery_region">
                  <option value="Johannesburg">Johannesburg</option>
                  <option value="Port Elizabeth">Port Elizabeth</option>
                  <option value="Durban">Durban</option>
                  <option value="Cape Town">Cape Town</option>
                </select>
              </div>
              <label>Contact Name</label>
              <input type="text" name="delivery_contact_name">
              <label>Contact Number</label>
              <input type="text" name="delivery_contact_number">
              <label>Email Addresses (comma separated)</label>
              <input type="text" name="delivery_email">
              <button type="button" onclick="saveContact('delivery')">Save Delivery Contact</button>
            </div>

          </div>
          <button type="submit">Submit Collection Request</button>
          <script>
        // ✅ Inline helper for sending confirmation email after booking
        function sendConfirmationEmail(to, subject, body) {{
          fetch("/api/send_email", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},            
            body: JSON.stringify({{ to, subject, body }})
          }})
          .then(res => res.json())
          .then(data => {{
            if (data.status === "ok") {{
              console.log("✅ Confirmation email sent");
            }} else {{
              console.error("❌ Email failed:", data.message);
            }}
          }})
          .catch(err => console.error("❌ Email dispatch error:", err));
        }}
        </script>


        </form>
      </div>
    </main>

    <footer>
      <p><strong>Hazmat Global Support Services</strong></p>
      <p><strong>Contact Numbers:</strong> Johannesburg: +27 11 397 2000 | Port Elizabeth: +27 31 587 5241 | Durban: +27 55 897 5412 | Cape Town: +27 21 258 4587</p>
      <p><strong>Quotes & Support</strong> — Email: <a href="mailto:csd@hazglobal.com" style="color:white;">csd@hazglobal.com</a></p>
      <p>&copy; 2025 Hazmat Global Support Services. All rights reserved.</p>
    </footer>

    <script>
    let clientId = null;

    document.addEventListener("DOMContentLoaded", function() {{
      fetch("/api/me")
        .then(res => res.json())
        .then(data => {{
          clientId = data.id;
          loadSavedContacts();
        }});
    }});

    function loadSavedContacts() {{
      fetch("/client/addresses")
        .then(res => res.json())
        .then(data => {{
          const select = document.getElementById("saved_contact");
          select.innerHTML = '<option value="">-- Choose from saved contacts --</option>';
          data.forEach(contact => {{
            select.innerHTML += `<option value="${{contact.id}}">${{contact.label}} (${{contact.company}})</option>`;
          }});
        }});
    }}

    function saveContact(type) {{
      let contact = {{}};
      if (type === 'collection') {{
        contact = {{
          company: document.querySelector('[name="collection_company"]').value,
          address: document.querySelector('[name="collection_address"]').value,
          contact_person: document.querySelector('[name="collection_contact_name"]').value,
          contact_number: document.querySelector('[name="collection_contact_number"]').value,
          email: document.querySelector('[name="collection_email"]').value
        }};
      }} else if (type === 'delivery') {{
        contact = {{
          company: document.querySelector('[name="delivery_company"]').value,
          address: document.querySelector('[name="delivery_address"]').value,
          contact_person: document.querySelector('[name="delivery_contact_name"]').value,
          contact_number: document.querySelector('[name="delivery_contact_number"]').value,
          email: document.querySelector('[name="delivery_email"]').value
        }};
      }}

      fetch("/client/addresses", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          label: type + "_contact",
          type: type,
          ...contact
        }})
      }})
      .then(res => res.json())
      .then(data => {{
        alert("✅ Contact saved");
        loadSavedContacts();
      }})
      .catch(err => {{
        alert("⚠️ Failed to save contact");
        console.error(err);
      }});
    }}

    function loadContact() {{
      const selectedId = document.getElementById("saved_contact").value;
      if (!selectedId) return;

      fetch("/client/addresses/" + selectedId)
        .then(res => res.json())
        .then(data => {{
          if (data.type === "collection") {{
            document.querySelector('[name="collection_company"]').value = data.company;
            document.querySelector('[name="collection_address"]').value = data.address;
            document.querySelector('[name="collection_contact_name"]').value = data.contact_person;
            document.querySelector('[name="collection_contact_number"]').value = data.contact_number;
            document.querySelector('[name="collection_email"]').value = data.email || "";
          }} else if (data.type === "delivery") {{
            document.querySelector('[name="delivery_company"]').value = data.company;
            document.querySelector('[name="delivery_address"]').value = data.address;
            document.querySelector('[name="delivery_contact_name"]').value = data.contact_person;
            document.querySelector('[name="delivery_contact_number"]').value = data.contact_number;
            document.querySelector('[name="delivery_email"]').value = data.email || "";
          }}
        }});
    }}

    function addPiece() {{
      var container = document.getElementById('pieces');
      var row = document.createElement('div');
      row.className = 'piece-row';
      row.innerHTML =
        '<input type="number" name="length[]" placeholder="Length (cm)">' +
        '<input type="number" name="width[]" placeholder="Width (cm)">' +
        '<input type="number" name="height[]" placeholder="Height (cm)">' +
        '<input type="number" name="weight[]" placeholder="Weight (kg)">' +
        '<input type="number" name="quantity[]" placeholder="Quantity">';
      container.appendChild(row);
    }}

    document.addEventListener("DOMContentLoaded", function () {{
      const incoSelect = document.getElementById("inco_terms");
      const incoHidden = document.getElementById("inco_terms_hidden");
      const shipmentType = document.getElementById("shipment_type");
      const colSelect = document.getElementById("collection_region");
      const colImport = document.getElementById("collection_region_import");
      const delWrap = document.getElementById("delivery_region_wrapper");

      incoSelect.addEventListener("change", function () {{
        incoHidden.value = this.value;
      }});

      shipmentType.addEventListener("change", function () {{
        if (this.value === "local") {{
          incoSelect.value = "DTD";
          incoHidden.value = "DTD";
          incoSelect.disabled = true;
          if (!document.querySelector('#inco_terms option[value="DTD"]')) {{
            incoSelect.insertAdjacentHTML('afterbegin','<option value="DTD">DTD</option>');
          }}
          colSelect.style.display = "block";
          colImport.style.display = "none";
          delWrap.style.display = "block";
        }} else if (this.value === "export") {{
          incoSelect.disabled = false;
          incoHidden.value = incoSelect.value;
          let dtdOption = document.querySelector('#inco_terms option[value="DTD"]');
          if (dtdOption) dtdOption.remove();
          colSelect.style.display = "block";
          colImport.style.display = "none";
          delWrap.style.display = "none";
        }} else if (this.value === "import") {{
          incoSelect.disabled = false;
          incoHidden.value = incoSelect.value;
          let dtdOption = document.querySelector('#inco_terms option[value="DTD"]');
          if (dtdOption) dtdOption.remove();
          colSelect.style.display = "none";
          colImport.style.display = "block";
          delWrap.style.display = "block";
        }}
      }});

      document.getElementById("hazmat-form").addEventListener("submit", function (e) {{
        let requiredFields = [
          "collection_company", "collection_address", "collection_contact_name",
          "collection_contact_number", "collection_email",
          "delivery_company", "delivery_address", "delivery_contact_name",
          "delivery_contact_number", "delivery_email"
        ];

        let valid = true;

        requiredFields.forEach(function(name) {{
          let el = document.querySelector('[name="' + name + '"]');
          if (el && !el.value.trim()) {{
            el.classList.add("missing-field");
            valid = false;
          }} else if (el) {{
            el.classList.remove("missing-field");
          }}
        }});

                let docs = document.querySelector('[name="shipment_docs"]');
        if (!docs || docs.files.length === 0) {{
          docs.classList.add("missing-field");
          valid = false;
        }} else {{
          docs.classList.remove("missing-field");
        }}

        let pieceRows = document.querySelectorAll("#pieces .piece-row");
        pieceRows.forEach(row => {{
          row.querySelectorAll("input").forEach(input => {{
            if (!input.value.trim()) {{
              input.classList.add("missing-field");
              valid = false;
            }} else {{
              input.classList.remove("missing-field");
            }}
          }});
        }});

        if (!valid) {{
          e.preventDefault();
          alert("Please fill in all required fields, including shipment details and documents.");
        }}
      }});
    }});
    </script>
    """

@app.post("/embed/complaint", response_class=HTMLResponse)
async def submit_complaint(request: Request):
    form = await request.form()
    client_name = form.get("client_name")
    client_email = form.get("client_email")
    reference_number = form.get("reference_number") or ""
    complaint_text = form.get("complaint")

    body = f"""
    <html>
      <body>
        <p><strong>Complaint received from {client_name}</strong></p>
        {f"<p><strong>Reference:</strong> {reference_number}</p>" if reference_number else ""}  
        <p><strong>Complaint:</strong></p>
        <p>{complaint_text}</p>
        <br>        
        {signature_block}
      </body>
    </html>
    """

    try:
        send_confirmation_email(
            to_email="hendrik.krueger@hazglobal.com",   # Ops Manager
            subject = f"Client Complaint{f' • Ref {reference_number}' if reference_number else ''}",
            body=body,
            cc_email=client_email                      # Client copied
        )
    except Exception as e:
        print("❌ Complaint email dispatch failed:", e)

    return HTMLResponse("""
    <html>
      <head>
        <title>Complaint Submitted</title>
        <style>
          body { font-family: Segoe UI; background:#ECEFF1; text-align:center; padding:2rem; }
          .container { background:white; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.1); max-width:600px; margin:auto; padding:2rem; }
          h1 { color:#2E7D32; }
          .btn { display:inline-block; margin-top:1.5rem; padding:0.75rem 1.5rem; background-color:#388E3C; color:white; border:none; border-radius:6px; font-size:1rem; cursor:pointer; text-decoration:none; }
        </style>
      </head>
      <body>
        <div class="container">
          <h1>✅ Complaint Submitted</h1>
          <p>Your complaint has been logged and sent to our Operations Manager.</p>
          <p>You will receive a copy of the email for your records.</p>
          <a href="/" class="btn">Return to Home</a>
        </div>
      </body>
    </html>
    """)



@app.get("/ops/assigned", response_class=HTMLResponse)
def ops_assigned():
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, reference_number, service_type, collection_company, delivery_company,
               assigned_driver, status, timestamp
        FROM requests
        WHERE assigned_driver IS NOT NULL
        ORDER BY timestamp DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    # Build HTML table rows
    table_rows = ""
    for r in rows:
        table_rows += f"""
        <tr>
          <td>{r[1]}</td>
          <td>{r[2]}</td>
          <td>{r[3]}</td>
          <td>{r[4]}</td>
          <td>{r[5]}</td>
          <td>{r[6]}</td>
          <td>{r[7]}</td>
        </tr>
        """

    return f"""
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
      body {{
        margin: 0; padding: 0; font-family: 'Inter', sans-serif;
        background: #F1F8E9; color: #333;
      }}
      header {{
        background: #2E7D32; color: white; padding: 1rem 2rem;
        display: flex; align-items: center; justify-content: space-between;
      }}
      header img {{ height: 60px; }}
      nav a {{
        color: white; margin-left: 1rem; text-decoration: none; font-weight: 500;
      }}
      nav a:hover {{ text-decoration: underline; }}
      main {{ max-width: 1200px; margin: 2rem auto; padding: 1rem; }}
      h2 {{ text-align: center; color: #2E7D32; margin-bottom: 2rem; }}
      table {{
        width: 100%; border-collapse: collapse; background: #fff;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
      }}
      th, td {{
        border: 1px solid #C8E6C9; padding: 0.75rem; text-align: left;
      }}
      th {{ background: #388E3C; color: white; }}
      tr:nth-child(even) {{ background: #F9FBE7; }}
      footer {{
        background: #2E7D32; color: white; text-align: center;
        padding: 1rem; font-size: 14px; line-height: 1.6;
      }}
    </style>

    <header>
      <img src="/static/logo.png" alt="Hazmat Global Support Services Logo">
      <nav style="flex:1; display:flex; justify-content:flex-end; align-items:center;">
        <a href="/">Home</a>
        <a href="/embed/submit">Book a Collection</a>
        <a href="/embed/track">Track Shipments</a>
        <a href="/embed/complaint">File a Complaint</a>
        <a href="/embed/rate">Rate Our Services</a>
        <span id="client-nav" style="margin-left:auto; font-weight:600;"></span>
      </nav>
    </header>

    <main>
      <h2>Assigned Shipments</h2>
      <table>
        <thead>
          <tr>
            <th>Reference #</th>
            <th>Service Type</th>
            <th>Collection Company</th>
            <th>Delivery Company</th>
            <th>Assigned Driver</th>
            <th>Status</th>
            <th>Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {table_rows if table_rows else '<tr><td colspan="7">No assigned shipments found.</td></tr>'}
        </tbody>
      </table>
    </main>

    <footer>
      <p>&copy; 2025 Hazmat Global Support Services. All rights reserved.</p>
    </footer>

    <script>
    document.addEventListener("DOMContentLoaded", function() {{
      fetch("/api/me")
        .then(res => res.json())
        .then(data => {{
          const navSpan = document.getElementById("client-nav");
          if (data.name) {{
            navSpan.innerText = data.name;
          }} else {{
            navSpan.innerHTML = '<a href="/embed/login">Login / Sign Up</a>';
          }}
        }});
    }});
    </script>
    """


@app.get("/driver/{code}")
def get_driver_jobs(code: str):
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT reference_number, collection_company, collection_address, pickup_date
        FROM requests WHERE assigned_driver = ?
    """, (code,))
    rows = cursor.fetchall()
    conn.close()
    return [{"hazjnb_ref": r[0], "company": r[1], "address": r[2], "pickup_date": r[3]} for r in rows]


@app.post("/scan_qr")
def scan_qr(payload: dict):
    ref = payload.get("ref")
    driver_id = payload.get("driver_id")
    timestamp = datetime.now().isoformat()
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO scan_log (reference_number, driver_id, timestamp) VALUES (?, ?, ?)
    """, (ref, driver_id, timestamp))
    cursor.execute("""
        UPDATE requests SET status = 'Collected' WHERE reference_number = ?
    """, (ref,))
    conn.commit()
    conn.close()
    return {"status": "collected", "ref": ref, "driver": driver_id}


@app.post("/ops/updates")
def submit_update(payload: dict):
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO updates (ops, hmj, haz, company, date, time, update)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        payload["ops"], payload["hmj"], payload["haz"], payload["company"],
        payload["date"], payload["time"], payload["update"]
    ))
    conn.commit()
    conn.close()
    backup_database()
    return {"status": "update received"}


@app.get("/ops/updates")
def get_updates():
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute('SELECT ops, hmj, haz, company, date, time, "update" FROM updates ORDER BY id DESC')
    rows = cursor.fetchall()
    conn.close()
    return [{"ops": r[0], "hmj": r[1], "haz": r[2], "company": r[3], "date": r[4], "time": r[5], "update": r[6]} for r
            in rows]


@app.post("/ops/completed")
def submit_completed(payload: dict):
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO completed (ops, company, delivery_date, time, signed_by, document, pod)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        payload["ops"], payload["company"], payload["delivery_date"], payload["time"],
        payload["signed_by"], payload["document"], payload["pod"]
    ))
    cursor.execute("""
        UPDATE requests SET status = 'Delivered' WHERE reference_number = ?
    """, (payload["haz_ref"],))
    conn.commit()
    conn.close()
    backup_database()
    return {"status": "completed"}


@app.get("/ops/completed")
def get_completed():
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT ops, company, delivery_date, time, signed_by, document, pod FROM completed ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [{"ops": r[0], "company": r[1], "delivery_date": r[2], "time": r[3], "signed_by": r[4], "document": r[5],
             "pod": r[6]} for r in rows]


# NEW: email helper — attaches waybill + all uploaded docs, sends from jnb@hazglobal.com
def send_confirmation_email(to_email, subject, body, attachments=None, cc_email=None):
    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    if cc_email:
        msg["Cc"] = cc_email
    msg["Subject"] = subject
    with open("static/logo.png", "rb") as f:
        logo = MIMEImage(f.read())
        logo.add_header("Content-ID", "<hazmatlogo>")
        msg.attach(logo)
    msg.attach(MIMEText(body, "html"))

    # Attach files
    if attachments:
        for path in attachments:
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(path)}")
            msg.attach(part)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


@app.post("/submit")
async def submit(request: Request):
    form = await request.form()
    required_fields = [
        "shipment_type", "inco_terms", "collection_date",
        "collection_company", "collection_address", "collection_region",
        "collection_contact_name", "collection_contact_number", "collection_email",
        "delivery_company", "delivery_address", "delivery_contact_name",
        "delivery_contact_number", "delivery_email"
    ]

    missing = [field for field in required_fields if not form.get(field)]
    if missing or not form.getlist("shipment_docs"):
        return HTMLResponse(
            content=f"<h3>Missing required fields: {', '.join(missing)}</h3>",
            status_code=400
        )
    # Files
    uploaded_files = form.getlist("shipment_docs")

    # Core fields (match current frontend names exactly)
    service_type = form.get("shipment_type") or form.get("serviceType")  # support both if present
    inco_terms = form.get("inco_terms") if service_type != "local" else "DTD"

    # Collection
    collection_company = form.get("collection_company") or ""
    collection_address = form.get("collection_address") or ""
    collection_region = form.get("collection_region") or ""
    collection_person = form.get("collection_contact_name") or ""
    collection_number = form.get("collection_contact_number") or ""
    collection_email_raw = form.get("collection_email") or ""

    # Delivery
    delivery_company = form.get("delivery_company") or ""
    delivery_address = form.get("delivery_address") or ""
    delivery_person = form.get("delivery_contact_name") or ""
    delivery_number = form.get("delivery_contact_number") or ""
    delivery_email_raw = form.get("delivery_email") or ""

    # ✅ Split multiple emails (comma separated)
    collection_emails = [e.strip() for e in collection_email_raw.split(",") if e.strip()]
    delivery_emails = [e.strip() for e in delivery_email_raw.split(",") if e.strip()]

    # Shipment
    collection_date = form.get("collection_date") or ""  # maps to DB pickup_date
    client_reference = form.get("client_reference") or ""
    client_notes = form.get("shipper_notes") or ""

    timestamp = datetime.now().isoformat()
    reference_number = get_next_reference_number()

    # Insert into DB
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO requests (
            reference_number, service_type, collection_company, collection_address, collection_person, collection_number,
            delivery_company, delivery_address, delivery_person, delivery_number,
            client_reference, pickup_date, inco_terms, client_notes, pdf_path, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        reference_number, service_type, collection_company, collection_address, collection_person, collection_number,
        delivery_company, delivery_address, delivery_person, delivery_number,
        client_reference, collection_date, inco_terms, client_notes, "", timestamp
    ))
    request_id = cursor.lastrowid
    conn.commit()
    conn.close()
    backup_database()

    # Save uploaded files and collect paths (for email attachments)
    uploaded_paths = []
    for file in uploaded_files:
        contents = await file.read()
        save_path = f"static/uploads/{reference_number}_{file.filename}"
        with open(save_path, "wb") as f:
            f.write(contents)
        uploaded_paths.append(save_path)

    # QR code
    qr_url = f"https://hazmat-collection.onrender.com/confirm/{reference_number}"
    qr_img = qrcode.make(qr_url)
    qr_path = f"static/qrcodes/qr_{request_id}.png"
    qr_img.save(qr_path)

    # Generate PDF
    pdf_path = f"static/waybills/waybill_{request_id}.pdf"
    generate_pdf({
        "reference_number": reference_number,
        "service_type": service_type,
        "client_reference": client_reference,
        "pickup_date": collection_date,
        "inco_terms": inco_terms,
        "collection_company": collection_company,
        "collection_address": collection_address,
        "collection_region": collection_region,
        "collection_person": collection_person,
        "collection_number": collection_number,
        # ✅ join multiple emails for PDF
        "collection_email": ", ".join(collection_emails),
        "delivery_company": delivery_company,
        "delivery_address": delivery_address,
        "delivery_person": delivery_person,
        "delivery_number": delivery_number,
        # ✅ join multiple emails for PDF
        "delivery_email": ", ".join(delivery_emails),
        "client_notes": client_notes
    }, request_id, qr_path, pdf_path)

    # Update DB with pdf path
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET pdf_path = ? WHERE id = ?", (pdf_path, request_id))
    conn.commit()
    conn.close()
    backup_database()

    # ✅ Always include ops team
    OPS_CC = ["hendrik.krueger@hazglobal.com"]  # <-- add your ops email(s) here

    # Merge all recipients
    recipients = collection_emails + delivery_emails
    quoted = form.get("quoted")  # will be "on" if checkbox ticked
    sales_rep_email = form.get("sales_rep") or ""

    # Build CC list
    cc_list = OPS_CC.copy()
    if quoted and sales_rep_email:
        cc_list.append(sales_rep_email)

    if recipients:
        subject = f"Hazmat Collection Confirmation • {reference_number}"
        body = f""""
        <html>
  <body>
    <p>Dear {collection_person},</p>

    <p>Your collection has been booked successfully.</p>

    <ul>
      <li><strong>Reference:</strong> {reference_number}</li>
      <li><strong>Collection Date:</strong> {collection_date}</li>
      <li><strong>Company:</strong> {collection_company}</li>
      <li><strong>Address:</strong> {collection_address}</li>
      <li><strong>Contact:</strong> {collection_number}</li>
      <li><strong>Email:</strong> {collection_email_raw}</li>
    </ul>    
    {signature_block}
  </body>
</html>
"""


        attachments = [pdf_path] + uploaded_paths
        try:
            # ✅ Pass full list of recipients, plus ops CC
            send_confirmation_email(
                to_email=", ".join(recipients),  # join list into comma-separated string
                subject=subject,
                body=body,
                attachments=attachments,
                cc_email=", ".join(cc_list)  # join CC list if needed
            )
        except Exception as e:
            print("❌ Email dispatch failed:", e)
    else:
        print("⚠️ No client email provided; skipping confirmation email.")

    # Overlay response
    return HTMLResponse(f"""
    <html>
      <head>
        <title>Waybill Generated</title>
        <link href="https://fonts.googleapis.com/css2?family=Segoe+UI&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
        <style>
          body {{
            font-family: 'Segoe UI', sans-serif;
            background: #F5F7FA;
            color: #333;
            text-align: center;
            padding: 3rem;
          }}
          .container {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            max-width: 600px;
            margin: auto;
            padding: 2rem;
          }}
          h1 {{
            color: #D32F2F;
            font-size: 2rem;
            margin-bottom: 1rem;
          }}
          p {{
            font-size: 1.1rem;
            margin-bottom: 2rem;
          }}
          .btn {{
            display: inline-block;
            margin: 0.5rem;
            padding: 0.75rem 1.5rem;
            font-size: 1rem;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            text-decoration: none;
            color: white;
          }}
          .btn-primary {{
            background-color: #1976D2;
          }}
          .btn-success {{
            background-color: #388E3C;
          }}
          .btn i {{
            margin-right: 8px;
          }}
        </style>
      </head>
      <body>
        <div class="container">
          <h1>✅ Waybill Generated</h1>
          <p>Your waybill is ready. You can view or download it below.</p>
          <a href="/pdf/{request_id}" target="_blank" class="btn btn-primary">
            <i class="fas fa-file-pdf"></i> View Waybill PDF
          </a>
          <a href="/" class="btn btn-success">
            <i class="fas fa-check-circle"></i> Continue
          </a>
        </div>
      </body>
    </html>
    """)

@app.get("/pdf/{request_id}")
def serve_pdf(request_id: int):
    path = f"static/waybills/waybill_{request_id}.pdf"
    file = open(path, "rb")
    return StreamingResponse(
        file,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="waybill_{request_id}.pdf"'}
    )


@app.get("/thankyou", response_class=HTMLResponse)
def thank_you():
    return HTMLResponse("""
    <html><body style="font-family:Segoe UI; text-align:center; padding:2rem;">
        <h1 style="color:#388E3C;">Thank you! Your request has been submitted.</h1>
        <button onclick="window.location.href='/'" style="margin:1rem; padding:0.75rem 1.5rem; background-color:#D32F2F; color:white; border:none; border-radius:4px;">Book Another Collection</button>
        <button onclick="window.location.href='/track'" style="margin:1rem; padding:0.75rem 1.5rem; background-color:#455A64; color:white; border:none; border-radius:4px;">Track a Collection</button>
    </body></html>
    """)


# ✅ QR confirmation now uses HAZJNB reference
@app.get("/confirm/{hazjnb_ref}", response_class=HTMLResponse)
def confirm(hazjnb_ref: str):
    return HTMLResponse(f"<h1>Driver confirmed request {hazjnb_ref}</h1>")


@app.post("/assign")
def assign_collection(payload: dict):
    driver_code = payload.get("driver_code")
    hazjnb_ref = payload.get("hazjnb_ref")

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()

    # Log incoming request
    print(f"🚨 Assigning driver {driver_code} to reference {hazjnb_ref}")

    # Run update
    cursor.execute("""
        UPDATE requests SET assigned_driver = ?, status = 'Assigned' WHERE reference_number = ?
    """, (driver_code, hazjnb_ref))

    conn.commit()
    affected = cursor.rowcount
    conn.close()

    # Log result
    if affected == 0:
        print(f"❌ No matching reference_number found for {hazjnb_ref}")
        return JSONResponse(content={"status": "error", "message": "Reference not found"}, status_code=404)

    print(f"✅ Assignment succeeded for {hazjnb_ref}")
    return {"status": "success", "driver": driver_code, "ref": hazjnb_ref}


@app.get("/driver/{code}")
def get_driver_jobs(code: str):
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT reference_number, collection_company, collection_address, pickup_date
        FROM requests WHERE assigned_driver = ?
    """, (code,))
    rows = cursor.fetchall()
    conn.close()

    jobs = []
    for row in rows:
        jobs.append({
            "hazjnb_ref": row[0],
            "company": row[1],
            "address": row[2],
            "pickup_date": row[3]
        })

    return jobs


@app.get("/ops/backup")
def trigger_backup():
    backup_database()
    return {"status": "backup complete"}


@app.post("/scan_qr")
def scan_qr(payload: dict):
    ref = payload.get("ref")
    driver_id = payload.get("driver_id")
    timestamp = datetime.now().isoformat()

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()

    # Log scan
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_number TEXT,
            driver_id TEXT,
            timestamp TEXT
        )
    """)
    cursor.execute("""
        INSERT INTO scan_log (reference_number, driver_id, timestamp)
        VALUES (?, ?, ?)
    """, (ref, driver_id, timestamp))

    # Update status
    cursor.execute("""
        UPDATE requests SET status = 'Collected' WHERE reference_number = ?
    """, (ref,))

    conn.commit()
    conn.close()

    print(f"✅ QR scan logged and status updated for {ref}")
    return {"status": "collected", "ref": ref, "driver": driver_id}


def generate_pdf(data, request_id, qr_path, pdf_path):
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    # Background
    c.setFillColor(HexColor("#ECEFF1"))
    c.rect(0, 0, width, height, fill=1)

    # Logo
    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 20 * mm, height - 30 * mm,
                    width=40 * mm, height=20 * mm,
                    preserveAspectRatio=True, mask='auto')

    # Title
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(HexColor("#D32F2F"))
    c.drawString(70 * mm, height - 25 * mm, "Hazmat Collection Waybill")

    def section(title, y):
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(HexColor("#455A64"))
        c.drawString(20 * mm, y, title)
        c.setStrokeColor(HexColor("#B0BEC5"))
        c.line(20 * mm, y - 2 * mm, width - 20 * mm, y - 2 * mm)
        return y - 10 * mm

    def field(label, value, y):
        c.setFont("Helvetica", 10)
        c.setFillColor(HexColor("#212121"))
        c.drawString(25 * mm, y, f"{label}:")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(70 * mm, y, value or "—")
        return y - 7 * mm

    y = height - 50 * mm

    # Shipment Details
    y = section("Shipment Details", y)
    y = field("Reference Number", data.get("reference_number"), y)
    y = field("Shipment Type", data.get("service_type"), y)
    y = field("Client Reference", data.get("client_reference"), y)
    y = field("Collection Date", data.get("pickup_date"), y)
    y = field("Inco Terms", data.get("inco_terms") or "N/A", y)

    # Collection
    y -= 5 * mm
    y = section("Collection", y)
    y = field("Company", data.get("collection_company"), y)
    y = field("Address", data.get("collection_address"), y)
    y = field("Region", data.get("collection_region"), y)
    y = field("Contact Person", data.get("collection_person"), y)
    y = field("Contact Number", data.get("collection_number"), y)
    y = field("Email", data.get("collection_email"), y)

    # Delivery
    y -= 5 * mm
    y = section("Delivery", y)
    y = field("Company", data.get("delivery_company"), y)
    y = field("Address", data.get("delivery_address"), y)
    y = field("Contact Person", data.get("delivery_person"), y)
    y = field("Contact Number", data.get("delivery_number"), y)
    y = field("Email", data.get("delivery_email"), y)

    # Notes
    y -= 5 * mm
    y = section("Shipper Notes", y)
    c.setFont("Helvetica", 10)
    c.setFillColor(HexColor("#212121"))
    c.drawString(25 * mm, y, data.get("client_notes") or "None")

    # QR Code
    if os.path.exists(qr_path):
        c.drawImage(qr_path, width - 50 * mm, 20 * mm,
                    width=30 * mm, preserveAspectRatio=True, mask='auto')

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(HexColor("#607D8B"))
    c.drawString(20 * mm, 10 * mm, "Generated by Hazmat Global Logistics System")

    c.save()