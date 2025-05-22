# Use official Python image as base
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements.txt and install dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire app source code to the container
COPY . .

# Expose port 5000 for the Flask app
EXPOSE 5000

# Set environment variables if needed (optional)
# ENV FLASK_ENV=production

# Run the app
CMD ["python", "app.py"]
