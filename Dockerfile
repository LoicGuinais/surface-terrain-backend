# Use a geospatial base image
FROM ghcr.io/osgeo/gdal:ubuntu-full-3.8.0

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Python & pip (already present, just update)
RUN apt-get update && apt-get install -y python3-pip

# Create working directory
WORKDIR /app

# Copy files
COPY . /app

# Install Python dependencies
RUN pip3 install --upgrade pip
RUN pip3 install fastapi uvicorn pandas==2.1.4 geopandas requests


# Expose port
EXPOSE 10000

# Start the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
