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
    Decodes JWT token and fetches the user from the DB. 
    This ensures that role/status changes are reflected 'live'.
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

    # Live fetch from Database
    user = db.query(User).filter(User.id == int(token_data.sub)).first()
    
    if user is None:
        raise credentials_exception

    return user


def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Base dependency: verifies account is active and approved.
    Used by all roles.
    """
    if not current_user.is_active or current_user.status != 'active':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Account is disabled or pending administrator approval."
        )
    return current_user


def get_current_superadmin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Permissions: Everything + User Management + Global Org Management.
    """
    if current_user.role != 'superadmin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin privileges required.",
        )
    return current_user


def get_current_manager_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Permissions: Can process files, link ERPNext, and manage their own org.
    Includes Superadmin as they are a superset of Manager.
    """
    if current_user.role not in ['superadmin', 'manager']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Managerial privileges required.",
        )
    return current_user


def get_current_client_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Permissions: Can access Home, Settings, and Sheet Maker.
    Includes Managers and Superadmins.
    """
    if current_user.role not in ['superadmin', 'manager', 'client']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Client access required.",
        )
    return current_user


def get_current_employee_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Permissions: View-only access to their own personal attendance.
    Includes everyone above them for support purposes.
    """
    if current_user.role not in ['superadmin', 'manager', 'employee']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to employees and staff.",
        )
    return current_user


def get_current_internal_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Legacy helper: restricted to staff who handle background processing (Superadmin/Manager).
    """
    if current_user.role not in ['superadmin', 'manager']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Internal staff privileges required.",
        )
    return current_user