from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

# Correct: Import schemas from the dedicated schemas folder
from app.schemas import user as user_schemas 
from app.core.services import user_service
from app.core import security
from app.db.session import get_db
from app.db.models import User, Organization

router = APIRouter()


@router.get("/setup-status")
def get_setup_status(db: Session = Depends(get_db)) -> dict:
    """Public endpoint to check if the initial superadmin user has been created."""
    user_count = db.query(User).count()
    return {"setup_needed": user_count == 0}


@router.post("/initial-setup", response_model=user_schemas.User, status_code=status.HTTP_201_CREATED)
def initial_admin_setup(*, db: Session = Depends(get_db), user_in: user_schemas.UserCreate):
    """
    Creates the first superadmin and their 'Internal' organization.
    This endpoint is only active if there are NO users in the database.
    """
    if db.query(User).count() > 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Setup has already been completed.")
    
    # 1. Create the default 'Internal' organization for our own company
    internal_org = Organization(name="Internal")
    db.add(internal_org)
    db.commit()
    db.refresh(internal_org)
    
    # 2. Create the superadmin user and assign them to this organization
    superadmin = user_service.create_user(
        db=db,
        user_in=user_in,
        organization_id=internal_org.id,
        role="superadmin" # Assign the superadmin role
    )
    return superadmin


@router.post("/login", response_model=user_schemas.Token)
def login_for_access_token(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()) -> dict:
    """OAuth2 compatible token login."""
    user = user_service.authenticate_user(db, email=form_data.username, password=form_data.password)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if hasattr(user, 'authentication_error'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=user.authentication_error)

    access_token = security.create_access_token(subject=user.id)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/organizations-public")
def list_orgs_public(db: Session = Depends(get_db)):
    """Publicly list organizations for the registration dropdown."""
    return db.query(Organization).all()

@router.post("/register", response_model=user_schemas.User, status_code=status.HTTP_201_CREATED)
def register_user(*, db: Session = Depends(get_db), user_in: user_schemas.UserCreate):
    # 1. Email check
    if user_service.get_user_by_email(db, email=user_in.email):
        raise HTTPException(status_code=400, detail="Email already registered.")

    org_id = user_in.organization_id

    # 2. Organization Logic
    if not org_id:
        if not user_in.organization_name:
            raise HTTPException(status_code=400, detail="Organization Name is required to create a new organization.")
        # Check if name exists
        if db.query(Organization).filter(Organization.name == user_in.organization_name).first():
            raise HTTPException(status_code=400, detail="An organization with this name already exists.")
        
        new_org = Organization(name=user_in.organization_name)
        db.add(new_org)
        db.commit()
        db.refresh(new_org)
        org_id = new_org.id

    # 3. Create User as 'client'
    new_user = user_service.create_user(
        db=db,
        user_in=user_in,
        organization_id=org_id,
        role="client" 
    )
    return new_user