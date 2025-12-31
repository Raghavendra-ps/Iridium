# Iridium — Gretis DataPort

![Python Version](https://img.shields.io/badge/python-3.10-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
[![Built with FastAPI](https://img.shields.io/badge/Built%20with-FastAPI-green.svg)](https://fastapi.tiangolo.com/)

**Gretis DataPort** is a dynamic, template-driven ETL platform designed to automate the painful process of data extraction, validation, and submission to ERPNext. It transforms messy, inconsistent spreadsheets and documents into clean, structured attendance records through a user-friendly web interface—eliminating the need for manual data entry or custom scripts for every new file format.

---

## Key Features

* **Template-Driven Parsing Engine:** Create "Import Templates" from the UI to define how to read virtually any column-based Excel/CSV file.
* **Multiple Parsing Modes:** Supports `MATRIX` (daily grid attendance) and `DATE_REFERENCE` (leave summary) formats.
* **Dynamic Code Mapping:** Build reusable "Mapping Profiles" to translate source codes (e.g., `P`, `A`, `WO`) into ERPNext statuses (`Present`, `Absent`, `Ignore`, etc.).
* **Interactive Validation Workbench:** Review and edit extracted records in a full-page grid before submission.
* **Asynchronous Background Processing:** Celery workers process files and submissions without blocking the UI.
* **Secure & Multi-Tenant:** User data, linked organizations, and templates are isolated.
* **Containerized & Production-Ready:** Fully Dockerized for consistent development and deployment.

---

## Technology Stack

* **Backend:** FastAPI, Python 3.10  
* **Task Queue:** Celery  
* **Message Broker & Cache:** Redis  
* **Database:** PostgreSQL + SQLAlchemy  
* **Data Processing:** Pandas  
* **File Extraction:** OpenPyXL (Excel), python-docx (Word), PyPDF2/pdf2image (PDF), Tesseract (OCR)  
* **Frontend:** Jinja2, vanilla JavaScript  
* **Grid UI:** Handsontable  
* **Containerization:** Docker & Docker Compose  

---

## Getting Started

Follow these instructions to run Gretis DataPort locally for development and testing.

### Prerequisites

* [Git](https://git-scm.com/)
* [Docker](https://www.docker.com/products/docker-desktop/)
* [Docker Compose](https://docs.docker.com/compose/install/)

---

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd Iridium
```
  

### 2. Configure Environment Variables

The application uses a .env file for configuration. A .env.example file is provided as a template.
code Bash

    
```bash
cp .env.example .env
```
  
Now, open the .env file and edit the variables. At a minimum, you must set:

  SECRET_KEY for JWT token encryption (you can generate one with openssl rand -hex 32).

  PostgreSQL connection details (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB).

### 3. Build and Run the Application

Use Docker Compose to build the images and start all the services (api, worker, db, redis).
code Bash

    
```bash
docker-compose up --build
```
  
Add the -d flag (docker-compose up --build -d) to run the containers in detached mode (in the background).

The first time you run this, it will download the base images and build the application containers, which may take a few minutes. The api service will automatically run the initial_data.py script to create the necessary database tables.

### 4. Accessing the Application

Once the containers are running, you can access the services:

  Web Application: http://localhost:8088

  API Documentation (Swagger UI): http://localhost:8088/docs

### 5. Stopping the Application

To stop the application, press Ctrl+C in the terminal where compose is running, or if in detached mode, run:

```bash

docker-compose down

```

To perform a full reset (stopping containers, removing networks, and deleting the database and Redis volumes), use:

```bash

docker-compose down -v --remove-orphans

```

## Project Architecture

The application is composed of four main containerized services:

- **api:** The FastAPI web server that handles all user-facing requests, API endpoints, authentication, and queues background tasks.
- **worker:** A Celery worker that processes queued jobs from Redis, performing file parsing, OCR, data transformation, and ERPNext submission.
- **db:** A PostgreSQL database for persistent storage of users, templates, jobs, and all application data.
- **redis:** A Redis instance serving as both the Celery message broker and results backend.

---

## Core Concepts

### Import Templates

An Import Template is a user-defined recipe that tells the engine how to parse a specific file layout.

- **Parsing Mode:** Controls how data should be interpreted.
  - `MATRIX`: Classic grid-style attendance where days are columns.
  - `DATE_REFERENCE`: Summary sheets that list dates of absence rather than daily markers.
  
- **Configuration:** User-provided mappings that link template logic to actual column headers in the uploaded file (example: mapping `employee_id_column` to `Empl Code` in Excel).

### Code Mapping Profiles

A Mapping Profile is a reusable dictionary translating source file codes into ERPNext attendance statuses.  
This is primarily used with `MATRIX` templates.

**Example:**  
Map the code `WO` (Weekly Off) to `IGNORE` so it is skipped during ERPNext submission.

---

## 📄 Environment Variables

All configuration is managed through the `.env` file.

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Random string for signing tokens and encrypting secrets | `openssl rand -hex 32` |
| `POSTGRES_SERVER` | PostgreSQL server hostname | `db` |
| `POSTGRES_USER` | Database username | `iridium_user` |
| `POSTGRES_PASSWORD` | Database password | `your_strong_password` |
| `POSTGRES_DB` | Name of the database | `iridium_db` |
| `REDIS_HOST` | Redis hostname | `redis` |
| `REDIS_PORT` | Redis port | `6379` |
| `ENVIRONMENT` | Application mode | `development` or `production` |

---

## 🗺️ Future Roadmap

- Automated testing for reliability and regression prevention
- Real-time validation warnings in the grid for duplicates and missing or invalid data
- Enhanced UI/UX: auto-save drafts, bulk editing tools, improved keyboard navigation
- Observability: structured logging integration and error tracking
- CI/CD pipeline using GitHub Actions

---

## 📜 License

This project is licensed under the **MIT License**.
