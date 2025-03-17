from flask import Flask, request, jsonify, render_template
import subprocess
import time
import threading
import logging
import os
from urllib.parse import urlparse
import re

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global Variables and State Management ---

devices = []
selected_device = None
scan_in_progress = False
scan_thread = None
last_scan_timestamp = 0
SCAN_COOLDOWN = 10
CAST_TIMEOUT = 10

# --- Device Discovery (using `catt scan`) ---

def discover_devices():
    global devices, scan_in_progress, last_scan_timestamp

    if scan_in_progress or (time.time() - last_scan_timestamp < SCAN_COOLDOWN):
        logging.info("Scan already in progress or cooldown active.")
        return

    scan_in_progress = True
    last_scan_timestamp = time.time()
    devices = []
    try:
        logging.info("Starting device discovery (using catt scan)...")
        result = subprocess.run(['catt', 'scan'], capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            logging.error(f"catt scan failed: {result.stderr}")
        else:
            output = result.stdout
            logging.info(f"catt scan output:\n{output}")
            for line in output.splitlines():
                match = re.match(r'^\s*([\d\.]+)\s+-\s+(.+?)\s+-\s+.*?$', line)
                if match:
                    ip_address = match.group(1)
                    device_name = match.group(2).strip()
                    devices.append({"name": device_name, "ip_address": ip_address})
                    logging.info(f"Found device: {device_name} - IP: {ip_address}")

        logging.info(f"Discovery found devices: {devices}")

    except subprocess.TimeoutExpired:
        logging.error("catt scan timed out.")
    except Exception as e:
        logging.error(f"Error during device discovery: {e}")
    finally:
        scan_in_progress = False



def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

# --- Flask Routes ---

@app.route('/')
def index():
    global selected_device
    initial_volume = 0.5  # Default volume
    if selected_device:
        try:
            # Get initial volume from the device *if* a device is selected
            status_output = subprocess.check_output(['catt', '-d', selected_device['ip_address'], 'status'], text=True, timeout=5)
            volume_match = re.search(r'volume_level:\s*([\d.]+)', status_output)
            if volume_match:
                initial_volume = float(volume_match.group(1))
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception) as e:
            logging.error(f"Error getting initial volume: {e}")
            # Keep default volume if there's an error

    return render_template('index.html', selected_device=selected_device, initial_volume=initial_volume)


@app.route('/scan')
def scan_devices():
    global scan_thread
    if scan_thread is None or not scan_thread.is_alive():
        scan_thread = threading.Thread(target=discover_devices)
        scan_thread.start()
        return jsonify({"message": "Scan started"})
    else:
        return jsonify({"message": "Scan already in progress"}), 409

@app.route('/get_devices')
def get_devices_endpoint():
    return jsonify(devices)


@app.route('/select_device', methods=['POST'])
def select_device():
    global selected_device
    device_identifier = request.form.get('device')
    for dev_info in devices:
        if dev_info["name"] == device_identifier or dev_info["ip_address"] == device_identifier:
            selected_device = dev_info
            logging.info(f"Device selected: {selected_device['name']} ({selected_device['ip_address']})")

            # Get the volume immediately after selecting the device
            try:
                status_output = subprocess.check_output(['catt', '-d', selected_device['ip_address'], 'status'], text=True, timeout=5)
                volume_match = re.search(r'volume_level:\s*([\d.]+)', status_output)  # Correct regex
                if volume_match:
                    initial_volume = float(volume_match.group(1))
                    return jsonify({"message": "Device selected", "name": selected_device['name'], "ip": selected_device['ip_address'], "volume": initial_volume})
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception) as e:
                logging.error(f"Error getting initial volume after selection: {e}")
                # Return success, but without volume, if there's an error getting it
                return jsonify({"message": "Device selected", "name": selected_device['name'], "ip": selected_device['ip_address']})


    logging.error(f"Failed to select device: {device_identifier}")
    return jsonify({"message": f"Failed to select device {device_identifier}"}), 400



