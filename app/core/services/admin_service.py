from typing import List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.db.models import User
from app.schemas import user as user_schemas  # <-- CORRECTED IMPORT

def get_all_users(db: Session) -> List[User]:
    """
    Retrieves all users from the database.
    Intended for admin use only.
    """
    return db.query(User).order_by(User.id).all()

def update_user(db: Session, *, user_id: int, user_in: user_schemas.UserUpdate) -> User:
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found.")

    update_data = user_in.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_user, field, value) # This dynamically handles organization_id now
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user