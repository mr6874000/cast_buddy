# 📺 Chromecast Controller 🚀

This project provides a simple web interface to control your Chromecast devices. You can discover devices on your network, select a device, cast content (like YouTube videos or URLs), control playback (play, pause, stop, rewind, forward), adjust volume, and view the device status. All from a convenient web UI!

## ✨ Features

*   **Device Discovery:** 🔍 Automatically scans your local network for Chromecast devices.
*   **Device Selection:** 🖱️ Choose the Chromecast you want to control from a list.
*   **Content Casting:** 🔗 Cast URLs (including YouTube links) to your selected device.
*   **Playback Controls:** ▶️⏸️⏹️⏪⏩ Full control over playback: play, pause, stop, rewind, and fast-forward.
*   **Volume Control:** 🔊 Adjust the volume with a slider.
*   **Device Status:** ℹ️ View the current status of the selected device (playing, paused, title, etc.).
*   **Web Interface:** 🌐 Access the controller through a user-friendly web interface.
*   **Dockerized:** 🐳 Easily run the application in a Docker container.
*   **Responsive Design:**📱💻 Works well on both desktop and mobile devices.

## 🛠️ Prerequisites

*   **Python 3.7+:**  Make sure you have Python 3.7 or higher installed.
*   **`catt`:** The application relies on the `catt` command-line tool.  It will be installed automatically if you use the Docker method.  If running locally, you'll need to install it: `pip install catt`
*  **Docker (Optional):** If you prefer to run the application in a container.

## 🚀 Getting Started (Docker - Recommended)

The easiest way to run the application is with Docker. This avoids any dependency issues.

1.  **Build the Docker Image:**
    ```bash
    docker build -t chromecast-controller .
    ```

2.  **Run the Docker Container:**
    ```bash
    docker run -d -p 5000:5000 --name my-chromecast-app chromecast-controller
    ```
    *   `-d`: Runs the container in detached mode (background).
    *   `-p 5000:5000`: Maps port 5000 on your host to port 5000 in the container.
    *   `--name my-chromecast-app`:  Gives the container a name (optional, but helpful).

3.  **Access the Application:** Open your web browser and go to `http://localhost:5000`.

## 🚀 Getting Started (Local Installation)

1.  **Clone the Repository:**
    ```bash
    git clone <repository_url>  # Replace <repository_url> with the actual URL
    cd <repository_directory> # Replace with directory name.
    ```

2.  **Install Dependencies:**
    ```bash
    pip install flask catt
    ```

3.  **Run the Application:**
    ```bash
    flask run --host=0.0.0.0
    ```
    *   `--host=0.0.0.0`:  Makes the application accessible from other devices on your network (not just `localhost`).

4.  **Access the Application:** Open your web browser and go to `http://localhost:5000` (or `http://<your_computer's_ip_address>:5000` to access from another device on your network).

## 📝 Project Structure

*   `app.py`:  The main Flask application file.
*   `templates/`: Contains the HTML template (`index.html`).
*   `devices.json`: Stores the list of discovered devices (created automatically).
*   `Dockerfile`:  Defines how to build the Docker image.
*   `README.md`: This file!

## 🤝 Contributing

Contributions are welcome! If you find a bug or have a feature request, please open an issue.  If you'd like to contribute code, please fork the repository and submit a pull request.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details (you'll need to create a LICENSE file and put the MIT license text in it).

## ℹ️ Notes and Troubleshooting
*  **Network:** Make sure your computer and Chromecast devices are on the same local network.
*  **Firewall:** If you have a firewall enabled, you may need to allow traffic on port 5000.
*  **`catt`:**  The application uses `catt` under the hood.  If you encounter any issues related to `catt` itself, refer to the `catt` documentation.
* **Multiple Instances:** Do *not* try to run multiple instances of this app (either locally or in Docker) on the same host using the same port (5000) without changing the port mapping.  This will cause a port conflict.  If you need multiple instances, use different port mappings (e.g., `-p 5001:5000`, `-p 5002:5000`).
* **YouTube URLs**: Sometimes, casting a youtube video might fail, but casting the playlist works.