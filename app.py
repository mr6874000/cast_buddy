from flask import Flask, request, jsonify, render_template, redirect, url_for
import catt.api
import time
import threading
import logging
import os  # Import the 'os' module
from urllib.parse import urlparse

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

def discover_devices():
    """Scans for Chromecast devices and updates the 'devices' list."""
    global devices, scan_in_progress, last_scan_timestamp

    if scan_in_progress or (time.time() - last_scan_timestamp < SCAN_COOLDOWN):
        logging.info("Scan already in progress or cooldown active.")
        return

    scan_in_progress = True
    last_scan_timestamp = time.time()

    try:
        logging.info("Starting device discovery...")
        new_devices = catt.api.discover()
        devices = []  # Clear the previous list
        for device_name in new_devices:
            try:
                # Use catt.api.get_device_info() to get the IP address
                info = catt.api.get_device_info(device_name)

                if info:
                  devices.append({"name": device_name, "ip_address": info.get("ip_address") }) # Get the IP
                  logging.info(f"Found device: {device_name} - IP: {info.get('ip_address')}") #Log Ip
                else:
                  logging.warning(f"Could not get information for device: {device_name}")

            except Exception as e:
                 logging.error(f"Error getting info for {device_name}: {e}")

        logging.info(f"Discovery found devices: {devices}")

    except Exception as e:
        logging.error(f"Error during device discovery: {e}")
    finally:
        scan_in_progress = False


def get_cast_device(device_name_or_ip):
    """
    Gets a CastDevice object by name or IP address.  Handles both cases and
    includes error handling.
    """
    try:
        if device_name_or_ip is None:
          return None
        if catt.api.validate_ip(device_name_or_ip):  # Check if it's a valid IP
            logging.info(f"Getting device by IP: {device_name_or_ip}")
            device = catt.api.CattDevice(ip_addr=device_name_or_ip)
        else:
            logging.info(f"Getting device by name: {device_name_or_ip}")
            # Resolve name to IP. Important to handle failure
            info = catt.api.get_device_info(device_name_or_ip)
            if info and "ip_address" in info:
                device = catt.api.CattDevice(ip_addr=info["ip_address"], name=device_name_or_ip) #Name and IP for CattDevice

            else:
                logging.error(f"Failed to resolve IP for device name: {device_name_or_ip}")
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
    """Renders the main page with device selection and casting options."""
    global selected_device
    return render_template('index.html', devices=devices, selected_device=selected_device)

@app.route('/scan')
def scan_devices():
    """Triggers a device scan (runs in the background)."""
    global scan_thread
    if scan_thread is None or not scan_thread.is_alive():
        scan_thread = threading.Thread(target=discover_devices)
        scan_thread.start()
        return jsonify({"message": "Scan started"})
    else:
        return jsonify({"message": "Scan already in progress"}), 409 # 409 Conflict

@app.route('/get_devices')
def get_devices_endpoint():
    """Returns the currently discovered devices as JSON."""
    return jsonify(devices)

@app.route('/select_device', methods=['POST'])
def select_device():
    """Sets the selected device."""
    global selected_device
    device_identifier = request.form.get('device')  # Could be name or IP
    logging.info(f"Attempting to select device: {device_identifier}")

    selected_device = get_cast_device(device_identifier)

    if selected_device:
        logging.info(f"Device selected: {selected_device.name} ({selected_device.ip_addr})")
        # Redirect back to the index page after successful selection.
        return redirect(url_for('index'))
    else:
        logging.error(f"Failed to select device: {device_identifier}")
        return jsonify({"message": f"Failed to select device {device_identifier}"}), 400

@app.route('/cast', methods=['POST'])
def cast_content():
    """Casts a URL or YouTube video to the selected device."""
    global selected_device
    content_url = request.form['url']

    if not selected_device:
        return jsonify({"message": "No device selected"}), 400
    if not is_valid_url(content_url):
      return jsonify({"message": "Invalid URL"}), 400

    try:
        logging.info(f"Casting {content_url} to {selected_device.name}")
        selected_device.cast_site(content_url, timeout=CAST_TIMEOUT) #Added Timeout
        return jsonify({"message": f"Casting {content_url} to {selected_device.name}"})
    except Exception as e:
        logging.error(f"Error casting: {e}")
        return jsonify({"message": f"Error casting: {e}"}), 500

@app.route('/controls', methods=['POST'])
def media_controls():
    """Handles media control actions (play, pause, stop, volume)."""
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
        elif action == 'seek':  # Add seek functionality
            position = float(request.form.get('position'))
            selected_device.seek(position)

        elif action == 'rewind':
            selected_device.rewind() # Uses default rewind

        elif action == "forward":
            selected_device.ffwd() # Uses default ffwd

        else:
            return jsonify({"message": "Invalid action"}), 400

        return jsonify({"message": f"Action '{action}' executed successfully"})

    except Exception as e:
        logging.error(f"Error in media controls: {e}")
        return jsonify({"message": f"Error: {e}"}), 500


@app.route('/status')
def get_device_status():
    """Returns the status of the selected device."""
    global selected_device
    if not selected_device:
        return jsonify({"message": "No device selected"}), 400

    try:
        status = selected_device.status
        # Convert to a more easily JSON serializable format.
        status_dict = {
            "cast_mode": status.cast_mode,
            "content_id": status.content_id,
            "display_name": status.display_name,
            "duration": status.duration,
            "player_state": status.player_state,
            "title": status.title,
            "volume_level": status.volume_level,
            "current_time" : status.current_time # Add current time
        }
        return jsonify(status_dict)

    except Exception as e:
        logging.error(f"Error getting device status: {e}")
        return jsonify({"message": f"Error getting status: {e}"}), 500


# --- Main Execution ---

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)