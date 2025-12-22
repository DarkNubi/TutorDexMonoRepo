FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY TutorDexBackend/requirements.txt /app/TutorDexBackend/requirements.txt
RUN pip install --no-cache-dir -r /app/TutorDexBackend/requirements.txt

COPY TutorDexBackend /app/TutorDexBackend

EXPOSE 8000

CMD ["uvicorn", "TutorDexBackend.app:app", "--host", "0.0.0.0", "--port", "8000"]

