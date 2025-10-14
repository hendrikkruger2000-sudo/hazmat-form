from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

jobs = [
    {"ref": "HAZJHB0001", "status": "Assigned", "driver_id": "DRIVER001"},
    {"ref": "HAZJHB0002", "status": "Assigned", "driver_id": "DRIVER001"},
    {"ref": "HAZJHB0003", "status": "Delivered", "driver_id": "DRIVER002"}
]

connected_drivers = {}

@app.route("/get_jobs")
def get_jobs():
    driver_id = request.args.get("driver_id")
    assigned = [j for j in jobs if j["driver_id"] == driver_id]
    return jsonify({"jobs": assigned})

@app.route("/scan_qr", methods=["POST"])
def scan_qr():
    data = request.get_json()
    ref = data.get("ref")
    driver_id = data.get("driver_id")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for job in jobs:
        if job["ref"] == ref and job["driver_id"] == driver_id:
            job["status"] = "Collected"
            job["collected_by"] = driver_id
            job["collected_at"] = timestamp
            return jsonify({
                "status": "updated",
                "ref": ref,
                "collected_by": driver_id,
                "collected_at": timestamp
            })

    return jsonify({"error": "Ref not found or driver mismatch"}), 404

@app.route("/assign_job", methods=["POST"])
def assign_job():
    data = request.get_json()
    ref = data.get("ref")
    driver_id = data.get("driver_id")

    for job in jobs:
        if job["ref"] == ref:
            job["driver_id"] = driver_id
            job["status"] = "Assigned"
            break
    else:
        jobs.append({"ref": ref, "status": "Assigned", "driver_id": driver_id})

    # 🔔 Emit push alert to connected driver
    if driver_id in connected_drivers:
        socketio.emit("job_alert", {"ref": ref}, room=connected_drivers[driver_id])
    return jsonify({"status": "job assigned", "ref": ref})

@socketio.on("connect_driver")
def handle_connect_driver(data):
    driver_id = data.get("driver_id")
    connected_drivers[driver_id] = request.sid
    print(f"Driver {driver_id} connected.")

@socketio.on("disconnect")
def handle_disconnect():
    for driver_id, sid in connected_drivers.items():
        if sid == request.sid:
            del connected_drivers[driver_id]
            print(f"Driver {driver_id} disconnected.")
            break

@app.route("/")
def index():
    return "✅ Hazmat Backend with SocketIO is running."

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
    print("🚀 Hazmat Backend is running on http://0.0.0.0:5000")