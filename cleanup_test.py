from app.db.session import SessionLocal
from app.db.models import Organization

db = SessionLocal()
try:
    org = db.query(Organization).filter(Organization.name == "Test External Corp").first()
    if org:
        print(f"Deleting test org: {org.name}")
        db.delete(org)
        db.commit()
        print("Deleted.")
    else:
        print("Test org not found.")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
