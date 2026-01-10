# app.py — Hazmat Backend (complete, no placeholders)

import os
import sqlite3
import base64
import io
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests

# Optional geocoding
try:
    from geopy.geocoders import Nominatim
    GEOCODER = Nominatim(user_agent="hazmat_backend")
except Exception:
    GEOCODER = None

# Optional PDF generation
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    HAS_REPORTLAB = True
except Exception:
    HAS_REPORTLAB = False

# Mail
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
    HAS_SENDGRID = True
except Exception:
    HAS_SENDGRID = False

DB_PATH = "hazmat.db"
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
FROM_EMAIL = "jnb@hazglobal.com"

app = FastAPI(title="Hazmat Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

    # Shipments master
    cur.execute("""
    CREATE TABLE IF NOT EXISTS shipments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hazjnb_ref TEXT UNIQUE,
        hmj_ref TEXT,
        type TEXT,                 -- local/import/export
        branch TEXT,               -- PLZ/CPT/JNB/KZN
        company TEXT,
        ops TEXT,                  -- ops code/name
        status TEXT,               -- Pending/Driver Assigned/In Progress/Delivered
        pickup_address TEXT,
        delivery_address TEXT,
        pickup_lat REAL,
        pickup_lng REAL,
        delivery_lat REAL,
        delivery_lng REAL,
        driver_code TEXT,
        transporter TEXT,          -- name if transporter used
        created_at TEXT,
        updated_at TEXT,
        message_id TEXT            -- for mail threading
    )
    """)

    # Updates table (dashboard)
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

    # Completed shipments
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

    # Drivers live location
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

    # Address catalog (region→area→place)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS places (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        region TEXT,   -- Gauteng, Western Cape, etc.
        area TEXT,     -- Johannesburg, Pretoria, etc.
        place TEXT,    -- Sandton, Midrand, etc.
        address TEXT,  -- canonical address string
        lat REAL,
        lng REAL
    )
    """)

    conn.commit()
    conn.close()

init_db()

# -----------------------------
# Address catalogs (seed)
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
            # Western Cape
            ("Western Cape", "Cape Town", "CBD", "Cape Town City Centre, Western Cape, South Africa", -33.9249, 18.4241),
            ("Western Cape", "Cape Town", "Bellville", "Bellville, Cape Town, Western Cape, South Africa", -33.9020, 18.6270),
            # KwaZulu-Natal
            ("KwaZulu-Natal", "Durban", "Umhlanga", "Umhlanga, Durban, KwaZulu-Natal, South Africa", -29.7260, 31.0686),
            ("KwaZulu-Natal", "Durban", "CBD", "Durban CBD, KwaZulu-Natal, South Africa", -29.8579, 31.0292),
            # Eastern Cape
            ("Eastern Cape", "Gqeberha", "Walmer", "Walmer, Gqeberha, Eastern Cape, South Africa", -33.9806, 25.5700),
        ]
        cur.executemany("""
            INSERT INTO places (region, area, place, address, lat, lng)
            VALUES (?, ?, ?, ?, ?, ?)
        """, seed)
        conn.commit()
    conn.close()

seed_places()

# -----------------------------
# Models
# -----------------------------
from pydantic import BaseModel, Field
from typing import Optional

class SubmitPayload(BaseModel):
    hazjnb_ref: str
    hmj_ref: Optional[str] = None
    type: str = Field(pattern="^(local|import|export)$")
    branch: str = Field(pattern="^(PLZ|CPT|JNB|KZN)$")
    company: str
    ops: str
    pickup_address: Optional[str] = None
    delivery_address: Optional[str] = None
    client_emails: List[str] = []
    # Optional region/area/place selections for automation
    pickup_region: Optional[str] = None
    pickup_area: Optional[str] = None
    pickup_place: Optional[str] = None
    delivery_region: Optional[str] = None
    delivery_area: Optional[str] = None
    delivery_place: Optional[str] = None

class QRScanPayload(BaseModel):
    ref: str
    driver_id: str
    stage: Optional[str] = Field(default="collection", regex="^(collection|delivery)$")
    signed_by: Optional[str] = None
    condition: Optional[str] = Field(default=None, regex="^(good|bad)$")
    notes: Optional[str] = None
    signature_b64: Optional[str] = None  # PNG/JPG base64 for driver POD

class UpdateStatusPayload(BaseModel):
    ref: str
    status: str
    driver_id: Optional[str] = None

class DriverLocationPayload(BaseModel):
    driver: str
    lat: float
    lng: float

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
    # Approximate average speed 60 km/h → 2.5h ≈ 150 km
    return km_distance(lat1, lng1, lat2, lng2) <= 150.0

def geocode(address: str) -> Optional[Dict[str, float]]:
    if not address:
        return None
    # Catalog lookup first
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT lat, lng FROM places WHERE address = ?", (address,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"lat": row["lat"], "lng": row["lng"]}

    # Fuzzy match by place name
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT place, lat, lng FROM places")
    rows = cur.fetchall()
    conn.close()
    place_lower = address.lower()
    for r in rows:
        if r["place"].lower() in place_lower:
            return {"lat": r["lat"], "lng": r["lng"]}

    # Geopy fallback
    if GEOCODER:
        try:
            loc = GEOCODER.geocode(address, timeout=10)
            if loc:
                return {"lat": loc.latitude, "lng": loc.longitude}
        except Exception:
            pass
    return None

def resolve_region_area_place(region: Optional[str], area: Optional[str], place: Optional[str]) -> Optional[Dict[str, Any]]:
    if not region or not area or not place:
        return None
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT address, lat, lng FROM places
        WHERE region = ? AND area = ? AND place = ?
    """, (region, area, place))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"address": row["address"], "lat": row["lat"], "lng": row["lng"]}
    return None

