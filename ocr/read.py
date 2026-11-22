"""Reads one file: read.py <source> <target>. The pages that carry text are left as they are;
Tesseract reads the others, turned upright when it is sure of their direction. A TIFF becomes
a PDF of its pages first, each image as it was stored."""

import os
import sys

ENCRYPTED = 20
SIGNED = 21
TIFF = (b"II*\0", b"MM\0*")

if __name__ == "__main__":
    import ocrmypdf
    import pikepdf
    from ocrmypdf.exceptions import DigitalSignatureError

    with open(sys.argv[1], "rb") as source:
        head = source.read(4)
    if head in TIFF:
        import img2pdf

        pages = sys.argv[1] + ".pdf"
        with open(pages, "wb") as written:
            img2pdf.convert(sys.argv[1], outputstream=written, rotation=img2pdf.Rotation.ifvalid)
        sys.argv[1] = pages
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
