# Nuvilog API image.
#
# There was no Dockerfile in the repo before CI needed one to build; this is a
# straightforward single-stage image, not a tuned production build.
FROM python:3.12-slim

# tesseract is the OCR fallback the input handler uses for scanned PDFs
# (pipeline/input_handler.py). Without it the app still runs — OCR degrades to
# an empty string — but the container wouldn't support a documented feature.
RUN apt-get update \
    && apt-get install --no-install-recommends -y tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Requirements first so a code change doesn't invalidate the dependency layer.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Uploads are written here at runtime; keep it present in the image.
RUN mkdir -p data/uploads

EXPOSE 8000

# SUPABASE_URL / SUPABASE_KEY / GEMINI_API_KEY come from the environment at
# run time — never baked into the image.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