def send_mail_threaded(to_emails: List[str], subject: str, html: str, attachment_path: Optional[str], in_reply_to: Optional[str]) -> Optional[str]:
    if not HAS_SENDGRID or not SENDGRID_API_KEY or not to_emails:
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
    # Try capture message id
    msg_id = None
    if hasattr(resp, "headers"):
        msg_id = resp.headers.get("X-Message-Id")
    return msg_id

def generate_pod_pdf(haz: str, hmj: Optional[str], company: str, signed_by: str, delivery_date: str, delivery_time: str,
                     condition: Optional[str], notes: Optional[str], signature_b64: Optional[str]) -> str:
    filename = f"POD_{haz}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    out_path = os.path.join("pods", filename)
    os.makedirs("pods", exist_ok=True)

    if not HAS_REPORTLAB:
        # Fallback: simple text PDF via minimal canvas-like approach not available—require reportlab
        raise HTTPException(status_code=500, detail="ReportLab not installed for PDF generation")

    c = canvas.Canvas(out_path, pagesize=A4)
    width, height = A4

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30*mm, (height - 30*mm), "Proof of Delivery")

    c.setFont("Helvetica", 11)
    c.drawString(30*mm, (height - 40*mm), f"Dear Customer, we are happy to let you know your shipment has been delivered to {signed_by}")
    c.drawString(30*mm, (height - 46*mm), f"on {delivery_date} at {delivery_time}" + (f" in {condition}" if condition else ""))

    # Shipment details
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

    # Signature image
    if signature_b64:
        try:
            sig_bytes = base64.b64decode(signature_b64)
            sig_stream = io.BytesIO(sig_bytes)
            from reportlab.lib.utils import ImageReader
            img = ImageReader(sig_stream)
            c.drawImage(img, 30*mm, 30*mm, width=60*mm, height=25*mm, preserveAspectRatio=True, mask='auto')
            c.setFont("Helvetica", 10)
            c.drawString(30*mm, 27*mm, "Receiver Signature")
        except Exception:
            pass

    c.showPage()
    c.save()
    return out_path

