import sys
from app.db.session import SessionLocal
from app.core.services import organization_service
from app.schemas.organization import ExternalOrganizationCreate
from app.db.models import Organization

db = SessionLocal()
try:
    print("Attempting to create external org 'Test External Corp'...")
    ext_in = ExternalOrganizationCreate(
        name="Test External Corp",
        erpnext_url="https://test.erpnext.com",
        api_key="key123",
        api_secret="secret123"
    )
    org = organization_service.create_external_organization(db=db, ext_in=ext_in)
    print(f"Created Org ID: {org.id}")
    print(f"Name: {org.name}")
    print(f"Source: {org.source}")
    
    # Verify DB persistence
    db.expire_all()
    org_refetched = db.query(Organization).get(org.id)
    print(f"Refetched Source: {org_refetched.source}")
    
    if org_refetched.source != 'external':
        print("FAIL: Source is not external!")
    else:
        print("SUCCESS: Source is external.")

except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
