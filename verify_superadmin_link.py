from app.db.session import SessionLocal
from app.api import dependencies
from app.schemas.organization import ERPNextLinkCreate
from app.core.services import organization_service
from app.db.models import User, Organization, LinkedOrganization

# Mock simulating the API call logic
def test_superadmin_linking():
    db = SessionLocal()
    try:
        # 1. Get Superadmin User
        superadmin = db.query(User).filter(User.role == "superadmin").first()
        if not superadmin:
            print("No superadmin found!")
            return

        print(f"User: {superadmin.email}, Role: {superadmin.role}, OrgID: {superadmin.organization_id}")

        # 2. Create a Dummy External Org (if not exists)
        test_org_name = "Verification Corp"
        org = db.query(Organization).filter(Organization.name == test_org_name).first()
        if not org:
            org = Organization(name=test_org_name, source="external")
            db.add(org)
            db.commit()
            db.refresh(org)
            print(f"Created Test Org: {org.name} (ID: {org.id})")
        else:
            print(f"Using Test Org: {org.name} (ID: {org.id})")

        # 3. Simulate POST payload
        link_in = ERPNextLinkCreate(
            erpnext_url="https://verify.erpnext.com",
            api_key="verify_key",
            api_secret="verify_secret",
            organization_id=org.id # Passing the ID!
        )

        # 4. Execute Logic (mimicking endpoints/linked_organizations.py)
        target_org_id = superadmin.organization_id
        if superadmin.role == "superadmin":
             if link_in.organization_id:
                 target_org_id = link_in.organization_id
        
        print(f"Target Org ID determined as: {target_org_id}")

        if target_org_id == superadmin.organization_id and target_org_id != org.id:
            print("FAIL: It defaulted to Superadmin's Org ID!")
        elif target_org_id == org.id:
            print("SUCCESS: It selected the provided Org ID!")
            
            # Allow linking
            organization_service.link_erpnext_to_organization(db=db, org_id=target_org_id, link_in=link_in)
            
            # Verify Link
            link = db.query(LinkedOrganization).filter(LinkedOrganization.organization_id == org.id).first()
            if link and link.erpnext_url == "https://verify.erpnext.com":
                 print("SUCCESS: Link verified in DB.")
            else:
                 print("FAIL: Link not found or incorrect.")
                 
            # Cleanup
            db.delete(link)
            db.delete(org)
            db.commit()
            print("Cleanup done.")
        else:
            print(f"FAIL: Unexpected Target ID {target_org_id}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_superadmin_linking()
