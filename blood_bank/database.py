# database.py
# Connects to MongoDB and prepares the 5 collections (tables)

from datetime import datetime
from pymongo import MongoClient
from werkzeug.security import generate_password_hash

# ---------- 1. CONNECTION ----------
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "blood_bank_db"

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = client[DB_NAME]

# ---------- 2. COLLECTIONS (like tables) ----------
admins = db["admins"]                  # Admin login details
donors = db["donors"]                  # Donor records
blood_stock = db["blood_stock"]        # Units available per blood group
hospitals = db["hospitals"]            # Hospital records
blood_requests = db["blood_requests"]  # Blood requests from hospitals

# ---------- 3. CONSTANTS ----------
BLOOD_GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]


# ---------- 4. SETUP FUNCTION ----------
def init_db():
    """Creates indexes, the default admin and the 8 blood group stock records."""
    admins.create_index("username", unique=True)
    blood_stock.create_index("blood_group", unique=True)

    if admins.count_documents({}) == 0:
        admins.insert_one({
            "username": "admin",
            "password": generate_password_hash("admin123"),
            "created_at": datetime.now()
        })
        print("Default admin created -> username: admin | password: admin123")

    for group in BLOOD_GROUPS:
        if blood_stock.find_one({"blood_group": group}) is None:
            blood_stock.insert_one({
                "blood_group": group,
                "units": 0,
                "last_updated": datetime.now()
            })
    print("Database is ready!")


# ---------- 5. TEST: run this file directly ----------
if __name__ == "__main__":
    try:
        client.admin.command("ping")
        print("Connected to MongoDB successfully!")
        init_db()
        print("\nBlood stock in database:")
        for item in blood_stock.find():
            print(f"  {item['blood_group']:>3} -> {item['units']} units")
    except Exception as e:
        print("Could not connect to MongoDB.")
        print("Make sure MongoDB service is running.")
        print("Error:", e)
