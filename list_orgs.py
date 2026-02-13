from app.db.session import SessionLocal
from app.db.models import Organization

db = SessionLocal()
try:
    print("\n--- ALL ORGANIZATIONS ---")
    orgs = db.query(Organization).all()
    for o in orgs:
        print(f"ID: {o.id}, Name: {o.name}, Source: {o.source}")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
