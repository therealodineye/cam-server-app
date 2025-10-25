from flask import Flask, render_template, jsonify

# --- Global Variables ---
app = Flask(__name__)
# This will be initialized from app.py
camera_status = None
main_app = None

def init_views(camera_status_obj, app_obj):
    global camera_status, main_app
    camera_status = camera_status_obj
    main_app = app_obj

# --- Web Server Routes (API) ---

@app.route("/")
def index():
    """Serves the main HTML dashboard."""
    return render_template("index.html")

@app.route("/api/status")
def get_status():
    """Provides the current status of all cameras as JSON, safely."""
    try:
        return jsonify(camera_status.get_all())
    except Exception as e:
        # In a real application, you would want to log this error
        return jsonify({"error": str(e)}), 500

@app.route("/api/restart/<camera_name>", methods=["POST"])
def restart_camera(camera_name):
    """Restarts a specific camera thread."""
    if main_app and main_app.restart_camera_thread(camera_name):
        return jsonify({"message": f"Camera '{camera_name}' is restarting."}), 200
    else:
        return jsonify({"error": f"Camera '{camera_name}' not found or could not be restarted."}), 404