# Use the official lightweight Python image
FROM python:3.11-slim-bookworm

# Set locale to avoid potential issues in minimal environments
ENV LANG=C.UTF-8

# Install system dependencies for:
# - OCRmyPDF (Ghostscript, qpdf, tesseract, jbig2dec, unpaper, pngquant)
# - PyMuPDF (libgl, libx11, libxext, libxrender, libglib, libfreetype)
# - Pillow/pdfplumber (libjpeg, libpng)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OCRmyPDF dependencies
    ghostscript \
    qpdf \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-deu \
    tesseract-ocr-chi-sim \
    pngquant \
    unpaper \
    jbig2dec \
    libjbig2dec0 \
    # Image libraries
    libjpeg62-turbo \
    libpng16-16 \
    # PyMuPDF dependencies
    libglib2.0-0 \
    libgl1 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/*

# Install OCRmyPDF (includes jbig2enc via pip)
RUN pip install --no-cache-dir ocrmypdf

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all other files
COPY . .

# Expose the port Flask will run on
ENV PORT=8080
EXPOSE 8080

# Run the Flask app
CMD ["python", "server.py"]
