from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates

from app.db.session import get_db
from app.db.models import User

router = APIRouter()

templates = Jinja2Templates(directory="frontend/templates")


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """
    Serves the login page.
    If no users exist in the database, it redirects to the initial setup page.
    """
    user_count = db.query(User).count()
    if user_count == 0:
        return RedirectResponse(url="/initial-setup")
    
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/initial-setup", response_class=HTMLResponse, include_in_schema=False)
async def initial_setup_page(request: Request):
    """Serves the one-time administrator setup page."""
    return templates.TemplateResponse("initial_setup.html", {"request": request})


@router.get("/upload", response_class=HTMLResponse, include_in_schema=False)
async def upload_page(request: Request):
    """Serves the main file upload page."""
    return templates.TemplateResponse(
        "upload.html", {"request": request, "active_page": "upload"}
    )


@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
async def register_page(request: Request):
    """Serves the user registration page."""
    return templates.TemplateResponse("register.html", {"request": request})


@router.get("/jobs/{job_id}/configure", response_class=HTMLResponse, include_in_schema=False)
async def job_configure_page(request: Request, job_id: int):
    """Serves the interactive page for confirming parsing configuration."""
    return templates.TemplateResponse(
        "job_configure.html", {"request": request, "job_id": job_id, "active_page": "jobs"}
    )


@router.get("/jobs/{job_id}/map-employees", response_class=HTMLResponse, include_in_schema=False)
async def job_map_employees_page(request: Request, job_id: int):
    """Serves the final step page for mapping employees."""
    return templates.TemplateResponse(
        "job_map_employees.html", {"request": request, "job_id": job_id, "active_page": "jobs"}
    )


@router.get("/jobs/{job_id}", response_class=HTMLResponse, include_in_schema=False)
async def job_detail_page(request: Request, job_id: int):
    """Serves the detail/validation page for a specific job."""
    return templates.TemplateResponse(
        "job_detail.html", {"request": request, "job_id": job_id, "active_page": "jobs"}
    )


@router.get("/home", response_class=HTMLResponse, include_in_schema=False)
async def home_page(request: Request):
    """Serves the main dashboard/home page."""
    return templates.TemplateResponse(
        "home.html", {"request": request, "active_page": "home"}
    )


@router.get("/settings", response_class=HTMLResponse, include_in_schema=False)
async def settings_page(request: Request):
    """Serves the settings page for managing mapping profiles."""
    return templates.TemplateResponse(
        "settings.html", {"request": request, "active_page": "settings"}
    )


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_center_page(request: Request):
    """Serves the new Admin Center for user management."""
    return templates.TemplateResponse(
        "admin_center.html", {"request": request, "active_page": "admin"}
    )


@router.get("/sheet-maker", response_class=HTMLResponse, include_in_schema=False)
async def sheet_maker_page(request: Request):
    """Serves the new page for generating attendance sheets."""
    return templates.TemplateResponse(
        "sheet_maker.html", {"request": request, "active_page": "sheet-maker"}
    )


@router.get("/organizations", response_class=HTMLResponse, include_in_schema=False)
async def organizations_page(request: Request):
    """Serves the new page for Superadmins to manage organizations."""
    return templates.TemplateResponse(
        "organizations.html", {"request": request, "active_page": "organizations"}
    )


@router.get("/employees", response_class=HTMLResponse, include_in_schema=False)
async def employees_page(request: Request):
    """Serves the page for Managers to manage employees in their organization."""
    return templates.TemplateResponse(
        "employees.html", {"request": request, "active_page": "employees"}
    )
    
@router.get("/check-attendance", response_class=HTMLResponse, include_in_schema=False)
async def check_attendance_page(request: Request):
    """Serves the personal attendance view for employees."""
    return templates.TemplateResponse(
        "check_attendance.html", {"request": request, "active_page": "check-attendance"}
    )
