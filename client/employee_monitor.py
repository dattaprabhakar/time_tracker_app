import mss
import cv2
import requests
import base64
import time
import datetime
import threading
import configparser
import os
from io import BytesIO
import logging

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration ---
CONFIG_FILE = 'config_client.ini'
config = configparser.ConfigParser()

if not os.path.exists(CONFIG_FILE):
    logging.error(f"Configuration file '{CONFIG_FILE}' not found. Please create it.")
    # Create a default config if it doesn't exist
    config['settings'] = {
        'employee_id': 'default_employee',
        'server_url': 'http://localhost:5000',
        'screenshot_interval_seconds': '60',
        'webcam_frame_interval_seconds': '30',
        'webcam_enabled': 'true'
    }
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)
    logging.info(f"Default '{CONFIG_FILE}' created. Please customize it.")
    exit()

config.read(CONFIG_FILE)

EMPLOYEE_ID = config.get('settings', 'employee_id', fallback='unknown_employee')
SERVER_URL = config.get('settings', 'server_url', fallback='http://localhost:5000')
SCREENSHOT_INTERVAL = config.getint('settings', 'screenshot_interval_seconds', fallback=60)
WEBCAM_FRAME_INTERVAL = config.getint('settings', 'webcam_frame_interval_seconds', fallback=30)
WEBCAM_ENABLED = config.getboolean('settings', 'webcam_enabled', fallback=True)

SCREENSHOT_ENDPOINT = f"{SERVER_URL}/api/upload_screenshot"
VIDEO_FRAME_ENDPOINT = f"{SERVER_URL}/api/upload_frame"

# --- Global state for stopping threads ---
stop_event = threading.Event()

# --- Capture Functions ---
def capture_screenshot():
    try:
        with mss.mss() as sct:
            sct_img = sct.grab(sct.monitors[1]) # Capture the primary monitor
            img_bytes = BytesIO()
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=img_bytes)
            img_bytes.seek(0)
            img_base64 = base64.b64encode(img_bytes.read()).decode('utf-8')
            return img_base64
    except Exception as e:
        logging.error(f"Error capturing screenshot: {e}")
        return None

def capture_webcam_frame():
    if not WEBCAM_ENABLED:
        return None
    cap = None
    try:
        cap = cv2.VideoCapture(0) # 0 for default webcam
        if not cap.isOpened():
            logging.warning("Cannot open webcam.")
            return None
        
        ret, frame = cap.read()
        if ret:
            _, buffer = cv2.imencode('.jpg', frame)
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            return frame_base64
        else:
            logging.warning("Failed to capture frame from webcam.")
            return None
    except Exception as e:
        logging.error(f"Error capturing webcam frame: {e}")
        return None
    finally:
        if cap:
            cap.release()

# --- Send Data Function ---
def send_data(endpoint, payload):
    try:
        headers = {'Content-Type': 'application/json'}
        response = requests.post(endpoint, json=payload, headers=headers, timeout=10)
        response.raise_for_status() # Raise an exception for HTTP errors
        logging.info(f"Data sent to {endpoint}. Status: {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending data to {endpoint}: {e}")
        return False

# --- Worker Functions for Threads ---
def screenshot_worker():
    logging.info(f"Screenshot worker started. Interval: {SCREENSHOT_INTERVAL}s")
    while not stop_event.is_set():
        img_base64 = capture_screenshot()
        if img_base64:
            payload = {
                "employee_id": EMPLOYEE_ID,
                "image": img_base64,
                "timestamp": datetime.datetime.utcnow().isoformat()
            }
            send_data(SCREENSHOT_ENDPOINT, payload)
        
        # Wait for the interval, but check stop_event frequently
        for _ in range(SCREENSHOT_INTERVAL):
            if stop_event.is_set():
                break
            time.sleep(1)
    logging.info("Screenshot worker stopped.")


def webcam_worker():
    if not WEBCAM_ENABLED:
        logging.info("Webcam capture is disabled.")
        return

    logging.info(f"Webcam worker started. Interval: {WEBCAM_FRAME_INTERVAL}s")
    while not stop_event.is_set():
        frame_base64 = capture_webcam_frame()
        if frame_base64:
            payload = {
                "employee_id": EMPLOYEE_ID,
                "frame": frame_base64,
                "timestamp": datetime.datetime.utcnow().isoformat()
            }
            send_data(VIDEO_FRAME_ENDPOINT, payload)
        
        for _ in range(WEBCAM_FRAME_INTERVAL):
            if stop_event.is_set():
                break
            time.sleep(1)
    logging.info("Webcam worker stopped.")


# --- Main Execution ---
if __name__ == "__main__":
    logging.info(f"Employee Monitor started for ID: {EMPLOYEE_ID}")
    logging.info(f"Server URL: {SERVER_URL}")

    if not EMPLOYEE_ID or EMPLOYEE_ID == 'default_employee' or EMPLOYEE_ID == 'unknown_employee':
        logging.error("CRITICAL: 'employee_id' is not set or is default. Please configure it in config_client.ini")
        exit()
        
    screenshot_thread = threading.Thread(target=screenshot_worker, daemon=True)
    webcam_thread = threading.Thread(target=webcam_worker, daemon=True)

    screenshot_thread.start()
    if WEBCAM_ENABLED:
        webcam_thread.start()

    try:
        while True:
            # Keep the main thread alive, or handle graceful shutdown signals
            time.sleep(1)
            # Add any checks here if needed, e.g., for a command to stop
    except KeyboardInterrupt:
        logging.info("Shutdown signal received. Stopping workers...")
        stop_event.set()
        screenshot_thread.join(timeout=5)
        if WEBCAM_ENABLED and webcam_thread.is_alive():
            webcam_thread.join(timeout=5)
        logging.info("All workers stopped. Exiting.")
    except Exception as e:
        logging.error(f"An unexpected error occurred in the main loop: {e}")
        stop_event.set() # Try to stop threads on any major error