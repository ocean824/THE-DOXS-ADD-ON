import os
import uuid
from datetime import datetime, timezone

import bcrypt
from dotenv import load_dotenv
from pymongo import MongoClient


load_dotenv('/app/backend/.env')

mongo = MongoClient(os.environ['MONGO_URL'])
db = mongo[os.environ['DB_NAME']]

email = f"uitest.client.mobile.{uuid.uuid4().hex[:8]}@example.com"
password = "TempPass12345!"

existing = db.users.find_one({"email": email}, {"_id": 0})
if existing:
    print(f"EMAIL={email}")
    print(f"PASSWORD={password}")
else:
    record = {
        "id": str(uuid.uuid4()),
        "name": "UITEST Mobile Client",
        "email": email,
        "role": "CLIENT",
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notification_preferences": {"messages": True, "tasks": True, "mentions": True},
        "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(),
    }
    db.users.insert_one(record)
    print(f"EMAIL={email}")
    print(f"PASSWORD={password}")

mongo.close()