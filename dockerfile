# Use an official Python image
FROM python:3.13-slim

# Set work directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire app folder
COPY app ./app

# Expose the port your app runs on
EXPOSE 8080

# Set the default command to run your app with uvicorn
# Assuming 'main.py' has 'app' object: uvicorn main:app --host 0.0.0.0 --port 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

