from typing import Optional
from sqlalchemy.orm import Session

from app.db.models import User
from app.schemas.user import UserCreate
from app.core.security import get_password_hash, verify_password

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
        status=status
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

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

    return user