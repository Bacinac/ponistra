# LibreOffice turns the word processor files it reads into docx, the spreadsheets into xlsx
# and the presentations into pptx, for the backend's import, on a network without the internet; the fonts are the
# backend's, for the same metrics.
FROM debian:trixie-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui python3 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=fonts . /usr/share/fonts/ponistra
COPY serve.py /srv/serve.py
ENV HOME=/tmp
USER nobody
EXPOSE 8040
CMD ["python3", "/srv/serve.py"]
