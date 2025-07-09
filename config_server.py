from flask import Flask, request, jsonify, send_from_directory
import yaml
import json # For handling JSON input
import os
import signal
from werkzeug.exceptions import BadRequest # Import BadRequest

# app = Flask(__name__) # Default static folder is 'static'
# To serve UI from a specific directory, e.g. 'config_ui/static' and 'config_ui/templates'
# We'll assume 'static' and a root HTML file for simplicity first.
# If index.html is in 'static', it's simpler. If we want a template, then template_folder.
app = Flask(__name__, static_folder='static')


CONFIG_FILE_PATH = os.environ.get("CONFIG_FILE_PATH", "config.yaml")
FENETRE_PID_FILE = os.environ.get("FENETRE_PID_FILE", "fenetre.pid") # Used to signal fenetre.py for reload

# --- Configuration Server Settings ---
CONFIG_SERVER_HOST = os.environ.get("CONFIG_SERVER_HOST", "0.0.0.0")
CONFIG_SERVER_PORT = int(os.environ.get("CONFIG_SERVER_PORT", 8889))

@app.route('/config', methods=['GET'])
def get_config():
    try:
        if not os.path.exists(CONFIG_FILE_PATH):
            return jsonify({"error": f"Configuration file not found: {CONFIG_FILE_PATH}"}), 404
        with open(CONFIG_FILE_PATH, 'r') as f:
            config_data = yaml.safe_load(f)
        return jsonify(config_data), 200
    except Exception as e:
        return jsonify({"error": f"Error reading configuration: {str(e)}"}), 500

@app.route('/config', methods=['PUT'])
def update_config():
    try:
        if not request.is_json:
            return jsonify({"error": "Request body must be JSON."}), 415 # Unsupported Media Type

        new_config_json = request.get_json()
        if not new_config_json:
            return jsonify({"error": "Request body is empty or not valid JSON."}), 400

        if not isinstance(new_config_json, dict):
            return jsonify({"error": "Root element of the configuration must be a dictionary."}), 400

        # Convert JSON to YAML
        try:
            new_config_yaml = yaml.dump(new_config_json, sort_keys=False, default_flow_style=False, indent=2)
        except yaml.YAMLError as e: # Error during YAML conversion
            return jsonify({"error": f"Error converting JSON to YAML: {str(e)}"}), 500

        with open(CONFIG_FILE_PATH, 'w') as f:
            f.write(new_config_yaml)

        return jsonify({"message": "Configuration updated successfully (saved as YAML). Reload is required to apply changes."}), 200
    except BadRequest: # Catch errors from request.get_json() like malformed JSON
        return jsonify({"error": "Invalid JSON format in request body or empty body."}), 400
    except Exception as e: # Catch other unexpected errors
        # Log the exception e for debugging on the server side
        print(f"Unexpected error in update_config: {e}") # Or use app.logger
        return jsonify({"error": f"Error processing configuration: {str(e)}"}), 500

# --- UI Serving Routes ---

@app.route('/ui')
def serve_ui_page():
    # Serves static/index.html, assuming index.html is the main page for the UI
    # If index.html is not in the 'static' folder but e.g. in 'templates', use render_template
    # For simplicity, let's assume we'll place index.html in the root of the static folder
    # or serve it from a specific path if it's outside 'static_folder'
    # A common pattern is to have a template for the main page.
    # Let's serve 'index.html' from the root directory for now, or create a static/index.html later.
    # For now, a simple placeholder or assume it's in static.
    # Flask default static route is /static/<path:filename>
    # To serve index.html at /ui, we can explicitly define a route.
    # We will place index.html in a 'ui' subfolder within static, or serve it from project root.
    # Let's assume we'll create a 'static/index.html' and access it via /static/index.html
    # or create a specific route for /ui

    # This will serve 'static/index.html'
    return app.send_static_file('index.html')


# Flask automatically adds a static route if static_folder is set.
# e.g., /static/app.js will be served from static/app.js
# No need for specific routes for each static file if they are in the 'static' folder.

@app.route('/config/reload', methods=['POST'])
def reload_config():
    """
    Signals the main fenetre.py process to reload its configuration.
    This is a placeholder and will be more fully implemented in fenetre.py
    by having fenetre.py listen for a signal (e.g., SIGHUP or SIGUSR1).
    """
    try:
        if os.path.exists(FENETRE_PID_FILE):
            with open(FENETRE_PID_FILE, 'r') as f:
                pid_str = f.read().strip()
                if pid_str:
                    pid = int(pid_str)
                    # Send SIGHUP (1) to the process. SIGHUP is often used to signal daemons to reload configuration.
                    # Ensure fenetre.py is set up to handle this signal.
                    os.kill(pid, signal.SIGHUP)
                    return jsonify({"message": f"Reload signal sent to process {pid}."}), 200
                else:
                    return jsonify({"error": "PID file is empty."}), 500
        else:
            return jsonify({"error": f"PID file not found: {FENETRE_PID_FILE}. Cannot signal reload."}), 404

    except FileNotFoundError:
         return jsonify({"error": f"PID file not found: {FENETRE_PID_FILE}. Cannot signal reload."}), 404
    except ProcessLookupError:
        return jsonify({"error": f"Process with PID read from {FENETRE_PID_FILE} not found. It might have exited."}), 500
    except ValueError:
        return jsonify({"error": f"Invalid PID found in {FENETRE_PID_FILE}."}), 500
    except Exception as e:
        return jsonify({"error": f"Error signaling reload: {str(e)}"}), 500

def run_server():
    # Using waitress or gunicorn is recommended for production instead of Flask's built-in server.
    # For simplicity in this context, we use the built-in server.
    # Consider adding host and port configuration if needed.
    app.run(host=CONFIG_SERVER_HOST, port=CONFIG_SERVER_PORT, debug=False)

if __name__ == '__main__':
    # This allows running the config server independently for testing or in a separate process.
    print(f"Starting configuration server on http://{CONFIG_SERVER_HOST}:{CONFIG_SERVER_PORT}")
    print(f"Monitoring configuration file: {os.path.abspath(CONFIG_FILE_PATH)}")
    print(f"PID file for fenetre process: {os.path.abspath(FENETRE_PID_FILE)}")
    run_server()
