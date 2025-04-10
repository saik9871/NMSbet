from app import app

# This is the proper handler for Vercel serverless functions with Flask
from flask import Flask

# Export the app for Vercel serverless functions
# Vercel looks for a handler variable
handler = app.wsgi_app
