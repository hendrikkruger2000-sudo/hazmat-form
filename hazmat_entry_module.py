import dash
from dash import dcc, html, Input, Output, State
import pandas as pd
import qrcode
from fpdf import FPDF
import os
from flask import send_from_directory

# 🔗 Ref number tracker
REF_TRACKER = "ref_counter.txt"
WAYBILL_DIR = "waybills"
LOGO_PATH = "assets/hazmat_logo.png"

if not os.path.exists(WAYBILL_DIR):
    os.makedirs(WAYBILL_DIR)

def get_next_ref():
    if not os.path.exists(REF_TRACKER):
        with open(REF_TRACKER, "w") as f:
            f.write("1")
        return "HAZJHB0001"
    with open(REF_TRACKER, "r") as f:
        num = int(f.read().strip())
    ref = f"HAZJHB{num:04d}"
    with open(REF_TRACKER, "w") as f:
        f.write(str(num + 1))
    return ref

def generate_waybill(ref, data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Logo
    if os.path.exists(LOGO_PATH):
        pdf.image(LOGO_PATH, x=10, y=8, w=40)

    pdf.ln(50)
    pdf.cell(200, 10, txt=f"Waybill - {ref}", ln=True, align="C")
    pdf.ln(10)

    for key, value in data.items():
        pdf.cell(200, 10, txt=f"{key}: {value}", ln=True)

    # QR Code
    qr = qrcode.make(ref)
    qr_path = os.path.join(WAYBILL_DIR, f"{ref}_qr.png")
    qr.save(qr_path)
    pdf.image(qr_path, x=160, y=20, w=40)

    pdf.output(os.path.join(WAYBILL_DIR, f"{ref}.pdf"))

# ⚙️ Dash app
app = dash.Dash(__name__)
@app.server.route("/waybills/<path:filename>")
def serve_waybill(filename):
    return send_from_directory(WAYBILL_DIR, filename)
app.title = "Hazmat Entry + Waybill"

app.layout = html.Div([
    html.H2("New Collection Entry"),
    dcc.Location(id="pdf-redirect", refresh=True),
    dcc.Input(id="collection-address", type="text", placeholder="Collection Address"),
    dcc.Input(id="collection-contact", type="text", placeholder="Collection Contact"),
    dcc.Input(id="collection-time", type="text", placeholder="Collection Time"),
    dcc.Input(id="delivery-address", type="text", placeholder="Delivery Address"),
    dcc.Input(id="delivery-contact", type="text", placeholder="Delivery Contact"),
    dcc.Dropdown(
        options=[{"label": i, "value": i} for i in ["NORMAL", "URGENT"]],
        id="delivery-type",
        placeholder="Delivery Type"
    ),
    dcc.Dropdown(
        options=[{"label": i, "value": i} for i in ["local", "export"]],
        id="shipment-type",
        placeholder="Shipment Type"
    ),
    html.Button("Submit Collection", id="submit-button", n_clicks=0),
    html.Div(id="confirmation")
])

@app.callback(
    Output("confirmation", "children"),
    Input("submit-button", "n_clicks"),
    State("collection-address", "value"),
    State("collection-contact", "value"),
    State("collection-time", "value"),
    State("delivery-address", "value"),
    State("delivery-contact", "value"),
    State("delivery-type", "value"),
    State("shipment-type", "value"),
    prevent_initial_call=True
)
def handle_submission(n_clicks, c_addr, c_contact, c_time, d_addr, d_contact, d_type, s_type):
    ref = get_next_ref()
    data = {
        "Reference": ref,
        "Collection Address": c_addr,
        "Collection Contact": c_contact,
        "Collection Time": c_time,
        "Delivery Address": d_addr,
        "Delivery Contact": d_contact,
        "Delivery Type": d_type,
        "Shipment Type": s_type
    }
    generate_waybill(ref, data)
    pdf_url = f"/waybills/{ref}.pdf"
    return dcc.Location(href=pdf_url, id="pdf-redirect", refresh=True)

if __name__ == "__main__":
    print("🚀 Launching Hazmat Entry Module...")
    app.run(host="0.0.0.0", port=8050)