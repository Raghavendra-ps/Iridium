from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.schemas import auth as auth_schemas
from app.core.services import user_service
from app.core import security
from app.db.session import get_db
from app.db.models import User

router = APIRouter()


# --- START OF NEW ENDPOINTS ---

@router.get("/setup-status")
def get_setup_status(db: Session = Depends(get_db)) -> dict:
    """
    Public endpoint to check if the initial admin user has been created.
    """
    user_count = db.query(User).count()
    return {"setup_needed": user_count == 0}


@router.post("/initial-setup", response_model=auth_schemas.User, status_code=status.HTTP_201_CREATED)
def initial_admin_setup(
    *,
    db: Session = Depends(get_db),
    user_in: auth_schemas.UserCreate,
):
    """
    Creates the very first administrator account.
    This endpoint is only active if there are NO users in the database.
    """
    user_count = db.query(User).count()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Initial setup has already been completed.",
        )
    
    # Create the user
    hashed_password = security.get_password_hash(user_in.password)
    db_user = User(
        email=user_in.email,
        hashed_password=hashed_password,
        role='admin',   # Explicitly set role to admin
        status='active', # Explicitly set status to active
        is_active=True
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

# --- END OF NEW ENDPOINTS ---


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(
    *,
    db: Session = Depends(get_db),
    user_in: auth_schemas.UserCreate,
) -> dict:
    """
    Create a new user. The account will be in a 'pending' state
    and will require admin approval.
    """
    user = user_service.get_user_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system.",
        )
    
    user_service.create_user(db, user_in=user_in)
    
    return {"message": "Registration successful. Your account is pending admin approval."}


@router.post("/login", response_model=auth_schemas.Token)
def login_for_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> dict:
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    user = user_service.authenticate_user(db, email=form_data.username, password=form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if hasattr(user, 'authentication_error'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=user.authentication_error,
        )

    access_token = security.create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer"}