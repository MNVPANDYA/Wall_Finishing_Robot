import os

# Database Configuration
SQLALCHEMY_DATABASE_URL = "sqlite:///./trajectories.db"

# CORS Configuration
CORS_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]

# API Configuration
API_TITLE = "Advanced Wall-Finishing Robot Control System"
API_DESCRIPTION = "Optimized path planning for autonomous wall-finishing robots"
API_VERSION = "1.0.0"