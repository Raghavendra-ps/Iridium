from typing import Optional
from sqlalchemy.orm import Session

from app.db.models import User
from app.schemas.user import UserCreate
from app.core.security import get_password_hash, verify_password
import secrets
import string
from app.core.email import send_verification_email
import asyncio


def get_user_by_email(db: Session, *, email: str) -> User | None:
    """Retrieves a user from the database by their email address."""
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, *, user_id: int) -> User | None:
    """Retrieves a user from the database by their ID."""
    return db.query(User).filter(User.id == user_id).first()

def create_user(db: Session, *, user_in: UserCreate, organization_id: int, role: str = "manager") -> User:
    """
    Creates a new user and assigns them to an organization.
    The user is created with status 'active' by default if created by an admin,
    otherwise 'pending'.
    """
    hashed_password = get_password_hash(user_in.password)

    # Determine status based on role being assigned
    status = "active" if role in ["superadmin", "employee"] else "pending"

    db_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        organization_id=organization_id,
        role=role,
        status=status,
    )

    # Generate Verification Code (8 chars, alphanumeric)
    # Skip verification for Superadmin setup (they are active immediately)
    if role != "superadmin":
        alphabet = string.ascii_uppercase + string.digits
        code = ''.join(secrets.choice(alphabet) for i in range(8))
        db_user.verification_code = code
        db_user.is_verified = False
        
        # We need to commit to get the ID, but we also want to send the email
        # Ideally, we send email background task, but here we'll just await if running in async context
        # or just call it. Since this is sync code called by async endpoint, we might need to handle it.
        # However, for simplicity in this service, we'll assign it and let the caller/background handle it?
        # Actually, let's just generate it here. The endpoint can call the email service.
    else:
        db_user.is_verified = True # Superadmin is auto-verified

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def verify_user_email(db: Session, *, user: User, code: str) -> bool:
    """Verifies the user's email if the code matches."""
    if not user.verification_code:
        return False
        
    if user.verification_code.upper() == code.strip().upper():
        user.is_verified = True
        user.verification_code = None # Clear code after success
        db.commit()
        db.refresh(user)
        return True
    return False

def resend_verification_code(db: Session, *, user: User) -> str:
    """Generates a new code and returns it for sending."""
    alphabet = string.ascii_uppercase + string.digits
    code = ''.join(secrets.choice(alphabet) for i in range(8))
    user.verification_code = code
    db.commit()
    db.refresh(user)
    return code


def authenticate_user(db: Session, *, email: str, password: str) -> Optional[User]:
    """
    Authenticates a user, checking for password, active status, and approval.
    """
    user = get_user_by_email(db, email=email)

    if not user or not verify_password(password, user.hashed_password):
        return None

    if user.status != "active":
        user.authentication_error = "Account is pending admin approval."
        return user

    if not user.is_active:
        user.authentication_error = "Account has been suspended."
        return user

    if not user.is_verified:
        user.authentication_error = "Email not verified."
        return user

    return user