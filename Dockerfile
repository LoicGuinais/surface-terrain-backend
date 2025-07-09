# ✅ Use clean Python 3.11 image
FROM python:3.11-slim

# 🧱 Install system dependencies for GDAL and geospatial stack
RUN apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    gcc \
    g++ \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 🔧 Set GDAL env vars so Python geospatial packages can find it
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

# 🏗 Set working dir and copy files
WORKDIR /app
COPY . /app

# 🐍 Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# 🚪 Open FastAPI port
EXPOSE 10000

# 🚀 Start app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
