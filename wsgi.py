"""WSGI/CLI entry point for the marketplace application.

Usage:
    flask --app wsgi run          # development server
    flask --app wsgi create-admin --name "..." --email "..." --password "..."

Entirely separate from the ML system — running this does not start, use, or
affect `dashboard/app.py` (Streamlit) in any way.
"""

from app import create_app

app = create_app()
