import unicodedata
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

from apps.reader import client


def texts(path: Path) -> list[str]:
    """The text of each page, in order, as the reader reads it."""
    return client.ask("pdf_text", path)


def found(path: Path, query: str, most: int) -> list[tuple[int, list[list[float]]]] | None:
    """Where the query is found, as the reader finds it (`hits`)."""
    return client.ask("pdf_hits", path, query=query, most=most)


def read(path: Path) -> list[str]:
    """The text of each page, in order; in the reader."""
    pdf = pdfium.PdfDocument(path)
    try:
        texts = []
        for page in pdf:
            text = page.get_textpage()
            texts.append(text.get_text_range().replace("\r\n", "\n").replace("\x00", ""))
            text.close()
            page.close()
        return texts
    finally:
        pdf.close()


def folded(text: str) -> str:
    """Text as a search compares it: without case, accents or ligatures."""
    return "".join(
        each for each in unicodedata.normalize("NFKD", text) if unicodedata.category(each) != "Mn"
    ).casefold()


def _page(text: pdfium.PdfTextPage) -> tuple[str, list[int]]:
    """The page's text folded, its spaces one each, and the character each place comes from."""
    made: list[str] = []
    owners: list[int] = []
    for index in range(text.count_chars()):
        code = pdfium_c.FPDFText_GetUnicode(text.raw, index)
        char = chr(code) if 0 < code < 0x110000 else " "
        if char.isspace():
            if made and made[-1] != " ":
                made.append(" ")
                owners.append(index)
            continue
        for each in folded(char):
            made.append(each)
            owners.append(index)
    return "".join(made), owners


def _lines(boxes: list[tuple[float, float, float, float]]) -> list[list[float]]:
    """Characters' boxes in reading order joined into one rectangle each line."""
    lines: list[list[float]] = []
    for left, bottom, right, top in boxes:
        if lines:
            line = lines[-1]
            height = min(top - bottom, line[3] - line[1])
            shared = min(top, line[3]) - max(bottom, line[1])
            gap = max(left, line[0]) - min(right, line[2])
            if shared > height / 2 and gap < height:
                lines[-1] = [
                    min(left, line[0]),
                    min(bottom, line[1]),
                    max(right, line[2]),
                    max(top, line[3]),
                ]
                continue
        lines.append([left, bottom, right, top])
    return [[round(value, 2) for value in line] for line in lines]


def hits(path: Path, query: str, most: int) -> list[tuple[int, list[list[float]]]] | None:
    """Each place the query is found, as a page and the rectangles its text covers there, or
    None where it is found more than most times; in the reader."""
    wanted = " ".join(folded(query).split())
    found: list[tuple[int, list[list[float]]]] = []
    pdf = pdfium.PdfDocument(path)
    try:
        for number, page in enumerate(pdf, start=1):
            text = page.get_textpage()
            try:
                content, owners = _page(text)
                at = content.find(wanted)
                while at >= 0 and wanted:
                    chars = sorted({owners[place] for place in range(at, at + len(wanted))})
                    boxes = [text.get_charbox(index, loose=True) for index in chars]
                    rects = _lines([box for box in boxes if box[2] > box[0] and box[3] > box[1]])
                    if rects:
                        found.append((number, rects))
                    if len(found) > most:
                        return None
                    at = content.find(wanted, at + len(wanted))
            finally:
                text.close()
                page.close()
        return found
    finally:
        pdf.close()
