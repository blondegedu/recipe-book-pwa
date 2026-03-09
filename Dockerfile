FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY recipe_server_multiuser.py .
COPY manifest.json .
COPY service-worker.js .

# Create data directories
RUN mkdir -p user_recipes

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "recipe_server_multiuser.py"]
