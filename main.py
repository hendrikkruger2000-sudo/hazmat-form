from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, FileResponse
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
    inco_terms = form.get("inco_terms") if service_type in ["export", "import"] else ""
    timestamp = datetime.now().isoformat()

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO requests (
            service_type, collection_company, collection_address, collection_person, collection_number,
            delivery_company, delivery_address, delivery_person, delivery_number,
            client_reference, pickup_date, inco_terms, client_notes, pdf_path, timestamp
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        service_type,
        form.get("collection_company"),
        form.get("collection_address"),
        form.get("collection_person"),
        form.get("collection_number"),
        form.get("delivery_company"),
        form.get("delivery_address"),
        form.get("delivery_person"),
        form.get("delivery_number"),
        form.get("client_reference"),
        form.get("pickup_date"),
        inco_terms,
        form.get("client_notes"),
        "",  # placeholder for pdf_path
        timestamp
    ))
    request_id = cursor.lastrowid
    conn.commit()
    conn.close()

    qr_url = f"http://localhost:8000/confirm/{request_id}"
    qr_img = qrcode.make(qr_url)
    qr_path = f"static/qrcodes/qr_{request_id}.png"
    qr_img.save(qr_path)

    pdf_path = f"static/waybills/waybill_{request_id}.pdf"
    generate_pdf(form, request_id, qr_path, pdf_path)

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
    return FileResponse(path, media_type="application/pdf", filename=f"waybill_{request_id}.pdf")

@app.get("/thankyou", response_class=HTMLResponse)
def thank_you():
    return HTMLResponse("<h1>Thank you! Your request has been submitted.</h1>")

@app.get("/confirm/{request_id}", response_class=HTMLResponse)
def confirm(request_id: int):
    return HTMLResponse(f"<h1>Driver confirmed request #{request_id}</h1>")

def generate_pdf(form, request_id, qr_path, pdf_path):
    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    # Background
    c.setFillColor(HexColor("#ECEFF1"))
    c.rect(0, 0, width, height, fill=1)

    # Logo
    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 20*mm, height - 40*mm, width=50*mm, preserveAspectRatio=True, mask='auto')

    # Header
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(HexColor("#D32F2F"))
    c.drawString(80*mm, height - 30*mm, "Hazmat Collection Waybill")

    # Section Title
    def section(title, y):
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(HexColor("#D32F2F"))
        c.drawString(20*mm, y, title)
        return y - 8*mm

    # Field Block
    def field(label, value, y):
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(HexColor("#212121"))
        c.drawString(20*mm, y, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(60*mm, y, value or "—")
        return y - 7*mm

    y = height - 50*mm
    y = section("Shipment Details", y)
    y = field("Service Type", form.get("serviceType"), y)
    y = field("Client Reference", form.get("client_reference"), y)
    y = field("Pickup Date", form.get("pickup_date"), y)
    y = field("Inco Terms", form.get("inco_terms") or "N/A", y)

    y -= 5*mm
    y = section("Collection", y)
    y = field("Company", form.get("collection_company"), y)
    y = field("Address", form.get("collection_address"), y)
    y = field("Contact Person", form.get("collection_person"), y)
    y = field("Contact Number", form.get("collection_number"), y)

    y -= 5*mm
    y = section("Delivery", y)
    y = field("Company", form.get("delivery_company"), y)
    y = field("Address", form.get("delivery_address"), y)
    y = field("Contact Person", form.get("delivery_person"), y)
    y = field("Contact Number", form.get("delivery_number"), y)

    y -= 5*mm
    y = section("Client Notes", y)
    c.setFont("Helvetica", 10)
    c.drawString(20*mm, y, form.get("client_notes") or "None")

    # QR Code
    if os.path.exists(qr_path):
        c.drawImage(qr_path, width - 50*mm, 20*mm, width=30*mm, preserveAspectRatio=True, mask='auto')

    c.save()