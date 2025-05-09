import os
import datetime
import base64
from io import BytesIO
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
import bcrypt # For password hashing
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

# Import config
from config_server import MONGODB_URI, DATABASE_NAME, SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD_HASH

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

# --- MongoDB Setup ---
client = MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]
screenshots_collection = db["screenshots"]
video_frames_collection = db["video_frames"]
users_collection = db["users"] # For admin users

# --- Flask-Login Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirect to 'login' view if @login_required fails

class User(UserMixin):
    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    # In a real app, you'd fetch from a users collection.
    # For simplicity, we have one hardcoded admin.
    if user_id == ADMIN_USERNAME: # Using username as ID for simplicity here
        return User(ADMIN_USERNAME, ADMIN_USERNAME)
    return None

# --- Ensure admin user exists (or create/update) ---
def setup_admin_user():
    admin_user = users_collection.find_one({"username": ADMIN_USERNAME})
    hashed_pw = ADMIN_PASSWORD_HASH.encode('utf-8') if ADMIN_PASSWORD_HASH else bcrypt.hashpw("defaultadmin".encode('utf-8'), bcrypt.gensalt())

    if not ADMIN_PASSWORD_HASH:
        print(f"WARNING: ADMIN_PASSWORD_HASH not set in .env. Using default password 'defaultadmin'. HASH: {hashed_pw.decode('utf-8')}")
        print("Please generate a secure hash and set it in .env for ADMIN_PASSWORD_HASH.")


    if not admin_user:
        users_collection.insert_one({
            "username": ADMIN_USERNAME,
            "password_hash": hashed_pw.decode('utf-8') # Store as string
        })
        print(f"Admin user '{ADMIN_USERNAME}' created/ensured.")
    elif admin_user.get("password_hash") != hashed_pw.decode('utf-8'):
         users_collection.update_one(
             {"username": ADMIN_USERNAME},
             {"$set": {"password_hash": hashed_pw.decode('utf-8')}}
         )
         print(f"Admin user '{ADMIN_USERNAME}' password hash updated from .env.")


# --- API Endpoints for Client ---
@app.route('/api/upload_screenshot', methods=['POST'])
def upload_screenshot():
    data = request.json
    employee_id = data.get('employee_id')
    image_data_b64 = data.get('image') # Base64 encoded image
    timestamp_str = data.get('timestamp')

    if not all([employee_id, image_data_b64, timestamp_str]):
        return jsonify({"status": "error", "message": "Missing data"}), 400

    try:
        timestamp = datetime.datetime.fromisoformat(timestamp_str)
        # Store image data directly for simplicity. For large scale, consider GridFS or file system.
        screenshots_collection.insert_one({
            "employee_id": employee_id,
            "image_data_b64": image_data_b64, # Storing base64 string
            "timestamp": timestamp,
            "type": "screenshot"
        })
        return jsonify({"status": "success", "message": "Screenshot uploaded"}), 201
    except Exception as e:
        app.logger.error(f"Error uploading screenshot: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/upload_frame', methods=['POST'])
def upload_video_frame():
    data = request.json
    employee_id = data.get('employee_id')
    frame_data_b64 = data.get('frame') # Base64 encoded frame
    timestamp_str = data.get('timestamp')

    if not all([employee_id, frame_data_b64, timestamp_str]):
        return jsonify({"status": "error", "message": "Missing data"}), 400

    try:
        timestamp = datetime.datetime.fromisoformat(timestamp_str)
        video_frames_collection.insert_one({
            "employee_id": employee_id,
            "frame_data_b64": frame_data_b64, # Storing base64 string
            "timestamp": timestamp,
            "type": "video_frame"
        })
        return jsonify({"status": "success", "message": "Frame uploaded"}), 201
    except Exception as e:
        app.logger.error(f"Error uploading frame: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- Web UI Routes for Admin ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Fetch admin user from DB (even though we have one, good practice)
        admin_db_user = users_collection.find_one({"username": username})

        if admin_db_user and bcrypt.checkpw(password.encode('utf-8'), admin_db_user['password_hash'].encode('utf-8')):
            user_obj = User(user_id=admin_db_user['username'], username=admin_db_user['username'])
            login_user(user_obj)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    # Get distinct employee IDs
    distinct_screenshots_ids = screenshots_collection.distinct("employee_id")
    distinct_frames_ids = video_frames_collection.distinct("employee_id")
    employee_ids = sorted(list(set(distinct_screenshots_ids + distinct_frames_ids)))
    
    selected_employee_id = request.args.get('employee_id')
    activities = []

    if selected_employee_id:
        # Fetch both screenshots and video frames, then sort by timestamp
        screenshots = list(screenshots_collection.find({"employee_id": selected_employee_id}).sort("timestamp", DESCENDING).limit(50))
        frames = list(video_frames_collection.find({"employee_id": selected_employee_id}).sort("timestamp", DESCENDING).limit(50))
        
        activities = sorted(screenshots + frames, key=lambda x: x['timestamp'], reverse=True)
        
        # Convert ObjectId to string for JSON serialization if needed by template, or use directly
        for activity in activities:
            activity['_id'] = str(activity['_id'])
            activity['timestamp_str'] = activity['timestamp'].strftime('%Y-%m-%d %H:%M:%S')


    return render_template('dashboard.html', 
                           employee_ids=employee_ids, 
                           selected_employee_id=selected_employee_id,
                           activities=activities)


if __name__ == '__main__':
    setup_admin_user() # Ensure admin user is set up
    app.run(debug=True, host='0.0.0.0', port=5000)