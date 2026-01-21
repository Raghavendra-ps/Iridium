from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import ALGORITHM
from app.db.session import get_db
from app.db.models import User
from app.schemas.user import TokenPayload

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)

def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> User:
    """
    Decodes JWT token to get the current user.
    Raises credentials exception if token is invalid, expired, or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        token_data = TokenPayload(sub=user_id)
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == int(token_data.sub)).first()
    
    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    A dependency that checks if the current user is active (not suspended and approved).
    This is the base-level access for any logged-in user.
    """
    if not current_user.is_active or current_user.status != 'active':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is not active or approved.")
    return current_user


def get_current_superadmin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    A dependency that checks if the current user has the 'superadmin' role.
    Used for top-level administrative tasks like managing organizations.
    """
    if current_user.role != 'superadmin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges (Superadmin required)",
        )
    return current_user


def get_current_internal_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    A dependency that checks if the current user is an internal staff member
    ('superadmin' or 'employee').
    """
    if current_user.role not in ['superadmin', 'employee']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges (Internal staff required)",
        )
    return current_user


def get_current_manager_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    A dependency that checks if the current user is a manager or above.
    ('manager', 'employee', or 'superadmin'). Used for actions within an organization.
    """
    if current_user.role not in ['superadmin', 'employee', 'manager']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges to manage this resource.",
        )
    return current_user