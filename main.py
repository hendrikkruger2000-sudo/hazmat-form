from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import sqlite3, os
from datetime import datetime
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

os.makedirs("static/waybills", exist_ok=True)
os.makedirs("static/qrcodes", exist_ok=True)

def init_db():
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS requests (
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
        timestamp TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

@app.get("/", response_class=HTMLResponse)
async def form():
    with open("templates/form.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.post("/submit")
async def submit(request: Request):
    form = await request.form()
    service_type = form.get("serviceType")
    inco_terms = form.get("inco_terms") or ""

    def get_field(name):
        return form.get(f"{name}_local") or form.get(f"{name}_export") or form.get(f"{name}_import")

    collection_company = get_field("collection_company")
    collection_address = get_field("collection_address")
    collection_person = get_field("collection_person")
    collection_number = get_field("collection_number")
    delivery_company = get_field("delivery_company")
    delivery_address = get_field("delivery_address")
    delivery_person = get_field("delivery_person")
    delivery_number = get_field("delivery_number")
    client_reference = get_field("client_reference")
    pickup_date = get_field("pickup_date")
    client_notes = get_field("client_notes")
    timestamp = datetime.now().isoformat()

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM requests")
    count = cursor.fetchone()[0]
    reference_number = f"HAZJNB{str(count + 1).zfill(4)}"

    cursor.execute("""
        INSERT INTO requests (
            reference_number, service_type, collection_company, collection_address, collection_person, collection_number,
            delivery_company, delivery_address, delivery_person, delivery_number,
            client_reference, pickup_date, inco_terms, client_notes, pdf_path, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        reference_number, service_type, collection_company, collection_address, collection_person, collection_number,
        delivery_company, delivery_address, delivery_person, delivery_number,
        client_reference, pickup_date, inco_terms, client_notes, "", timestamp
    ))
    request_id = cursor.lastrowid
    conn.commit()
    conn.close()

    qr_url = f"https://hazmat-collection.onrender.com/confirm/{request_id}"
    qr_img = qrcode.make(qr_url)
    qr_path = f"static/qrcodes/qr_{request_id}.png"
    qr_img.save(qr_path)

    pdf_path = f"static/waybills/waybill_{request_id}.pdf"
    generate_pdf({
        "reference_number": reference_number,
        "service_type": service_type,
        "collection_company": collection_company,
        "collection_address": collection_address,
        "collection_person": collection_person,
        "collection_number": collection_number,
        "delivery_company": delivery_company,
        "delivery_address": delivery_address,
        "delivery_person": delivery_person,
        "delivery_number": delivery_number,
        "client_reference": client_reference,
        "pickup_date": pickup_date,
        "inco_terms": inco_terms,
        "client_notes": client_notes
    }, request_id, qr_path, pdf_path)

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE requests SET pdf_path = ? WHERE id = ?", (pdf_path, request_id))
    conn.commit()
    conn.close()

    return HTMLResponse(f"""
    <html><body>
    <script>
        window.open('/pdf/{request_id}', '_blank');
        window.location.href = '/thankyou';
    </script>
    </body></html>
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

@app.get("/confirm/{request_id}", response_class=HTMLResponse)
def confirm(request_id: int):
    return HTMLResponse(f"<h1>Driver confirmed request #{request_id}</h1>")

def generate_pdf(data, request_id, qr_path, pdf_path):
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    # Background
    c.setFillColor(HexColor("#ECEFF1"))
    c.rect(0, 0, width, height, fill=1)

    # Logo
    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 20*mm, height - 30*mm, width=40*mm, height=20*mm, preserveAspectRatio=True, mask='auto')

    # Header
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(HexColor("#D32F2F"))
    c.drawString(70*mm, height - 25*mm, "Hazmat Collection Waybill")

    # Section Title
    def section(title, y):
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(HexColor("#455A64"))
        c.drawString(20*mm, y, title)
        c.setStrokeColor(HexColor("#B0BEC5"))
        c.line(20*mm, y - 2*mm, width - 20*mm, y - 2*mm)
        return y - 10*mm

    # Field Block
    def field(label, value, y):
        c.setFont("Helvetica", 10)
        c.setFillColor(HexColor("#212121"))
        c.drawString(25*mm, y, f"{label}:")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(70*mm, y, value or "—")
        return y - 7*mm

    y = height - 50*mm
    y = section("Shipment Details", y)
    y = field("Reference Number", data["reference_number"], y)
    y = field("Service Type", data["service_type"], y)
    y = field("Client Reference", data["client_reference"], y)
    y = field("Pickup Date", data["pickup_date"], y)
    y = field("Inco Terms", data["inco_terms"] or "N/A", y)

    y -= 5*mm
    y = section("Collection", y)
    y = field("Company", data["collection_company"], y)
    y = field("Address", data["collection_address"], y)
    y = field("Contact Person", data["collection_person"], y)
    y = field("Contact Number", data["collection_number"], y)

    y -= 5*mm
    y = section("Delivery", y)
    y = field("Company", data["delivery_company"], y)
    y = field("Address", data["delivery_address"], y)
    y = field("Contact Person", data["delivery_person"], y)
    y = field("Contact Number", data["delivery_number"], y)

    y -= 5*mm
    y = section("Client Notes", y)
    c.setFont("Helvetica", 10)
    c.drawString(25*mm, y, data["client_notes"] or "None")

    # QR Code
    if os.path.exists(qr_path):
        c.drawImage(qr_path, width - 50*mm, 20*mm, width=30*mm, preserveAspectRatio=True, mask='auto')

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(HexColor("#607D8B"))
    c.drawString(20*mm, 10*mm, "Generated by Hazmat Global Logistics System")

    c.save()