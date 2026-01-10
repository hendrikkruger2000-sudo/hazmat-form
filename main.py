import os
import sqlite3
import base64
import io
from datetime import datetime, date
from typing import Optional, List, Dict, Literal

from fastapi import FastAPI, HTTPException, Body, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

# Geocoding
try:
    from geopy.geocoders import Nominatim
    GEOCODER = Nominatim(user_agent="hazmat_backend")
except Exception:
    GEOCODER = None

# PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

# Mail
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition

DB_PATH = "hazmat.db"
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
FROM_EMAIL = os.environ.get("FROM_EMAIL", "jnb@hazglobal.com")

app = FastAPI(title="Hazmat Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Static files (logo, assets)
# -----------------------------
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# -----------------------------
# Database bootstrap
# -----------------------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS shipments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hazjnb_ref TEXT UNIQUE,
        hmj_ref TEXT,
        type TEXT,
        branch TEXT,
        company TEXT,
        ops TEXT,
        status TEXT,
        pickup_address TEXT,
        delivery_address TEXT,
        pickup_lat REAL,
        pickup_lng REAL,
        delivery_lat REAL,
        delivery_lng REAL,
        driver_code TEXT,
        transporter TEXT,
        created_at TEXT,
        updated_at TEXT,
        message_id TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ops TEXT,
        hmj TEXT,
        haz TEXT,
        company TEXT,
        date TEXT,
        time TEXT,
        latest_update TEXT,
        document TEXT,
        client_emails TEXT,
        message_id TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS completed (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ops TEXT,
        hmj TEXT,
        haz TEXT,
        company TEXT,
        pickup_date TEXT,
        delivery_date TEXT,
        time TEXT,
        signed_by TEXT,
        document TEXT,
        pod TEXT,
        invoice TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS drivers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        name TEXT,
        lat REAL,
        lng REAL,
        updated_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS places (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        region TEXT,
        area TEXT,
        place TEXT,
        address TEXT,
        lat REAL,
        lng REAL
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS client_addresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT,
        type TEXT, -- 'collection' or 'delivery'
        company TEXT,
        address TEXT,
        contact_person TEXT,
        contact_number TEXT,
        email TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

# -----------------------------
# Helpers
# -----------------------------
def km_distance(lat1, lng1, lat2, lng2) -> float:
    from math import radians, sin, cos, atan2, sqrt
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def within_2h30(lat1, lng1, lat2, lng2) -> bool:
    return km_distance(lat1, lng1, lat2, lng2) <= 150.0

def geocode(address: str) -> Optional[Dict[str, float]]:
    if not address:
        return None
    if GEOCODER:
        try:
            loc = GEOCODER.geocode(address, timeout=10)
            if loc:
                return {"lat": loc.latitude, "lng": loc.longitude}
        except Exception:
            pass
    return None

def send_mail_threaded(to_emails: List[str], subject: str, html: str, attachment_path: Optional[str], in_reply_to: Optional[str]) -> Optional[str]:
    if not SENDGRID_API_KEY or not to_emails:
        return None
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_emails,
        subject=subject,
        html_content=html
    )
    if in_reply_to:
        message.headers = {
            "In-Reply-To": in_reply_to,
            "References": in_reply_to
        }
    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            data = f.read()
        encoded = base64.b64encode(data).decode()
        attachment = Attachment(
            FileContent(encoded),
            FileName(os.path.basename(attachment_path)),
            FileType("application/pdf"),
            Disposition("attachment")
        )
        message.attachment = attachment
    sg = SendGridAPIClient(SENDGRID_API_KEY)
    resp = sg.send(message)
    msg_id = None
    if hasattr(resp, "headers"):
        msg_id = resp.headers.get("X-Message-Id")
    return msg_id

def generate_pod_pdf(haz: str, hmj: Optional[str], company: str, signed_by: str, delivery_date: str, delivery_time: str,
                     condition: Optional[str], notes: Optional[str], signature_b64: Optional[str]) -> str:
    filename = f"POD_{haz}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    out_path = os.path.join("pods", filename)
    os.makedirs("pods", exist_ok=True)
    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30*mm, (height - 30*mm), "Proof of Delivery")
    c.setFont("Helvetica", 11)
    c.drawString(30*mm, (height - 40*mm), f"Delivered to {signed_by} on {delivery_date} at {delivery_time} in {condition or '—'} condition.")
    y = height - 60*mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30*mm, y, "Shipment Details:")
    y -= 8*mm
    c.setFont("Helvetica", 11)
    c.drawString(30*mm, y, f"HAZJNB REF: {haz}")
    y -= 6*mm
    c.drawString(30*mm, y, f"HMJ REF: {hmj or '—'}")
    y -= 6*mm
    c.drawString(30*mm, y, f"Client: {company}")
    y -= 6*mm
    c.drawString(30*mm, y, f"Notes: {notes or '—'}")
    if signature_b64:
        try:
            sig_bytes = base64.b64decode(signature_b64)
            sig_stream = io.BytesIO(sig_bytes)
            img = ImageReader(sig_stream)
            c.drawImage(img, 30*mm, 30*mm, width=60*mm, height=25*mm, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    c.showPage()
    c.save()
    return out_path

# -----------------------------
# Address catalog seeding
# -----------------------------
def seed_places():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM places")
    count = cur.fetchone()["c"]
    if count == 0:
        seed = [
            # Gauteng
            ("Gauteng", "Johannesburg", "Sandton", "Sandton, Johannesburg, Gauteng, South Africa", -26.1076, 28.0567),
            ("Gauteng", "Johannesburg", "Midrand", "Midrand, Johannesburg, Gauteng, South Africa", -25.9970, 28.1260),
            ("Gauteng", "Pretoria", "Hatfield", "Hatfield, Pretoria, Gauteng, South Africa", -25.7460, 28.2293),
            ("Gauteng", "Ekurhuleni", "Brakpan", "Brakpan, Ekurhuleni, Gauteng, South Africa", -26.2560, 28.3200),
            ("Gauteng", "Johannesburg", "CBD", "Johannesburg CBD, Gauteng, South Africa", -26.2041, 28.0473),
            ("Gauteng", "Vereeniging", "CBD", "Vereeniging, Gauteng, South Africa", -26.6731, 27.9319),
            ("Gauteng", "Sasolburg", "CBD", "Sasolburg, Free State, South Africa", -26.8136, 27.8166),

            # Western Cape
            ("Western Cape", "Cape Town", "CBD", "Cape Town City Centre, Western Cape, South Africa", -33.9249, 18.4241),
            ("Western Cape", "Cape Town", "Bellville", "Bellville, Cape Town, Western Cape, South Africa", -33.9020, 18.6270),
            ("Western Cape", "Cape Town", "Durbanville", "Durbanville, Cape Town, Western Cape, South Africa", -33.8350, 18.6500),
            ("Western Cape", "Cape Town", "Milnerton", "Milnerton, Cape Town, Western Cape, South Africa", -33.8762, 18.4960),
            ("Western Cape", "Stellenbosch", "CBD", "Stellenbosch, Western Cape, South Africa", -33.9344, 18.8610),
            ("Western Cape", "Paarl", "CBD", "Paarl, Western Cape, South Africa", -33.7342, 18.9621),
            ("Western Cape", "George", "CBD", "George, Western Cape, South Africa", -33.9640, 22.4590),

            # KwaZulu-Natal
            ("KwaZulu-Natal", "Durban", "Umhlanga", "Umhlanga, Durban, KwaZulu-Natal, South Africa", -29.7260, 31.0686),
            ("KwaZulu-Natal", "Durban", "CBD", "Durban CBD, KwaZulu-Natal, South Africa", -29.8579, 31.0292),
            ("KwaZulu-Natal", "Pinetown", "CBD", "Pinetown, KwaZulu-Natal, South Africa", -29.8170, 30.8850),
            ("KwaZulu-Natal", "Pietermaritzburg", "CBD", "Pietermaritzburg, KwaZulu-Natal, South Africa", -29.6006, 30.3794),

            # Eastern Cape
            ("Eastern Cape", "Gqeberha", "Walmer", "Walmer, Gqeberha, Eastern Cape, South Africa", -33.9806, 25.5700),
            ("Eastern Cape", "Gqeberha", "CBD", "Gqeberha CBD, Eastern Cape, South Africa", -33.9608, 25.6022),
            ("Eastern Cape", "East London", "CBD", "East London, Eastern Cape, South Africa", -33.0153, 27.9116),
        ]
        cur.executemany("""
            INSERT INTO places (region, area, place, address, lat, lng)
            VALUES (?, ?, ?, ?, ?, ?)
        """, seed)
        conn.commit()
    conn.close()

seed_places()

# -----------------------------
# Catalog endpoints (regions → areas → places)
# -----------------------------
@app.get("/catalog/regions")
def get_regions():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT region FROM places ORDER BY region")
    regions = [r["region"] for r in cur.fetchall()]
    conn.close()
    return {"regions": regions}

@app.get("/catalog/areas/{region}")
def get_areas(region: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT area FROM places WHERE region = ? ORDER BY area", (region,))
    areas = [r["area"] for r in cur.fetchall()]
    conn.close()
    return {"region": region, "areas": areas}

@app.get("/catalog/places/{region}/{area}")
def get_places(region: str, area: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT place, address, lat, lng FROM places WHERE region = ? AND area = ? ORDER BY place", (region, area))
    rows = cur.fetchall()
    conn.close()
    return {
        "region": region,
        "area": area,
        "places": [{"place": r["place"], "address": r["address"], "lat": r["lat"], "lng": r["lng"]} for r in rows]
    }

# -----------------------------
# Identity stub for navbar
# -----------------------------
@app.get("/api/me")
def api_me():
    # Replace with real auth/session later if needed
    return {"id": 1, "name": "Hazmat Client"}

# -----------------------------
# Saved contacts endpoints
# -----------------------------
@app.get("/client/addresses")
def list_addresses():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM client_addresses ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/client/addresses/{addr_id}")
def get_address(addr_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM client_addresses WHERE id = ?", (addr_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        raise HTTPException(status_code=404, detail="Address not found")
    return dict(r)

@app.post("/client/addresses")
def save_address(
    label: str = Body(...),
    type: str = Body(...),  # 'collection' or 'delivery'
    company: str = Body(...),
    address: str = Body(...),
    contact_person: str = Body(...),
    contact_number: str = Body(...),
    email: Optional[str] = Body(default=None)
):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO client_addresses (label, type, company, address, contact_person, contact_number, email)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (label, type, company, address, contact_person, contact_number, email))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"ok": True, "id": new_id}

# -----------------------------
# Email endpoint (SendGrid)
# -----------------------------
@app.post("/api/send_email")
def api_send_email(to: List[str] = Body(...), subject: str = Body(...), body: str = Body(...)):
    msg_id = send_mail_threaded(to, subject, body, None, None)
    return {"status": "ok" if msg_id else "sent_without_id", "message_id": msg_id}

# -----------------------------
# Home Page
# -----------------------------
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
          <h1>Welcome to Hazmat Global Support Services</h1>
          <p>Your trusted partner in hazardous materials logistics. Navigate above to book collections, track shipments, file complaints, or rate our services.</p>
        </main>

        <footer>
          <p><strong>Hazmat Global Support Services</strong></p>
          <p><strong>Quotes & Support</strong> — Email: <a href="mailto:csd@hazglobal.com" style="color:white;">csd@hazglobal.com</a></p>
          <p>&copy; 2026 Hazmat Global Support Services. All rights reserved.</p>
        </footer>
        """

# -----------------------------
# Submit Page (full, matching your attached content)
# -----------------------------
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
      <p><strong>Quotes & Support</strong> — Email: <a href="mailto:csd@hazglobal.com" style="color:white;">csd@hazglobal.com</a></p>
      <p>&copy; 2026 Hazmat Global Support Services. All rights reserved.</p>
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
    }});
    </script>
    """

# -----------------------------
# POST /submit (form-based, full ops flow)
# -----------------------------
@app.post("/submit")
async def submit_collection(
    shipment_type: str = Form(...),
    collection_date: str = Form(...),
    inco_terms: str = Form(...),
    quoted: Optional[str] = Form(None),
    sales_rep: Optional[str] = Form(None),

    collection_company: str = Form(...),
    collection_address: str = Form(...),
    collection_contact_name: str = Form(...),
    collection_contact_number: str = Form(...),
    collection_email: str = Form(...),
    collection_region: Optional[str] = Form(None),

    delivery_company: Optional[str] = Form(None),
    delivery_address: Optional[str] = Form(None),
    delivery_contact_name: Optional[str] = Form(None),
    delivery_contact_number: Optional[str] = Form(None),
    delivery_email: Optional[str] = Form(None),
    delivery_region: Optional[str] = Form(None),

    shipper_notes: Optional[str] = Form(None),

    length: Optional[List[float]] = Form(None),
    width: Optional[List[float]] = Form(None),
    height: Optional[List[float]] = Form(None),
    weight: Optional[List[float]] = Form(None),
    quantity: Optional[List[int]] = Form(None),

    shipment_docs: Optional[List[UploadFile]] = File(None)
):
    # Normalize quoted checkbox
    quoted_flag = 1 if quoted in ("on", "true", "1") else 0

    # Map region to branch code
    region_to_branch = {
        "Johannesburg": "JNB",
        "Durban": "KZN",
        "Cape Town": "CPT",
        "Port Elizabeth": "PLZ",
    }
    branch = region_to_branch.get(collection_region or "", "JNB")

    # Validate required addresses by type
    if shipment_type == "local":
        if not collection_address or not delivery_address:
            raise HTTPException(status_code=400, detail="Local requires collection and delivery addresses")
    elif shipment_type == "import":
        if not delivery_address:
            raise HTTPException(status_code=400, detail="Import requires delivery address")
    elif shipment_type == "export":
        if not collection_address:
            raise HTTPException(status_code=400, detail="Export requires collection address")

    pickup_addr = collection_address
    delivery_addr = delivery_address

    pickup_coords = geocode(pickup_addr) if pickup_addr else None
    delivery_coords = geocode(delivery_addr) if delivery_addr else None

    # Branch hubs (approx coords)
    hubs = {
        "JNB": {"lat": -26.2041, "lng": 28.0473},
        "CPT": {"lat": -33.9249, "lng": 18.4241},
        "KZN": {"lat": -29.8579, "lng": 31.0292},
        "PLZ": {"lat": -33.9608, "lng": 25.6022},
    }
    hub = hubs.get(branch)

    # Decide transporter for locals/exports (2h30 radius from branch to pickup)
    transporter = None
    if shipment_type in ("local", "export") and pickup_coords and hub:
        if not within_2h30(hub["lat"], hub["lng"], pickup_coords["lat"], pickup_coords["lng"]):
            transporter = "Third-Party"

    # Generate refs
    hazjnb_ref = f"HAZJNB{datetime.now().strftime('%Y%m%d%H%M%S')}"
    hmj_ref = None  # can be set later if needed
    ops = "OPS"     # derive from session/user if available

    # Insert shipment
    now = datetime.now()
    conn = db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO shipments (hazjnb_ref, hmj_ref, type, branch, company, ops, status,
                                   pickup_address, delivery_address, pickup_lat, pickup_lng,
                                   delivery_lat, delivery_lng, driver_code, transporter,
                                   created_at, updated_at, message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            hazjnb_ref, hmj_ref, shipment_type, branch, collection_company, ops,
            "Pending",
            pickup_addr, delivery_addr,
            (pickup_coords["lat"] if pickup_coords else None),
            (pickup_coords["lng"] if pickup_coords else None),
            (delivery_coords["lat"] if delivery_coords else None),
            (delivery_coords["lng"] if delivery_coords else None),
            None,
            transporter,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d %H:%M:%S"),
            None
        ))
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=409, detail="HAZJNB Ref already exists")

    # Seed updates row
    client_emails = []
    if collection_email:
        client_emails += [e.strip() for e in collection_email.split(",") if e.strip()]
    if delivery_email:
        client_emails += [e.strip() for e in delivery_email.split(",") if e.strip()]
    client_emails = list(dict.fromkeys(client_emails))  # dedupe

    cur.execute("""
        INSERT INTO updates (ops, hmj, haz, company, date, time, latest_update, document, client_emails, message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ops,
        hmj_ref or "",
        hazjnb_ref,
        collection_company,
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M"),
        f"Shipment submitted ({shipment_type})",
        "",
        ",".join(client_emails),
        None
    ))
    conn.commit()

    # Save uploaded docs (optional)
    if shipment_docs:
        os.makedirs("uploads", exist_ok=True)
        for f in shipment_docs:
            dest = os.path.join("uploads", f.filename)
            with open(dest, "wb") as out:
                out.write(await f.read())

    # Initial mail per type
    msg_id = None
    if client_emails and SENDGRID_API_KEY:
        if shipment_type == "import":
            html = f"""
            <p>Dear Customer,</p>
            <p>Please note that our Operations team have received your import request, {ops} is working on this and will be providing updates shortly.</p>
            """
        elif shipment_type == "export":
            html = f"""
            <p>Dear Client,</p>
            <p>Your export collection has been arranged for {collection_company}. Once received at our warehouse, updates will follow.</p>
            """
        else:
            html = f"""
            <p>Dear Client,</p>
            <p>Your local shipment has been submitted and is being scheduled.</p>
            """
        subject = f"Shipment // ({hmj_ref or 'HMJ—'} // {hazjnb_ref})"
        msg_id = send_mail_threaded(client_emails, subject, html, None, None)

    if msg_id:
        cur.execute("UPDATE shipments SET message_id = ? WHERE hazjnb_ref = ?", (msg_id, hazjnb_ref))
        cur.execute("UPDATE updates SET message_id = ? WHERE haz = ?", (msg_id, hazjnb_ref))
        conn.commit()

    conn.close()
    return {"ok": True, "hazjnb_ref": hazjnb_ref, "transporter": transporter}

# -----------------------------
# Track Page + handler
# -----------------------------
@app.get("/embed/track", response_class=HTMLResponse)
def embed_track():
    return """
    <header style="background:#2E7D32; color:white; padding:1rem 2rem;">
      <h2>Track Your Shipment</h2>
    </header>
    <main style="max-width:800px; margin:2rem auto;">
      <form action="/track" method="get">
        <label>Enter HAZJNB Reference</label>
        <input type="text" name="ref">
        <button type="submit">Track</button>
      </form>
    </main>
    """

@app.get("/track")
def track(ref: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shipments WHERE hazjnb_ref = ?", (ref,))
    r = cur.fetchone()
    conn.close()
    if not r:
        return {"found": False, "ref": ref}
    return {
        "found": True,
        "ref": ref,
        "type": r["type"],
        "company": r["company"],
        "status": r["status"],
        "pickup_address": r["pickup_address"],
        "delivery_address": r["delivery_address"]
    }

# -----------------------------
# Complaint Page + handler
# -----------------------------
@app.get("/embed/complaint", response_class=HTMLResponse)
def embed_complaint():
    return """
    <header style="background:#2E7D32; color:white; padding:1rem 2rem;">
      <h2>File a Complaint</h2>
    </header>
    <main style="max-width:800px; margin:2rem auto;">
      <form action="/complaint" method="post">
        <label>Your Name</label>
        <input type="text" name="name">
        <label>Email</label>
        <input type="email" name="email">
        <label>Complaint Details</label>
        <textarea name="details"></textarea>
        <button type="submit">Submit Complaint</button>
      </form>
    </main>
    """

@app.post("/complaint")
def complaint(name: str = Form(...), email: str = Form(...), details: str = Form(...)):
    # You can extend to email ops or log elsewhere
    return {"ok": True}

# -----------------------------
# Rate Page + handler
# -----------------------------
@app.get("/embed/rate", response_class=HTMLResponse)
def embed_rate():
    return """
    <header style="background:#2E7D32; color:white; padding:1rem 2rem;">
      <h2>Rate Our Services</h2>
    </header>
    <main style="max-width:800px; margin:2rem auto;">
      <form action="/rate" method="post">
        <label>Rating (1-5)</label>
        <input type="number" name="rating" min="1" max="5">
        <label>Comments</label>
        <textarea name="comments"></textarea>
        <button type="submit">Submit Rating</button>
      </form>
    </main>
    """

@app.post("/rate")
def rate(rating: int = Form(...), comments: Optional[str] = Form(None)):
    return {"ok": True}

# -----------------------------
# Login Page + handler (demo)
# -----------------------------
@app.get("/embed/login", response_class=HTMLResponse)
def embed_login():
    return """
    <header style="background:#2E7D32; color:white; padding:1rem 2rem;">
      <h2>Client Login</h2>
    </header>
    <main style="max-width:600px; margin:2rem auto;">
      <form action="/login" method="post">
        <label>Email</label>
        <input type="email" name="email">
        <label>Password</label>
        <input type="password" name="password">
        <button type="submit">Login</button>
      </form>
    </main>
    """

@app.post("/login")
def login(email: str = Form(...), password: str = Form(...)):
    return {"ok": True, "email": email}

# -----------------------------
# Ops feeds
# -----------------------------
@app.get("/ops/unassigned")
def ops_unassigned():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT hazjnb_ref, company, pickup_address, delivery_address, pickup_lat, pickup_lng,
               delivery_lat, delivery_lng, driver_code, status, type
        FROM shipments
        WHERE status IN ('Pending', 'Driver Assigned') AND (driver_code IS NULL OR driver_code = '')
        ORDER BY created_at DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/ops/assigned")
def ops_assigned():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT hazjnb_ref, company, pickup_address, delivery_address, pickup_lat, pickup_lng,
               delivery_lat, delivery_lng, driver_code, status, type
        FROM shipments
        WHERE driver_code IS NOT NULL AND status IN ('Driver Assigned', 'In Progress')
        ORDER BY updated_at DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/ops/completed")
def ops_completed():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT ops, hmj, haz, company, delivery_date, time, signed_by, document, pod
        FROM completed
        ORDER BY id DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/ops/drivers")
def ops_drivers():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT code, name, lat, lng, updated_at FROM drivers")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# -----------------------------
# Driver feeds
# -----------------------------
@app.get("/driver/{code}")
def driver_jobs(code: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT hazjnb_ref, company, pickup_address AS address, status
        FROM shipments
        WHERE driver_code = ? AND status IN ('Driver Assigned', 'In Progress')
        ORDER BY updated_at DESC
    """, (code,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/deliveries/{code}")
def driver_deliveries(code: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT hazjnb_ref, company, delivery_address AS address, status
        FROM shipments
        WHERE driver_code = ? AND status IN ('In Progress')
        ORDER BY updated_at DESC
    """, (code,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# -----------------------------
# Status updates
# -----------------------------
@app.post("/update_status")
def update_status(ref: str = Body(...), status: str = Body(...), driver_id: Optional[str] = Body(default=None)):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shipments WHERE hazjnb_ref = ?", (ref,))
    s = cur.fetchone()
    if not s:
        conn.close()
        raise HTTPException(status_code=404, detail="Shipment not found")

    cur.execute("""
        UPDATE shipments SET status = ?, driver_code = ?, updated_at = ?
        WHERE hazjnb_ref = ?
    """, (status, driver_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ref))
    conn.commit()
    conn.close()
    return {"ok": True}

# -----------------------------
# QR scan (collection/delivery)
# -----------------------------
@app.post("/scan_qr")
def scan_qr(
    ref: str = Body(...),
    driver_id: str = Body(...),
    stage: Literal["collection", "delivery"] = Body(...),
    signed_by: Optional[str] = Body(default=None),
    condition: Optional[Literal["good", "bad"]] = Body(default=None),
    notes: Optional[str] = Body(default=None),
    signature_b64: Optional[str] = Body(default=None)
):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shipments WHERE hazjnb_ref = ?", (ref,))
    s = cur.fetchone()
    if not s:
        conn.close()
        raise HTTPException(status_code=404, detail="Shipment not found")

    # Threading info
    cur.execute("SELECT client_emails, message_id FROM updates WHERE haz = ?", (ref,))
    u = cur.fetchone()
    client_emails = []
    original_msg_id = None
    if u:
        if u["client_emails"]:
            client_emails = [e.strip() for e in u["client_emails"].split(",") if e.strip()]
        original_msg_id = u["message_id"]

    now = datetime.now()

    if stage == "collection":
        cur.execute("""
            UPDATE shipments SET driver_code = ?, status = ?, updated_at = ?
            WHERE hazjnb_ref = ?
        """, (driver_id, "In Progress", now.strftime("%Y-%m-%d %H:%M:%S"), ref))
        conn.commit()

        html = f"""
        <p>Dear Client,</p>
        <p>Your shipment {ref} has been collected and is en route.</p>
        """
        subject = f"Collection Update // ({s['hmj_ref'] or 'HMJ—'} // {ref})"
        msg_id = send_mail_threaded(client_emails, subject, html, None, original_msg_id)

        if msg_id:
            cur.execute("UPDATE shipments SET message_id = ? WHERE hazjnb_ref = ?", (msg_id, ref))
            cur.execute("UPDATE updates SET message_id = ? WHERE haz = ?", (msg_id, ref))
            conn.commit()

        conn.close()
        return {"ok": True, "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")}

    if stage == "delivery":
        pod_path = generate_pod_pdf(
            haz=ref,
            hmj=s["hmj_ref"],
            company=s["company"],
            signed_by=signed_by or "—",
            delivery_date=now.strftime("%Y-%m-%d"),
            delivery_time=now.strftime("%H:%M"),
            condition=condition,
            notes=notes,
            signature_b64=signature_b64
        )

        cur.execute("""
            UPDATE shipments SET status = ?, updated_at = ?
            WHERE hazjnb_ref = ?
        """, ("Delivered", now.strftime("%Y-%m-%d %H:%M:%S"), ref))
        conn.commit()

        cur.execute("""
            INSERT INTO completed (ops, hmj, haz, company, pickup_date, delivery_date, time, signed_by, document, pod, invoice)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s["ops"], s["hmj_ref"], ref, s["company"],
            None, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"),
            signed_by or "—", "", pod_path, ""
        ))
        conn.commit()

        html = f"""
        <p>Dear Client,</p>
        <p>We are pleased to inform you that the shipment has successfully been delivered. Attached is a copy of the POD for your records.</p>
        <p>Should you have any enquiries on your shipment, please do not hesitate to contact us.</p>
        """
        subject = f"Delivery Update // ({s['hmj_ref'] or 'HMJ—'} // {ref})"
        msg_id = send_mail_threaded(client_emails, subject, html, pod_path, s["message_id"])

        if msg_id:
            cur.execute("UPDATE shipments SET message_id = ? WHERE hazjnb_ref = ?", (msg_id, ref))
            cur.execute("UPDATE updates SET message_id = ? WHERE haz = ?", (msg_id, ref))
            conn.commit()

        conn.close()
        return {"ok": True, "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"), "pod": pod_path}

    conn.close()
    raise HTTPException(status_code=400, detail="Invalid stage")

