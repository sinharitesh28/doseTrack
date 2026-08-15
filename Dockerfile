# Use the official lightweight Python image.
FROM python:3.10-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Copy local code to the container image.
ENV APP_HOME /app
WORKDIR $APP_HOME
COPY . ./

# Install production dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup using Gunicorn
# Cloud Run injects the $PORT environment variable automatically (default 8080)
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 run:app

# Cache bust: 1786509106.83383

# Bulletproof sync deploy: 1786520269.568679

# SSL CA Cert fix deploy: 1786528350.9942784

# Polling spam fix deploy: 1786777823.1136277

# SQL Time Format Fix: 1786785377.469105
