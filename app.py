from flask import Flask, request, jsonify, render_template, redirect, url_for
import catt.api
import time
import threading
import logging
import os
from urllib.parse import urlparse
from catt.controllers import CastController

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global Variables and State Management ---

devices = []  # Store discovered devices (name, ip_address)
selected_device = None  # Currently selected device (as a CastDevice object)
scan_in_progress = False
scan_thread = None
last_scan_timestamp = 0
SCAN_COOLDOWN = 10  # Minimum seconds between scans
CAST_TIMEOUT = 10 # Timeout in seconds for casting functions

# --- Device Discovery (using CastBrowser) ---
def discover_devices():
    """Scans for Chromecast devices using CastBrowser and updates the 'devices' list."""
    global devices, scan_in_progress, last_scan_timestamp

    if scan_in_progress or (time.time() - last_scan_timestamp < SCAN_COOLDOWN):
        logging.info("Scan already in progress or cooldown active.")
        return

    scan_in_progress = True
    last_scan_timestamp = time.time()
    devices = []  # Clear devices *before* the scan
    try:
        logging.info("Starting device discovery (using CastBrowser)...")

        # Use a CastBrowser context manager for proper resource management
        with catt.api.CastBrowser(None, None) as browser:
            browser.start_discovery()
            time.sleep(5)  # Allow time for discovery
            browser.stop_discovery()

            for service in browser.services:
                devices.append({"name": service.friendly_name, "ip_address": service.ip_address})
                logging.info(f"Found device: {service.friendly_name} - IP: {service.ip_address}")

        logging.info(f"Discovery found devices: {devices}")

    except Exception as e:
        logging.error(f"Error during device discovery: {e}")
    finally:
        scan_in_progress = False


def get_cast_device(device_name_or_ip):
    """
    Gets a CastDevice object by name or IP address.  Handles both cases.
    """
    try:
        if not device_name_or_ip:
            return None

        if catt.api.validate_ip(device_name_or_ip):
            logging.info(f"Getting device by IP: {device_name_or_ip}")
            device = catt.api.CattDevice(ip_addr=device_name_or_ip)
        else:
            logging.info(f"Getting device by name: {device_name_or_ip}")
            # Find the device in the 'devices' list by name
            for dev_info in devices:
                if dev_info["name"] == device_name_or_ip:
                    device = catt.api.CattDevice(ip_addr=dev_info["ip_address"], name=dev_info["name"])
                    return device
            logging.error(f"Device name not found: {device_name_or_ip}")
            return None

        return device
    except Exception as e:
        logging.error(f"Error getting CastDevice: {e}")
        return None

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False
# --- Flask Routes ---

@app.route('/')
def index():
    """Renders the main page."""
    global selected_device
    return render_template('index.html', selected_device=selected_device)

@app.route('/scan')
def scan_devices():
    """Triggers a device scan."""
    global scan_thread
    if scan_thread is None or not scan_thread.is_alive():
        scan_thread = threading.Thread(target=discover_devices)
        scan_thread.start()
        return jsonify({"message": "Scan started"})
    else:
        return jsonify({"message": "Scan already in progress"}), 409

@app.route('/get_devices')
def get_devices_endpoint():
    """Returns discovered devices."""
    return jsonify(devices)


@app.route('/select_device', methods=['POST'])
def select_device():
    """Sets the selected device."""
    global selected_device
    device_identifier = request.form.get('device')  # Expecting IP address
    logging.info(f"Attempting to select device: {device_identifier}")

    selected_device = get_cast_device(device_identifier)

    if selected_device:
        logging.info(f"Device selected: {selected_device.name} ({selected_device.ip_addr})")
        return jsonify({"message": "Device selected", "name": selected_device.name, "ip": selected_device.ip_addr}) # Return success with name
    else:
        logging.error(f"Failed to select device: {device_identifier}")
        return jsonify({"message": f"Failed to select device {device_identifier}"}), 400


@app.route('/cast', methods=['POST'])
def cast_content():
    """Casts a URL."""
    global selected_device
    content_url = request.form['url']

    if not selected_device:
        return jsonify({"message": "No device selected"}), 400
    if not is_valid_url(content_url):
        return jsonify({"message": "Invalid URL"}), 400

    try:
        logging.info(f"Casting {content_url} to {selected_device.name}")
        selected_device.cast_site(content_url, timeout=CAST_TIMEOUT)
        return jsonify({"message": f"Casting {content_url} to {selected_device.name}"})
    except Exception as e:
        logging.error(f"Error casting: {e}")
        return jsonify({"message": f"Error casting: {e}"}), 500

@app.route('/controls', methods=['POST'])
def media_controls():
    """Handles media controls."""
    global selected_device
    action = request.form.get('action')

    if not selected_device:
        return jsonify({"message": "No device selected"}), 400

    try:
        if action == 'play':
            selected_device.play()
        elif action == 'pause':
            selected_device.pause()
        elif action == 'stop':
            selected_device.stop()
        elif action == 'volume':
            volume_level = float(request.form.get('volume_level'))
            if 0.0 <= volume_level <= 1.0:
                selected_device.set_volume(volume_level)
            else:
                return jsonify({"message": "Invalid volume level"}), 400
        elif action == 'seek':
            position = float(request.form.get('position'))
            selected_device.seek(position)
        elif action == 'rewind':
            selected_device.rewind()
        elif action == "forward":
            selected_device.ffwd()
        else:
            return jsonify({"message": "Invalid action"}), 400

        return jsonify({"message": f"Action '{action}' executed successfully"})

    except Exception as e:
        logging.error(f"Error in media controls: {e}")
        return jsonify({"message": f"Error: {e}"}), 500


@app.route('/status')
def get_device_status():
    """Returns device status."""
    global selected_device
    if not selected_device:
        return jsonify({"message": "No device selected"}), 204  # 204 No Content

    try:
        status = selected_device.status
        status_dict = {
            "cast_mode": status.cast_mode,
            "content_id": status.content_id,
            "display_name": status.display_name,
            "duration": status.duration,
            "player_state": status.player_state,
            "title": status.title,
            "volume_level": status.volume_level,
            "current_time": status.current_time
        }
        return jsonify(status_dict)

    except Exception as e:
        logging.error(f"Error getting device status: {e}")
        return jsonify({"message": f"Error getting status: {e}"}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)