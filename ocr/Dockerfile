# Tesseract reads the pages of a PDF that carry no text and ocrmypdf lays what it read over
# them as invisible text, for the backend, on a network without the internet. Ghostscript,
# unpaper and pngquant stay out: only PDF/A and image cleaning need them, and they are GPL.
FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-hrv tesseract-ocr-eng tesseract-ocr-osd python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /srv/requirements.lock
RUN python3 -m venv /opt/ocr \
    && /opt/ocr/bin/pip install --no-cache-dir --require-hashes --no-deps -r /srv/requirements.lock
COPY serve.py read.py /srv/
ENV HOME=/tmp
USER nobody
EXPOSE 8060
CMD ["/opt/ocr/bin/python", "/srv/serve.py"]
