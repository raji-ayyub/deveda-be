

#  Deveda Backend API (FastAPI + MongoDB + Docker)

This project is a **Dockerized FastAPI backend** with **MongoDB**, designed for local development and production-ready deployment using **Docker Compose**.

---

##  Tech Stack

* **FastAPI** — Backend framework
* **MongoDB** — Database
* **Motor** — Async MongoDB driver
* **Docker & Docker Compose** — Containerization & orchestration
* **Uvicorn** — ASGI server

---

##  Project Structure

```text
Deveda-be/
│
├── database/
│   └── database.py        # MongoDB connection
│
├── main.py                # FastAPI application
├── requirements.txt       # Python dependencies
├── Dockerfile             # API container definition
├── docker-compose.yml     # Multi-container setup (API + MongoDB)
├── .dockerignore          # Files ignored by Docker
├── .env                   # Environment variables (not committed)
└── README.md
```

---

## ⚙️ Prerequisites

Make sure you have the following installed:

* **Docker Desktop**

  * Virtualization enabled in BIOS
  * WSL 2 enabled (Windows)
* **Docker Compose v2** (comes with Docker Desktop)

Verify installation:

```bash
docker --version
docker compose version
```

---

##  Environment Variables

Create a `.env` file in the project root:

```env
MONGO_URI=mongodb://mongo:27017
DB_NAME=auth_db
```

> ⚠️ Do NOT use `localhost` here.
> Docker containers communicate using **service names**.

---

##  Running the Project (Docker Compose)

From the project root:

```bash
docker compose up --build
```

This will:

* Build the FastAPI image
* Start MongoDB
* Create an internal Docker network
* Persist MongoDB data using volumes

---

## 🌐 Accessing the Application

* **API Base URL**
   [http://localhost:8000](http://localhost:8000)

* **Swagger Docs**
   [http://localhost:8000/docs](http://localhost:8000/docs)

* **MongoDB**

  * Host: `localhost`
  * Port: `27017`
  * Database: `auth_db`

---

## 🗄 Data Persistence

MongoDB data is stored in a Docker volume:

```yaml
volumes:
  mongo_data:
```

This ensures:

* Data survives container restarts
* Safe local development
* Production-like behavior

---

##  How Container Networking Works

```text
Docker Network
│
├── api (FastAPI)
│    └── connects to mongo:27017
│
└── mongo (MongoDB)
```

* Containers communicate using **service names**
* `mongo` is resolved automatically by Docker DNS
* `localhost` inside a container refers to itself

---

##  Stopping the Containers

```bash
docker compose down
```

To also remove volumes (⚠️ deletes DB data):

```bash
docker compose down -v
```

---

##  Common Commands

Rebuild everything:

```bash
docker compose up --build
```

View running containers:

```bash
docker ps
```

View logs:

```bash
docker compose logs -f
```

---

## Deployment Notes

This setup is compatible with:

* Render
* Fly.io
* AWS (ECS / EC2)
* DigitalOcean

The same Docker image can be reused without modification.

---

##  Key Takeaways

* No local MongoDB installation needed
* No Python virtualenv required
* Consistent behavior across machines
* Production-aligned architecture

---

##  Future Improvements

* JWT authentication
* Role-based access control
* Health checks
* CI/CD pipeline
* Reverse proxy (Nginx)

