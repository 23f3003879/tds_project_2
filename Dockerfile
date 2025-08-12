FROM python:3.11-slim

# Avoid writing pyc files and buffer stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces expects this env var
ENV PORT=7860
EXPOSE 7860

# Disable Docker sandbox in HF
ENV DISABLE_DOCKER=1

# Start the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]