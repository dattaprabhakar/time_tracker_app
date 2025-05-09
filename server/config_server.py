import os
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DATABASE_NAME = "time_tracker_db"
SECRET_KEY = os.getenv("SECRET_KEY", "your_super_secret_key_here") # CHANGE THIS!
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH") # Store hashed password

# For initial setup, you can hash a password like this:
# import bcrypt
# password = "admin_password" # Change this
# hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
# print(f"Set ADMIN_PASSWORD_HASH in .env to: {hashed.decode('utf-8')}")
# Then set ADMIN_PASSWORD_HASH in your .env file