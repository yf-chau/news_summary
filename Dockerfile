# Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Use Playwright’s official Python image (it already has browsers + deps).
FROM mcr.microsoft.com/playwright/python:v1.51.0-jammy

# Install Xvfb
USER root
RUN apt-get update \
    && apt-get install -y xvfb xauth x11-utils \
    && rm -rf /var/lib/apt/lists/*
USER pwuser

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
ENV HEADLESS=False

# Finally run your script
CMD ["bash","-lc","xvfb-run -a -s '-screen 0 1920x1080x24' python substack_playwright.py"]
