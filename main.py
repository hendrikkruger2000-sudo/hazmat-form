from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def form():
    return """
    <html>
        <head><title>Hazmat Collection Request</title></head>
        <body style="font-family:sans-serif;">
            <h1>Hazmat Global Collection Request</h1>
            <form action="/submit" method="post">
                Name: <input type="text" name="name"><br><br>
                Contact: <input type="text" name="contact"><br><br>
                Location: <input type="text" name="location"><br><br>
                Waste Type: <input type="text" name="waste"><br><br>
                Urgency: 
                <select name="urgency">
                    <option>Low</option>
                    <option>Medium</option>
                    <option>High</option>
                </select><br><br>
                Notes: <textarea name="notes"></textarea><br><br>
                <input type="submit" value="Submit Request">
            </form>
        </body>
    </html>
    """

@app.post("/submit")
async def submit(
    name: str = Form(...),
    contact: str = Form(...),
    location: str = Form(...),
    waste: str = Form(...),
    urgency: str = Form(...),
    notes: str = Form(...)
):
    print(f"New request from {name} at {location} for {waste} (Urgency: {urgency})")
    return {"status": "success", "message": "Request received"}