# -----------------------------
# Catalog endpoints (dropdowns)
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
    return {"region": region, "area": area, "places": [{"place": r["place"], "address": r["address"], "lat": r["lat"], "lng": r["lng"]} for r in rows]}

# -----------------------------
# Address resolver (automated)
# -----------------------------
@app.post("/geocode/resolve")
def resolve_address(
    address: Optional[str] = Body(default=None),
    region: Optional[str] = Body(default=None),
    area: Optional[str] = Body(default=None),
    place: Optional[str] = Body(default=None)
):
    # Prefer dropdown selection
    resolved = resolve_region_area_place(region, area, place)
    if resolved:
        return {"address": resolved["address"], "lat": resolved["lat"], "lng": resolved["lng"], "source": "catalog"}

    # Fallback to geocode + fuzzy
    if address:
        coords = geocode(address)
        if coords:
            return {"address": address, "lat": coords["lat"], "lng": coords["lng"], "source": "geocode"}
    raise HTTPException(status_code=400, detail="Unable to resolve address")

# -----------------------------
# Submit shipment
# -----------------------------
@app.post("/submit")
def submit_shipment(payload: SubmitPayload):
    conn = db()
    cur = conn.cursor()

    # Resolve pickup/delivery via dropdowns first
    pickup = resolve_region_area_place(payload.pickup_region, payload.pickup_area, payload.pickup_place)
    delivery = resolve_region_area_place(payload.delivery_region, payload.delivery_area, payload.delivery_place)

    # If not provided via dropdowns, try geocode
    pickup_addr = payload.pickup_address or (pickup["address"] if pickup else None)
    delivery_addr = payload.delivery_address or (delivery["address"] if delivery else None)

    pickup_coords = geocode(pickup_addr) if pickup_addr else None
    delivery_coords = geocode(delivery_addr) if delivery_addr else None

    # Validate required addresses by type
    if payload.type == "local":
        if not pickup_addr or not delivery_addr:
            raise HTTPException(status_code=400, detail="Local requires pickup and delivery addresses")
    elif payload.type == "import":
        if not delivery_addr:
            raise HTTPException(status_code=400, detail="Import requires delivery address")
    elif payload.type == "export":
        if not pickup_addr:
            raise HTTPException(status_code=400, detail="Export requires pickup address")

    # Branch hubs (approx coords)
    hubs = {
        "JNB": {"lat": -26.2041, "lng": 28.0473},
        "CPT": {"lat": -33.9249, "lng": 18.4241},
        "KZN": {"lat": -29.8579, "lng": 31.0292},
        "PLZ": {"lat": -33.9608, "lng": 25.6022},
    }
    hub = hubs.get(payload.branch)

    # Decide driver vs transporter for locals/exports collections
    transporter = None
    if payload.type in ("local", "export") and pickup_coords and hub:
        if not within_2h30(hub["lat"], hub["lng"], pickup_coords["lat"], pickup_coords["lng"]):
            transporter = "Third-Party"

    # Insert shipment
    now = datetime.now()
    cur.execute("""
        INSERT INTO shipments (hazjnb_ref, hmj_ref, type, branch, company, ops, status,
                               pickup_address, delivery_address, pickup_lat, pickup_lng,
                               delivery_lat, delivery_lng, driver_code, transporter,
                               created_at, updated_at, message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.hazjnb_ref, payload.hmj_ref, payload.type, payload.branch, payload.company, payload.ops,
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
    conn.commit()

    # Add to updates table and send initial mail
    cur.execute("""
        INSERT INTO updates (ops, hmj, haz, company, date, time, latest_update, document, client_emails, message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.ops,
        payload.hmj_ref or "",
        payload.hazjnb_ref,
        payload.company,
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M"),
        f"Shipment submitted ({payload.type})",
        "",
        ",".join(payload.client_emails or []),
        None
    ))
    conn.commit()

    # Compose initial mail per type
    msg_id = None
    if payload.client_emails and HAS_SENDGRID and SENDGRID_API_KEY:
        if payload.type == "import":
            html = f"""
            <p>Dear Customer,</p>
            <p>Please note that our Operations team have received your import request, {payload.ops} is working on this and will be providing updates shortly.</p>
            """
        elif payload.type == "export":
            html = f"""
            <p>Dear Client,</p>
            <p>We are pleased to inform you that your shipment has been received and is being processed by {payload.ops}. Updates will be shared shortly.</p>
            """
        else:
            html = f"""
            <p>Dear Client,</p>
            <p>Your local shipment has been submitted and is being scheduled.</p>
            """
        subject = f"Shipment // ({payload.hmj_ref or 'HMJ—'} // {payload.hazjnb_ref})"
        msg_id = send_mail_threaded(payload.client_emails, subject, html, None, None)

    # Persist message_id for threading
    if msg_id:
        cur.execute("UPDATE shipments SET message_id = ? WHERE hazjnb_ref = ?", (msg_id, payload.hazjnb_ref))
        cur.execute("UPDATE updates SET message_id = ? WHERE haz = ?", (msg_id, payload.hazjnb_ref))
        conn.commit()

    conn.close()
    return {"ok": True, "hazjnb_ref": payload.hazjnb_ref, "transporter": transporter}

