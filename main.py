# main.py
from fastapi import FastAPI, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
import sqlite3, json, os


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

os.makedirs("static/waybills", exist_ok=True)
os.makedirs("static/qrcodes", exist_ok=True)
os.makedirs("static/uploads", exist_ok=True)

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

@app.post("/signup")
def signup(payload: dict):
    email = payload.get("email")
    password = payload.get("password")
    name = payload.get("name")

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO clients (email, password, name) VALUES (?, ?, ?)", (email, password, name))
        conn.commit()
        return {"status": "success", "message": "Account created"}
    except sqlite3.IntegrityError:
        return {"status": "error", "message": "Email already registered"}
    finally:
        conn.close()

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
        return {"status": "success", "client_id": row[0], "name": row[1]}
    return {"status": "error", "message": "Invalid credentials"}

@app.get("/client/addresses/{client_id}")
def get_saved_addresses(client_id: int):
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, label, type, company, address, contact_person, contact_number
        FROM saved_addresses WHERE client_id = ?
    """, (client_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(zip(["id", "label", "type", "company", "address", "contact_person", "contact_number"], r)) for r in rows]

@app.post("/client/addresses")
def save_address(payload: dict):
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO saved_addresses (client_id, label, type, company, address, contact_person, contact_number)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        payload["client_id"], payload["label"], payload["type"],
        payload["company"], payload["address"],
        payload["contact_person"], payload["contact_number"]
    ))
    conn.commit()
    conn.close()
    return {"status": "saved"}

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
      <head>
        <title>Hazmat Collection System</title>
        <link rel="icon" href="/icon.png" type="image/png">
        <style>
          body {
            margin: 0;
            font-family: Segoe UI, sans-serif;
            background: #F1F8E9;
            display: flex;
            flex-direction: column;
            min-height: 100vh;
          }
          header {
            background: linear-gradient(to bottom, #2E7D32, #66BB6A, #C8E6C9);
            padding: 1rem;
            text-align: center;

          }
          header img {
            height: 60px;
            margin-bottom: 1rem;
          }
          .nav-bar {
  text-align: left;
  padding: 0.5rem 2rem;
  font-size: 1rem;
  color: white;
}

.nav-bar a {
  color: white;
  text-decoration: none;
  margin-right: 1rem;
  font-weight: 500;
}

.nav-bar a:hover {
  text-decoration: underline;
  color: #F1F8E9;
}
          main {
             flex: 1;
            padding: 2rem;
            max-width: 900px;
            margin: auto;
            background: #FAFAFA;

          }
          footer {
            background: linear-gradient(to right, #2E7D32, #81C784, #E8F5E9);
            color: #333;
            text-align: center;
            padding: 1rem;
            font-size: 0.9rem;

          }
        </style>
      </head>
      <body>
        <header>
          <img src="/static/logo.png" alt="Hazmat Logo" style="height:60px; margin-bottom:1rem;">
          <header>
  <img src="/static/logo.png" alt="Hazmat Logo" style="height:60px; margin-bottom:1rem;">
  <nav class="nav-bar">
    <a href="#" onclick="loadContent('home')">Home</a> |
    <a href="#" onclick="loadContent('login')">Login / Sign Up</a> |
    <a href="#" onclick="loadContent('submit')">Book a Collection</a> |
    <a href="#" onclick="loadContent('track')">Track Shipments</a> |
    <a href="#" onclick="loadContent('complaint')">File a Complaint</a> |
    <a href="#" onclick="loadContent('rate')">Rate Our Services</a>
  </nav>
</header>
        </header>
        <main id="content">
          <h2>Welcome to the Hazmat Collection System</h2>
          <p>
            The Hazmat Collection System is your all-in-one platform for booking, tracking, and managing hazardous material shipments — built for speed, simplicity, and global reach. Whether you're a local client or operating across borders, our system empowers you to:
          </p>
          <ul>
            <li>📦 Book collections effortlessly with a streamlined digital form</li>
            <li>📄 Upload all required documents directly — no printing, no email chains</li>
            <li>🔔 Receive real-time updates on every step of your shipment</li>
          </ul>
          <p>
            What sets us apart? No more back-and-forth with operations. No more missing paperwork. No more delays. Just a seamless, timeous experience that keeps your logistics moving forward — paperless, painless, and powerful.
          </p>
        </main>
        <footer>
          Hazmat Global Logistics | Johannesburg | Cape Town | Durban | support@hazmatglobal.com
        </footer>
        <script>
          function loadContent(section) {
            const content = document.getElementById("content");
            if (section === "home") {
              content.innerHTML = `<h2>Welcome to the Hazmat Collection System</h2>
                <p>The Hazmat Collection System is your all-in-one platform for booking, tracking, and managing hazardous material shipments — built for speed, simplicity, and global reach. Whether you're a local client or operating across borders, our system empowers you to:</p>
                <ul>
                  <li>📦 Book collections effortlessly with a streamlined digital form</li>
                  <li>📄 Upload all required documents directly — no printing, no email chains</li>
                  <li>🔔 Receive real-time updates on every step of your shipment</li>
                </ul>
                <p>What sets us apart? No more back-and-forth with operations. No more missing paperwork. No more delays. Just a seamless, timeous experience that keeps your logistics moving forward — paperless, painless, and powerful.</p>`;
            } else {
              fetch(`/embed/${section}`)
                .then(res => {
                  if (!res.ok) throw new Error("Failed to load content");
                  return res.text();
                })
                .then(html => {
                  content.innerHTML = html;
                })
                .catch(err => {
                  content.innerHTML = `<p style="color:red;">⚠️ Could not load section: ${section}</p>`;
                  console.error(err);
                });
            }
          }
        </script>
      </body>
    </html>
    """

