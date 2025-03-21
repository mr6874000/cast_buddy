from flask import Flask, request, jsonify, render_template
import subprocess
import time
import threading
import logging
import os
from urllib.parse import urlparse
import re
import json

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global Variables and State Management ---

# devices = []  # No longer needed at the top-level
selected_device = None
scan_in_progress = False
scan_thread = None
last_scan_timestamp = 0
SCAN_COOLDOWN = 10
CAST_TIMEOUT = 10
DEVICES_FILE = 'devices.json'  # File to store device list


# --- Device Discovery (using `catt scan`) ---

def discover_devices():
    global scan_in_progress, last_scan_timestamp  # devices removed

    if scan_in_progress or (time.time() - last_scan_timestamp < SCAN_COOLDOWN):
        logging.info("Scan already in progress or cooldown active.")
        return

    scan_in_progress = True
    last_scan_timestamp = time.time()
    devices_temp = []  # Use a temporary list to avoid global issues.
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
                    devices_temp.append({"name": device_name, "ip_address": ip_address})
                    logging.info(f"Found device: {device_name} - IP: {ip_address}")

        logging.info(f"Discovery found devices: {devices_temp}")
        save_devices(devices_temp)  # Save to file after successful scan


    except subprocess.TimeoutExpired:
        logging.error("catt scan timed out.")
    except Exception as e:
        logging.error(f"Error during device discovery: {e}")
    finally:
        scan_in_progress = False


def load_devices():
    try:
        with open(DEVICES_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logging.info(f"{DEVICES_FILE} not found or is invalid, returning empty list.")
        return []

def save_devices(devices_list):
    try:
        with open(DEVICES_FILE, 'w') as f:
            json.dump(devices_list, f)
        logging.info(f"Devices saved to {DEVICES_FILE}")
    except Exception as e:
        logging.error(f"Error saving devices to {DEVICES_FILE}: {e}")



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
    devices = load_devices() # Load devices *every time* index is loaded
    initial_volume = 0.5

    if selected_device:  #Keep selected device if there is one.
        device_found = False
        for dev in devices:
            if dev["ip_address"] == selected_device["ip_address"]: #Selected based on ip
                device_found = True
                break
        if not device_found: #If selected device is not found, unselect.
            selected_device = None

    if selected_device:  #If, after unselection checks, we still have selected_device
        try:
            # Get initial volume from the device *if* a device is selected
            status_output = subprocess.check_output(['catt', '-d', selected_device['ip_address'], 'status'], text=True, timeout=5)
            volume_match = re.search(r'volume_level:\s*([\d.]+)', status_output)
            if volume_match:
                initial_volume = float(volume_match.group(1))
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception) as e:
            logging.error(f"Error getting initial volume: {e}")
            # Keep default volume if there's an error

    return render_template('index.html', devices=devices, selected_device=selected_device, initial_volume=initial_volume) 


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
    devices = load_devices()  # Load devices from file
    return jsonify(devices)


@app.route('/select_device', methods=['POST'])
def select_device():
    global selected_device
    devices = load_devices()  #Load every time to make sure it's up to date.
    device_identifier = request.form.get('device')

    logging.info(f"Attempting to select device: {device_identifier}")  # Log the received identifier

    if not device_identifier:
        logging.warning("No device identifier provided in request.")
        return jsonify({"message": "No device identifier provided"}), 400

    for dev_info in devices:
        logging.debug(f"Checking device: {dev_info['name']} ({dev_info['ip_address']})") #log each device
        if dev_info["name"] == device_identifier or dev_info["ip_address"] == device_identifier:
            selected_device = dev_info
            logging.info(f"Device selected: {selected_device['name']} ({selected_device['ip_address']})")

            # Get the volume immediately after selecting the device
            try:
                status_output = subprocess.check_output(['catt', '-d', selected_device['ip_address'], 'status'], text=True, timeout=5)
                volume_match = re.search(r'volume_level:\s*([\d.]+)', status_output)  # Correct regex
                if volume_match:
                    initial_volume = float(volume_match.group(1))
                    logging.info(f"Initial volume for {selected_device['name']}: {initial_volume}") #Log initial volume.
                    return jsonify({"message": "Device selected", "name": selected_device['name'], "ip": selected_device['ip_address'], "volume": initial_volume})
                else:
                    logging.warning(f"Could not find volume in status output for {selected_device['name']}.")
                    #Return without the volume.
                    return jsonify({"message": "Device selected", "name": selected_device['name'], "ip": selected_device['ip_address']})

            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
                logging.error(f"Error getting initial volume after selection for {selected_device['name']}: {e}")
                # Return success, but without volume, if there's an error getting it
                return jsonify({"message": "Device selected", "name": selected_device['name'], "ip": selected_device['ip_address']})
            except Exception as e:
                logging.exception(f"Unexpected error getting initial volume for {selected_device['name']}: {e}") #use logging.exception
                return jsonify({"message": "Device selected", "name": selected_device['name'], "ip": selected_device['ip_address']})


    logging.error(f"Failed to select device: {device_identifier} - Device not found in loaded devices.") #more specific
    return jsonify({"message": f"Failed to select device {device_identifier} - Device not found"}), 400


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
            ['catt', '-d', selected_device['ip_address'], 'cast_site', content_url],
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
        device_name = selected_device.get('name', 'Unknown Device')  # Get device name, default to "Unknown Device"
        device_ip = selected_device['ip_address']
        logging.info(f"Getting status for device: {device_name} ({device_ip})")  # Log the device details

        result = subprocess.run(['catt', '-d', device_ip, 'status'], capture_output=True, text=True, timeout=CAST_TIMEOUT)

        if result.returncode != 0:
            error_message = result.stderr.strip()  # Get the error and clean it up
            logging.error(f"catt status failed for {device_name} ({device_ip}): {error_message}")
            return jsonify({"message": f"Error getting status for {device_name}: {error_message}"}), 500
        else:
            output = result.stdout.strip() #clean up output
            logging.info(f"catt status output for {device_name} ({device_ip}):\n{output}")

            # Parse the output using regular expressions (more reliable than JSON)
            status_data = {}
            status_data['device_name'] = device_name  # Include the device name in the response
            status_data['device_ip'] = device_ip

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
            
            match = re.search(r'current_time:\s*([\d.]+)', output)
            if match:
                 status_data['current_time'] = float(match.group(1))

            match = re.search(r'volume_level:\s*([\d.]+)', output)
            if match:
                status_data['volume_level'] = float(match.group(1))
            
            # Create a nicely formatted response for the client (optional, for better readability)
            formatted_response = {
                "message": f"Status for {device_name} ({device_ip})",
                "status": status_data
            }

            return jsonify(formatted_response)


    except subprocess.TimeoutExpired:
        logging.error(f"catt status timed out for {device_name} ({device_ip}).")
        return jsonify({"message": f"Status request timed out for {device_name}"}), 500
    except Exception as e:
        logging.error(f"Error getting device status for {device_name} ({device_ip}): {e}")
        return jsonify({"message": f"Error getting status for {device_name}: {e}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)