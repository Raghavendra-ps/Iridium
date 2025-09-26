from sqlalchemy.orm import Session

from app.db.models import User
from app.api.schemas.auth import UserCreate
from app.core.security import get_password_hash

def get_user_by_email(db: Session, *, email: str) -> User | None:
    """
    Retrieves a user from the database by their email address.
    """

    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, *, user_id: int) -> User | None:
    """
    Retrieves a user from the database by their ID.
    """
    return db.query(User).filter(User.id == user_id).first()

def create_user(db: Session, *, user_in: UserCreate) -> User:
    """
    Creates a new user in the database.
    """
    # Hash the password before storing it
    hashed_password = get_password_hash(user_in.password)

    db_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
