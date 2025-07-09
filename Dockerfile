# Geospatial base image with GDAL pre-installed
FROM osgeo/gdal:ubuntu-small-3.8.0

# Install Python 3.11 and set it as default
RUN apt-get update && \
    apt-get install -y python3.11 python3.11-venv python3.11-distutils curl gcc g++ && \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.11 && \
    ln -sf /usr/bin/python3.11 /usr/local/bin/python && \
    ln -sf /usr/local/bin/pip /usr/local/bin/pip3 && \
    ln -sf /usr/local/bin/pip /usr/bin/pip

# Set environment variables so GDAL can be used by Python packages
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Working directory
WORKDIR /app

# Copy your code
COPY . /app

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose the API port
EXPOSE 10000

# Launch FastAPI with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
