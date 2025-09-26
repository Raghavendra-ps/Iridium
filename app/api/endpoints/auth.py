from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.schemas import auth as auth_schemas
from app.core.services import user_service
from app.core import security
from app.db.session import get_db

router = APIRouter()


@router.post("/register", response_model=auth_schemas.User, status_code=status.HTTP_201_CREATED)
def register_user(
    *,
    db: Session = Depends(get_db),
    user_in: auth_schemas.UserCreate,
) -> auth_schemas.User:
    """
    Create a new user.
    """
    user = user_service.get_user_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The user with this email already exists in the system.",
        )
    new_user = user_service.create_user(db, user_in=user_in)
    return new_user


@router.post("/login", response_model=auth_schemas.Token)
def login_for_access_token(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
) -> dict:
    """
    OAuth2 compatible token login, get an access token for future requests.

    The form data should be sent as `application/x-www-form-urlencoded`.
    - `username`: The user's email address.
    - `password`: The user's password.
    """
    # Note: OAuth2PasswordRequestForm uses a field named "username" by convention,
    # which we are treating as the user's email address for authentication.
    user = user_service.get_user_by_email(db, email=form_data.username)

    # Verify that the user exists and the password is correct.
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create and return the access token for the authenticated user.
    access_token = security.create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer"}