@app.get("/embed/login", response_class=HTMLResponse)
def embed_login():
    return """
    <h2>Client Login / Sign Up</h2>
    <input type="email" id="email" placeholder="Email" style="width:100%; margin-bottom:8px;">
    <input type="password" id="password" placeholder="Password" style="width:100%; margin-bottom:8px;">
    <button onclick="login()">Login</button>
    <p id="login-status" style="color:red;"></p>
    <hr>
    <h3>Sign Up</h3>
    <input type="text" id="signup-name" placeholder="Name" style="width:100%; margin-bottom:8px;">
    <input type="email" id="signup-email" placeholder="Email" style="width:100%; margin-bottom:8px;">
    <input type="password" id="signup-password" placeholder="Password" style="width:100%; margin-bottom:8px;">
    <button onclick="signup()">Sign Up</button>
    <p id="signup-status" style="color:green;"></p>
    <script>
      function login() {
        fetch("/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: document.getElementById("email").value,
            password: document.getElementById("password").value
          })
        }).then(res => res.json()).then(data => {
          document.getElementById("login-status").innerText = data.message;
        });
      }
      function signup() {
        fetch("/signup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: document.getElementById("signup-name").value,
            email: document.getElementById("signup-email").value,
            password: document.getElementById("signup-password").value
          })
        }).then(res => res.json()).then(data => {
          document.getElementById("signup-status").innerText = data.message;
        });
      }
    </script>
    """
@app.get("/embed/track", response_class=HTMLResponse)
def embed_track():
    return """
    <h2>Track Your Shipment</h2>
    <input type="text" id="track-ref" placeholder="Enter HAZJNB Reference" style="width:100%; margin-bottom:8px;">
    <button onclick="trackShipment()">Track</button>
    <div id="track-result" style="margin-top:1rem;"></div>
    <script>
      function trackShipment() {
        const ref = document.getElementById("track-ref").value;
        fetch(`/driver/${ref}`)
          .then(res => res.json())
          .then(data => {
            if (data.length === 0) {
              document.getElementById("track-result").innerText = "No shipment found.";
            } else {
              document.getElementById("track-result").innerHTML = "<pre>" + JSON.stringify(data, null, 2) + "</pre>";
            }
          });
      }
    </script>
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
    <h2>File a Complaint</h2>
    <form>
      <label>Your Name</label><input type="text" style="width:100%; margin-bottom:8px;">
      <label>Your Email</label><input type="email" style="width:100%; margin-bottom:8px;">
      <labelReference Number</label><input type="text" style="width:100%; margin-bottom:8px;">
      <label>Complaint Details</label><textarea style="width:100%; height:100px;"></textarea>
      <button type="submit">Submit Complaint</button>
    </form>
    """

@app.get("/embed/rate", response_class=HTMLResponse)
def embed_rate():
    return """
    <h2>Rate Our Services</h2>
    <p>How would you rate your experience?</p>
    <select>
      <option>⭐ Poor</option>
      <option>⭐⭐ Fair</option>
      <option>⭐⭐⭐ Good</option>
      <option>⭐⭐⭐⭐ Very Good</option>
      <option>⭐⭐⭐⭐⭐ Excellent</option>
    </select>
    <br><br>
    <textarea placeholder="Additional feedback..." style="width:100%; height:100px;"></textarea>
    <br><button>Submit Rating</button>
    """


