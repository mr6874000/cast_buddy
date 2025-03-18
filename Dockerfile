# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install Flask and catt directly
RUN pip install --no-cache-dir flask catt

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable (optional, but good practice)
ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

# Run app.py when the container launches
CMD ["flask", "run"]