# -----------------------------
# Dashboard feeds
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
    """, (code,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# -----------------------------
# Status updates & QR scans
# -----------------------------
@app.post("/update_status")
def update_status(payload: UpdateStatusPayload):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shipments WHERE hazjnb_ref = ?", (payload.ref,))
    s = cur.fetchone()
    if not s:
        conn.close()
        raise HTTPException(status_code=404, detail="Shipment not found")

    cur.execute("""
        UPDATE shipments SET status = ?, driver_code = ?, updated_at = ?
        WHERE hazjnb_ref = ?
    """, (payload.status, payload.driver_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), payload.ref))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/scan_qr")
def scan_qr(payload: QRScanPayload):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shipments WHERE hazjnb_ref = ?", (payload.ref,))
    s = cur.fetchone()
    if not s:
        conn.close()
        raise HTTPException(status_code=404, detail="Shipment not found")

    # Threading info
    cur.execute("SELECT client_emails, message_id FROM updates WHERE haz = ?", (payload.ref,))
    u = cur.fetchone()
    client_emails = []
    original_msg_id = None
    if u:
        if u["client_emails"]:
            client_emails = [e.strip() for e in u["client_emails"].split(",") if e.strip()]
        original_msg_id = u["message_id"]

    now = datetime.now()
    if payload.stage == "collection":
        # Mark driver assigned and in progress
        cur.execute("""
            UPDATE shipments SET driver_code = ?, status = ?, updated_at = ?
            WHERE hazjnb_ref = ?
        """, (payload.driver_id, "In Progress", now.strftime("%Y-%m-%d %H:%M:%S"), payload.ref))
        conn.commit()

        # Mail: collected
        html = f"""
        <p>Dear Client,</p>
        <p>Your shipment {payload.ref} has been collected and is en route.</p>
        """
        subject = f"Collection Update // ({s['hmj_ref'] or 'HMJ—'} // {payload.ref})"
        msg_id = send_mail_threaded(client_emails, subject, html, None, original_msg_id)

        if msg_id:
            cur.execute("UPDATE shipments SET message_id = ? WHERE hazjnb_ref = ?", (msg_id, payload.ref))
            cur.execute("UPDATE updates SET message_id = ? WHERE haz = ?", (msg_id, payload.ref))
            conn.commit()

        conn.close()
        return {"ok": True, "timestamp": now.strftime("%Y-%m-%d %H:%M:%S")}

    # Delivery stage
    if payload.stage == "delivery":
        # Generate POD (driver flow)
        pod_path = generate_pod_pdf(
            haz=payload.ref,
            hmj=s["hmj_ref"],
            company=s["company"],
            signed_by=payload.signed_by or "—",
            delivery_date=now.strftime("%Y-%m-%d"),
            delivery_time=now.strftime("%H:%M"),
            condition=payload.condition,
            notes=payload.notes,
            signature_b64=payload.signature_b64
        )

        # Mark delivered
        cur.execute("""
            UPDATE shipments SET status = ?, updated_at = ?
            WHERE hazjnb_ref = ?
        """, ("Delivered", now.strftime("%Y-%m-%d %H:%M:%S"), payload.ref))
        conn.commit()

        # Completed record
        cur.execute("""
            INSERT INTO completed (ops, hmj, haz, company, pickup_date, delivery_date, time, signed_by, document, pod, invoice)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s["ops"], s["hmj_ref"], payload.ref, s["company"],
            None, now.strftime("%Y-%m-%d"), now.strftime("%H:%M"),
            payload.signed_by or "—", "", pod_path, ""
        ))
        conn.commit()

        # Mail POD to client (threaded)
        html = f"""
        <p>Dear Client,</p>
        <p>We are pleased to inform you that the shipment has successfully been delivered. Attached is a copy of the POD for your records.</p>
        <p>Should you have any enquiries on your shipment, please do not hesitate to contact us.</p>
        """
        subject = f"Delivery Update // ({s['hmj_ref'] or 'HMJ—'} // {payload.ref})"
        msg_id = send_mail_threaded(client_emails, subject, html, pod_path, s["message_id"])

        if msg_id:
            cur.execute("UPDATE shipments SET message_id = ? WHERE hazjnb_ref = ?", (msg_id, payload.ref))
            cur.execute("UPDATE updates SET message_id = ? WHERE haz = ?", (msg_id, payload.ref))
            conn.commit()

        conn.close()
        return {"ok": True, "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"), "pod": pod_path}

    conn.close()
    raise HTTPException(status_code=400, detail="Invalid stage")

