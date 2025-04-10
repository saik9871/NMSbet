from app import app

# This is important for Vercel serverless functions
def handler(request, response):
    return app(request, response)
