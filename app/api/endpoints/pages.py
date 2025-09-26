from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api import dependencies
from app.db.models import User

router = APIRouter()

templates = Jinja2Templates(directory="frontend/templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serves the login page."""
    return templates.TemplateResponse("login.html", {"request": request})

@router.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """
    Serves the main file upload page.
    Authentication is handled by the JavaScript on the page itself.
    """
    return templates.TemplateResponse("upload.html", {"request": request, "active_page": "upload"})

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serves the user registration page."""
    return templates.TemplateResponse("register.html", {"request": request})

@router.get("/jobs", response_class=HTMLResponse)
async def list_jobs_page(request: Request):
    """Serves the page listing all jobs. Data is fetched by JS."""
    return templates.TemplateResponse(
        "jobs_list.html",
        {"request": request, "active_page": "jobs"}
    )

@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail_page(request: Request, job_id: int):
    """Serves the detail page for a specific job. Data is fetched by JS."""
    return templates.TemplateResponse(
        "job_detail.html",
        {"request": request, "job_id": job_id, "active_page": "jobs"}
    )

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root_redirect():
    """Redirects the root URL to the main dashboard page."""
    return RedirectResponse(url="/home")

@router.get("/home", response_class=HTMLResponse)
async def home_page(request: Request):
    """Serves the main dashboard/home page."""
    return templates.TemplateResponse("home.html", {"request": request, "active_page": "home"})

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Serves the settings page."""
    return templates.TemplateResponse("settings.html", {"request": request, "active_page": "settings"})
