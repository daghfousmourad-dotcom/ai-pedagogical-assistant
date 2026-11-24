FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PyMuPDF, vision models and Docker CLI
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    curl \
    && curl -fsSL https://get.docker.com | sh \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV LANG=C.UTF-8

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m nltk.downloader punkt stopwords

COPY . .

EXPOSE 5005

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5005"]