# -----------------------------
# Transporter POD generation (ops-triggered)
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
    # Generate POD without condition (transporter flow)
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

    # Completed record
    cur.execute("""
        INSERT INTO completed (ops, hmj, haz, company, pickup_date, delivery_date, time, signed_by, document, pod, invoice)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        s["ops"], s["hmj_ref"], haz, s["company"],
        None, delivery_date, delivery_time, signed_by, "", pod_path, ""
    ))
    conn.commit()

    # Mail POD
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
    subject = f"POD // ({s['hmj_ref'] or 'HMJ—'} // {haz})"
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
def update_location(payload: DriverLocationPayload):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM drivers WHERE code = ?", (payload.driver,))
    row = cur.fetchone()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if row:
        cur.execute("UPDATE drivers SET lat = ?, lng = ?, updated_at = ? WHERE code = ?",
                    (payload.lat, payload.lng, now, payload.driver))
    else:
        cur.execute("INSERT INTO drivers (code, name, lat, lng, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (payload.driver, payload.driver, payload.lat, payload.lng, now))
    conn.commit()
    conn.close()
    return {"ok": True}

# -----------------------------
# Cleanup dummy shipments
# -----------------------------
@app.post("/admin/cleanup_dummies")
def cleanup_dummies(prefix: str = Body(default="HAZJNBTEST")):
    conn = db()
    cur = conn.cursor()
    # Delete shipments, updates, completed with haz starting with prefix
    cur.execute("DELETE FROM shipments WHERE hazjnb_ref LIKE ?", (f"{prefix}%",))
    cur.execute("DELETE FROM updates WHERE haz LIKE ?", (f"{prefix}%",))
    cur.execute("DELETE FROM completed WHERE haz LIKE ?", (f"{prefix}%",))
    conn.commit()
    conn.close()
    return {"ok": True, "prefix": prefix}

# -----------------------------
# Mail API (explicit route)
# -----------------------------
@app.post("/api/sendmail")
def api_sendmail(
    to_emails: List[str] = Body(...),
    subject: str = Body(...),
    html_content: str = Body(...),
    attachment_path: Optional[str] = Body(default=None),
    in_reply_to: Optional[str] = Body(default=None),
    hmj: Optional[str] = Body(default=None),
    haz: Optional[str] = Body(default=None)
):
    msg_id = send_mail_threaded(to_emails, subject, html_content, attachment_path, in_reply_to)

    # Persist message_id for threading if hmj/haz provided
    if msg_id and (hmj or haz):
        conn = db()
        cur = conn.cursor()
        if haz:
            cur.execute("UPDATE shipments SET message_id = ? WHERE hazjnb_ref = ?", (msg_id, haz))
            cur.execute("UPDATE updates SET message_id = ? WHERE haz = ?", (msg_id, haz))
        elif hmj:
            cur.execute("UPDATE updates SET message_id = ? WHERE hmj = ?", (msg_id, hmj))
        conn.commit()
        conn.close()

    return {"ok": True, "message_id": msg_id}

# -----------------------------
# Utility: delivery ETA messaging for imports
# -----------------------------
def import_eta_text(delivery_coords: Optional[Dict[str, float]], branch: str) -> str:
    # If before 13:00 → today; else tomorrow; if outside 2h30 → ASAP
    now = datetime.now()
    hubs = {
        "JNB": {"lat": -26.2041, "lng": 28.0473},
        "CPT": {"lat": -33.9249, "lng": 18.4241},
        "KZN": {"lat": -29.8579, "lng": 31.0292},
        "PLZ": {"lat": -33.9608, "lng": 25.6022},
    }
    hub = hubs.get(branch)
    if not delivery_coords or not hub:
        return "Shipment will be delivered as soon as possible."

    if not within_2h30(hub["lat"], hub["lng"], delivery_coords["lat"], delivery_coords["lng"]):
        return "Shipment will be delivered as soon as possible."

    if now.hour < 13:
        return "Shipment will be delivered today."
    return "Shipment will be delivered tomorrow."

# -----------------------------
# Hook: import collection confirmation mail
# -----------------------------
@app.post("/imports/collected")
def import_collected(haz: str = Body(...)):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM shipments WHERE hazjnb_ref = ?", (haz,))
    s = cur.fetchone()
    if not s:
        conn.close()
        raise HTTPException(status_code=404, detail="Shipment not found")

    cur.execute("SELECT client_emails, message_id FROM updates WHERE haz = ?", (haz,))
    u = cur.fetchone()
    client_emails = []
    original_msg_id = None
    if u:
        if u["client_emails"]:
            client_emails = [e.strip() for e in u["client_emails"].split(",") if e.strip()]
        original_msg_id = u["message_id"]

    eta_text = import_eta_text(
        delivery_coords={"lat": s["delivery_lat"], "lng": s["delivery_lng"]} if s["delivery_lat"] and s["delivery_lng"] else None,
        branch=s["branch"]
    )
    html = f"""
    <p>Dear Customer,</p>
    <p>Your import shipment {haz} has been collected at the airport and {eta_text}</p>
    """
    subject = f"Import Update // ({s['hmj_ref'] or 'HMJ—'} // {haz})"
    msg_id = send_mail_threaded(client_emails, subject, html, None, original_msg_id)

    if msg_id:
        cur.execute("UPDATE shipments SET message_id = ? WHERE hazjnb_ref = ?", (msg_id, haz))
        cur.execute("UPDATE updates SET message_id = ? WHERE haz = ?", (msg_id, haz))
        conn.commit()

    conn.close()
    return {"ok": True}