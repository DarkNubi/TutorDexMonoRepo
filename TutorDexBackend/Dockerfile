FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/TutorDexBackend:/app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/TutorDexBackend

WORKDIR /app/TutorDexBackend

EXPOSE 8000

CMD ["uvicorn", "TutorDexBackend.app:app", "--host", "0.0.0.0", "--port", "8000"]

