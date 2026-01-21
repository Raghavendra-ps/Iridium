import sys
from getpass import getpass
from sqlalchemy.orm import Session

# Add the project root to the Python path to allow imports
sys.path.append('.')

from app.db.session import SessionLocal
from app.db.models import User
from app.core.security import get_password_hash

def create_superuser():
    """
    Command-line utility to create a superuser (admin) account.
    """
    print("--- Creating Superuser ---")
    db: Session = SessionLocal()
    
    while True:
        email = input("Enter email for the admin account: ").strip()
        if not email:
            print("Email cannot be empty.")
            continue
        
        user_exists = db.query(User).filter(User.email == email).first()
        if user_exists:
            print(f"Error: A user with the email '{email}' already exists. Please choose a different email.")
            continue
        break

    while True:
        password = getpass("Enter password (will be hidden): ")
        if not password:
            print("Password cannot be empty.")
            continue
        
        password_confirm = getpass("Confirm password: ")
        if password != password_confirm:
            print("Passwords do not match. Please try again.")
            continue
        break
        
    try:
        hashed_password = get_password_hash(password)
        
        superuser = User(
            email=email,
            hashed_password=hashed_password,
            role='admin',   # Set the role directly to admin
            status='active', # Set the status directly to active
            is_active=True
        )
        
        db.add(superuser)
        db.commit()
        
        print("\n✅ Superuser created successfully!")
        print(f"   Email: {email}")
        print("   Role: admin")
        print("   Status: active")
        print("\nYou can now log in with this account.")
        
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_superuser()