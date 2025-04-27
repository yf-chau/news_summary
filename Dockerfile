# Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Use Playwright’s official Python image (it already has browsers + deps).
FROM mcr.microsoft.com/playwright/python:latest
# Create and set working dir
WORKDIR /app

# Copy your requirements (if you have extras) and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your entire script+modules
COPY . .

# Environment tweaks
# Run Chromium in no-sandbox (required in many container runtimes)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PYTHONUNBUFFERED=1

# Launch in headless mode by default
ENV HEADLESS=true

# Finally run your script
CMD ["python", "main.py"]