@app.get("/embed/submit", response_class=HTMLResponse)
def embed_submit_form():
    return """
    <h2>Book a Hazmat Collection</h2>
    <form action="/submit" method="post" enctype="multipart/form-data">
      <label>Service Type</label>
      <select name="serviceType">
        <option value="local">Local</option>
        <option value="export">Export</option>
        <option value="import">Import</option>
      </select>

      <label>Collection Company</label>
      <input type="text" name="collection_company_local">

      <label>Collection Address</label>
      <input type="text" name="collection_address_local">

      <label>Pickup Date</label>
      <input type="date" name="pickup_date_local">

      <label>Delivery Company</label>
      <input type="text" name="delivery_company_local">

      <label>Delivery Address</label>
      <input type="text" name="delivery_address_local">

      <label>Client Reference</label>
      <input type="text" name="client_reference_local">

      <label>Client Notes</label>
      <textarea name="client_notes_local"></textarea>

      <label>Shipment Documents</label>
      <input type="file" name="shipment_docs" multiple>

      <button type="submit">Submit Collection Request</button>
    </form>
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

@app.get("/submit", response_class=HTMLResponse)
def submit_form():
    return """
    <html>
      <head>
        <title>Book a Hazmat Collection</title>
        <link rel="icon" href="/icon.png" type="image/png">
        <style>
          body { font-family:Segoe UI; padding:2rem; background:#ECEFF1; }
          h1 { color:#D32F2F; text-align:center; }
          form { max-width:600px; margin:auto; background:white; padding:2rem; border-radius:8px; }
          label { display:block; margin-top:1rem; font-weight:bold; }
          input, textarea, select {
            width:100%; padding:0.5rem; margin-top:0.5rem;
            border:1px solid #B0BEC5; border-radius:4px;
          }
          button {
            margin-top:2rem; padding:0.75rem 1.5rem;
            background-color:#388E3C; color:white;
            border:none; border-radius:4px;
            font-size:1rem;
          }
        </style>
      </head>
      <body>
        <h1>Book a Hazmat Collection</h1>
        <h2 style="text-align:center;">Client Login</h2>
        <div id="login-section" style="max-width:600px; margin:auto; background:white; padding:1rem; border-radius:8px;">
         <input type="email" id="email" placeholder="Email" style="margin-bottom:8px; width:100%; padding:8px;">
        <input type="password" id="password" placeholder="Password" style="margin-bottom:8px; width:100%; padding:8px;">
        <button type="button" onclick="login()" style="padding:8px 16px; background-color:#D32F2F; color:white; border:none; border-radius:4px;">Login</button>
        <p id="login-status" style="color:red; margin-top:8px;"></p>
        </div>
        <form action="/submit" method="post" enctype="multipart/form-data">
          <label>Service Type</label>
          <select name="serviceType">
            <option value="local">Local</option>
            <option value="export">Export</option>
            <option value="import">Import</option>
          </select>

          <label>Collection Company</label>
          <input type="text" name="collection_company_local">

          <label>Collection Address</label>
          <input type="text" name="collection_address_local">

          <label>Pickup Date</label>
          <input type="date" name="pickup_date_local">

          <label>Delivery Company</label>
          <input type="text" name="delivery_company_local">

          <label>Delivery Address</label>
          <input type="text" name="delivery_address_local">

          <label>Client Reference</label>
          <input type="text" name="client_reference_local">

          <label>Client Notes</label>
          <textarea name="client_notes_local"></textarea>

          <label>Shipment Documents</label>
          <input type="file" name="shipment_docs" multiple>

          <button type="submit">Submit Collection Request</button>
        </form>
        <script>
            let clientId = null;

            function login() {
            const email = document.getElementById("email").value;
            const password = document.getElementById("password").value;

            fetch("/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === "success") {
                clientId = data.client_id;
                document.getElementById("login-status").innerText = "✅ Logged in as " + data.name;
                } else {
                document.getElementById("login-status").innerText = "❌ " + data.message;
                }
            });
            }
        </script>
      </body>
    </html>
    """



@app.get("/ops/assigned")
def get_assigned():
    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT reference_number, collection_company, collection_address, pickup_date, assigned_driver, status
        FROM requests WHERE assigned_driver IS NOT NULL AND status IS NOT 'Delivered'
        ORDER BY timestamp DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [{"hazjnb_ref": r[0], "company": r[1], "address": r[2], "pickup_date": r[3], "driver": r[4], "status": r[5]} for r in rows]

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
    return [{"ops": r[0], "hmj": r[1], "haz": r[2], "company": r[3], "date": r[4], "time": r[5], "update": r[6]} for r in rows]

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
    return [{"ops": r[0], "company": r[1], "delivery_date": r[2], "time": r[3], "signed_by": r[4], "document": r[5], "pod": r[6]} for r in rows]

# Remaining routes: /submit, /pdf/{id}, /confirm/{ref}, /thankyou, generate_pdf — already correct in your version

@app.post("/submit")
async def submit(request: Request):
    form = await request.form()
    files = await request.form()
    uploaded_files = request._form.getlist("shipment_docs")

    service_type = form.get("serviceType")

    def get_field(name):
        return form.get(f"{name}_local") or form.get(f"{name}_export") or form.get(f"{name}_import")

    def get_inco():
        if service_type == "local":
            return "DTD"
        return form.get("inco_terms_export") or form.get("inco_terms_import") or "N/A"

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
    inco_terms = get_inco()
    timestamp = datetime.now().isoformat()

    conn = sqlite3.connect("hazmat.db")
    cursor = conn.cursor()
    reference_number = get_next_reference_number()

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
    backup_database()

    for file in uploaded_files:
        contents = await file.read()
        with open(f"static/uploads/{reference_number}_{file.filename}", "wb") as f:
            f.write(contents)

    # ✅ QR code now links to HAZJNB reference number
    qr_url = f"https://hazmat-collection.onrender.com/confirm/{reference_number}"
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
    backup_database()

    return HTMLResponse(f"""
    <html>
      <head>
        <title>Waybill Generated</title>
        <style>
          body {{
            font-family: Segoe UI;
            background: #ECEFF1;
            text-align: center;
            padding: 2rem;
          }}
          button {{
            margin: 1rem;
            padding: 0.75rem 1.5rem;
            background-color: #388E3C;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 1rem;
            cursor: pointer;
          }}
        </style>
      </head>
      <body>
        <h1 style="color:#D32F2F;">Waybill Generated</h1>
        <p>Your waybill is ready. Click below to view or download it:</p>
        <button onclick="window.open('/pdf/{request_id}', '_blank')">📄 View Waybill PDF</button>
        <button onclick="window.location.href='/thankyou'">✅ Continue</button>
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

    c.setFillColor(HexColor("#ECEFF1"))
    c.rect(0, 0, width, height, fill=1)

    logo_path = "static/logo.png"
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 20*mm, height - 30*mm, width=40*mm, height=20*mm, preserveAspectRatio=True, mask='auto')

    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(HexColor("#D32F2F"))
    c.drawString(70*mm, height - 25*mm, "Hazmat Collection Waybill")

    def section(title, y):
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(HexColor("#455A64"))
        c.drawString(20*mm, y, title)
        c.setStrokeColor(HexColor("#B0BEC5"))
        c.line(20*mm, y - 2*mm, width - 20*mm, y - 2*mm)
        return y - 10*mm

    def field(label, value, y):
        c.setFont("Helvetica", 10)
        c.setFillColor(HexColor("#212121"))
        c.drawString(25*mm, y, f"{label}:")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(70 * mm, y, value or "—")
        return y - 7 * mm

    y = height - 50 * mm
    y = section("Shipment Details", y)
    y = field("Reference Number", data["reference_number"], y)
    y = field("Service Type", data["service_type"], y)
    y = field("Client Reference", data["client_reference"], y)
    y = field("Pickup Date", data["pickup_date"], y)
    y = field("Inco Terms", data["inco_terms"] or "N/A", y)

    y -= 5 * mm
    y = section("Collection", y)
    y = field("Company", data["collection_company"], y)
    y = field("Address", data["collection_address"], y)
    y = field("Contact Person", data["collection_person"], y)
    y = field("Contact Number", data["collection_number"], y)

    y -= 5 * mm
    y = section("Delivery", y)
    y = field("Company", data["delivery_company"], y)
    y = field("Address", data["delivery_address"], y)
    y = field("Contact Person", data["delivery_person"], y)
    y = field("Contact Number", data["delivery_number"], y)

    y -= 5 * mm
    y = section("Client Notes", y)
    c.setFont("Helvetica", 10)
    c.setFillColor(HexColor("#212121"))
    c.drawString(25 * mm, y, data["client_notes"] or "None")

    # QR Code
    if os.path.exists(qr_path):
        c.drawImage(qr_path, width - 50 * mm, 20 * mm, width=30 * mm, preserveAspectRatio=True, mask='auto')

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(HexColor("#607D8B"))
    c.drawString(20 * mm, 10 * mm, "Generated by Hazmat Global Logistics System")

    c.save()