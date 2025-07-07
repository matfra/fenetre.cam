from flask import Flask, request, jsonify
import yaml
import os
import threading
import signal

app = Flask(__name__)

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
        new_config_yaml = request.data.decode('utf-8')
        if not new_config_yaml:
            return jsonify({"error": "Request body is empty. YAML data expected."}), 400

        # Validate YAML structure (basic validation)
        try:
            new_config_data = yaml.safe_load(new_config_yaml)
            if not isinstance(new_config_data, dict):
                raise yaml.YAMLError("Root element must be a dictionary.")
        except yaml.YAMLError as e:
            return jsonify({"error": f"Invalid YAML format: {str(e)}"}), 400

        with open(CONFIG_FILE_PATH, 'w') as f:
            f.write(new_config_yaml)

        return jsonify({"message": "Configuration updated successfully. Reload is required to apply changes."}), 200
    except Exception as e:
        return jsonify({"error": f"Error writing configuration: {str(e)}"}), 500

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