# -----------------------------
# Transporter POD (ops-triggered)
# -----------------------------
@app.post("/ops/generate_pod")
def ops_generate_pod(
    haz: str = Body(...),
    hmj: Optional[str] = Body(default=None),
    company: str = Body(...),
    signed_by: str = Body(...),
    delivery_date: str = Body(...),
    delivery_time: str = Body(...),
    notes: Optional[str] = Body(default=None),
    signature_b64: Optional[str] = Body(default=None)
):
    pod_path = generate_pod_pdf(
        haz=haz, hmj=hmj, company=company, signed_by=signed_by,
        delivery_date=delivery_date, delivery_time=delivery_time,
        condition=None, notes=notes, signature_b64=signature_b64
    )

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shipments WHERE hazjnb_ref = ?", (haz,))
    s = cur.fetchone()
    if not s:
        conn.close()
        raise HTTPException(status_code=404, detail="Shipment not found")

    cur.execute("""
        INSERT INTO completed (ops, hmj, haz, company, pickup_date, delivery_date, time, signed_by, document, pod, invoice)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        s["ops"], hmj or s["hmj_ref"], haz, s["company"],
        None, delivery_date, delivery_time, signed_by, "", pod_path, ""
    ))
    conn.commit()

    cur.execute("SELECT client_emails, message_id FROM updates WHERE haz = ?", (haz,))
    u = cur.fetchone()
    client_emails = []
    original_msg_id = None
    if u:
        if u["client_emails"]:
            client_emails = [e.strip() for e in u["client_emails"].split(",") if e.strip()]
        original_msg_id = u["message_id"]

    html = """
    <p>Dear Client,</p>
    <p>We are pleased to inform you that the shipment has successfully been delivered, attached is a copy of the POD for your records.</p>
    <p>Should you have any enquiries on your shipment, please do not hesitate to contact us.</p>
    """
    subject = f"POD // ({hmj or s['hmj_ref'] or 'HMJ—'} // {haz})"
    msg_id = send_mail_threaded(client_emails, subject, html, pod_path, original_msg_id)

    if msg_id:
        cur.execute("UPDATE shipments SET message_id = ? WHERE hazjnb_ref = ?", (msg_id, haz))
        cur.execute("UPDATE updates SET message_id = ? WHERE haz = ?", (msg_id, haz))
        conn.commit()

    conn.close()
    return {"ok": True, "pod": pod_path}

# -----------------------------
# Driver location updates
# -----------------------------
@app.post("/ops/update_location")
def update_location(driver: str = Body(...), lat: float = Body(...), lng: float = Body(...)):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM drivers WHERE code = ?", (driver,))
    row = cur.fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if row:
        cur.execute("UPDATE drivers SET lat = ?, lng = ?, updated_at = ? WHERE code = ?",
                    (lat, lng, now, driver))
    else:
        cur.execute("INSERT INTO drivers (code, name, lat, lng, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (driver, driver, lat, lng, now))
    conn.commit()
    conn.close()
    return {"ok": True}

