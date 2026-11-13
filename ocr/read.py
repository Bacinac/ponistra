"""Reads one file: read.py <source> <target>. The pages that carry text are left as they are;
Tesseract reads the others, turned upright when it is sure of their direction."""

import os
import sys

ENCRYPTED = 20
SIGNED = 21

if __name__ == "__main__":
    import ocrmypdf
    import pikepdf
    from ocrmypdf.exceptions import DigitalSignatureError

    # ocrmypdf opens a file whose restrictions need no password and writes it without them.
    try:
        with pikepdf.open(sys.argv[1]) as pdf:
            encrypted = pdf.is_encrypted
    except pikepdf.PasswordError:
        encrypted = True
    if encrypted:
        sys.exit(ENCRYPTED)
    try:
        ocrmypdf.ocr(
            sys.argv[1],
            sys.argv[2],
            language=["hrv", "eng"],
            mode="skip",
            rotate_pages=True,
            # fpdf2, the default, drops the text of an upright page a reader shows turned.
            pdf_renderer="sandwich",
            output_type="pdf",
            optimize=0,
            jobs=max(1, (os.cpu_count() or 2) // 2),
            progress_bar=False,
        )
    except DigitalSignatureError:
        sys.exit(SIGNED)