@app.route('/cast', methods=['POST'])
def cast_content():
    global selected_device
    content_url = request.form['url']

    if not selected_device:
        return jsonify({"message": "No device selected"}), 400
    if not is_valid_url(content_url):
        return jsonify({"message": "Invalid URL"}), 400

    try:
        logging.info(f"Casting {content_url} to {selected_device['name']} ({selected_device['ip_address']})")
        result = subprocess.run(
            ['catt', '-d', selected_device['ip_address'], 'cast', content_url],
            capture_output=True,
            text=True,
            timeout=CAST_TIMEOUT
        )

        if result.returncode != 0:
            logging.error(f"catt cast failed: {result.stderr}")
            return jsonify({"message": f"Error casting: {result.stderr}"}), 500
        else:
            logging.info(f"catt cast output: {result.stdout}")
            return jsonify({"message": f"Casting {content_url} to {selected_device['name']}"})

    except subprocess.TimeoutExpired:
        logging.error("catt cast timed out.")
        return jsonify({"message": "Cast timed out"}), 500
    except Exception as e:
        logging.error(f"Error casting: {e}")
        return jsonify({"message": f"Error casting: {e}"}), 500


@app.route('/controls', methods=['POST'])
def media_controls():
    global selected_device
    action = request.form.get('action')

    if not selected_device:
        return jsonify({"message": "No device selected"}), 400

    try:
        if action == 'volume':
            volume_level = float(request.form.get('volume_level'))
            if not 0.0 <= volume_level <= 1.0:
                return jsonify({"message": "Invalid volume level"}), 400
            command = ['catt', '-d', selected_device['ip_address'], 'volume', str(volume_level)]
        elif action == 'seek':
            position = float(request.form.get('position'))
            command = ['catt', '-d', selected_device['ip_address'], 'seek', str(position)]
        else:
            command = ['catt', '-d', selected_device['ip_address'], action]

        result = subprocess.run(command, capture_output=True, text=True, timeout=CAST_TIMEOUT)

        if result.returncode != 0:
            logging.error(f"catt control failed: {result.stderr}")
            return jsonify({"message": f"Error: {result.stderr}"}), 500
        else:
            logging.info(f"catt control output: {result.stdout}")
            return jsonify({"message": f"Action '{action}' executed successfully"})

    except subprocess.TimeoutExpired:
        logging.error(f"catt {action} timed out.")
        return jsonify({"message": f"{action} command timed out"}), 500
    except Exception as e:
        logging.error(f"Error in media controls: {e}")
        return jsonify({"message": f"Error: {e}"}), 500


@app.route('/status')
def get_device_status():
    global selected_device
    if not selected_device:
        return jsonify({"message": "No device selected"}), 204

    try:
        result = subprocess.run(['catt', '-d', selected_device['ip_address'], 'status'], capture_output=True, text=True, timeout=CAST_TIMEOUT)

        if result.returncode != 0:
            logging.error(f"catt status failed: {result.stderr}")
            return jsonify({"message": f"Error getting status: {result.stderr}"}), 500
        else:
            logging.info(f"catt status output: {result.stdout}")
            # Parse the output using regular expressions (more reliable than JSON)
            status_data = {}
            output = result.stdout

            # Extract relevant information using regular expressions
            match = re.search(r'state:\s*(\w+)', output)
            if match:
                status_data['state'] = match.group(1)

            match = re.search(r'display_name:\s*(.+)', output)
            if match:
                status_data['display_name'] = match.group(1).strip()

            match = re.search(r'title:\s*(.+)', output)
            if match:
                status_data['title'] = match.group(1).strip()
            
            match = re.search(r'current_time:\s*([\d.]+)', output)  #Gets current time.
            if match:
                 status_data['current_time'] = float(match.group(1))


            match = re.search(r'volume_level:\s*([\d.]+)', output)
            if match:
                status_data['volume_level'] = float(match.group(1))

            return jsonify(status_data)


    except subprocess.TimeoutExpired:
        logging.error("catt status timed out.")
        return jsonify({"message": "Status request timed out"}), 500
    except Exception as e:
        logging.error(f"Error getting device status: {e}")
        return jsonify({"message": f"Error getting status: {e}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)