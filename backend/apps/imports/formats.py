"""The Office files a document is imported from, by the format each is read as, with the
extension each keeps."""

from apps.blobs import store

WORD = {
    store.DOCX: "docx",
    store.DOCM: "docm",
    store.DOTX: "dotx",
    store.DOTM: "dotm",
    store.ODT: "odt",
    store.DOC: "doc",
    store.RTF: "rtf",
}
SHEETS = {
    store.XLSX: "xlsx",
    store.XLSM: "xlsm",
    store.XLTX: "xltx",
    store.XLTM: "xltm",
    store.ODS: "ods",
    store.XLS: "xls",
    store.TEXT: "csv",
}
PRESENTATIONS = {
    store.PPTX: "pptx",
    store.PPTM: "pptm",
    store.POTX: "potx",
    store.POTM: "potm",
    store.PPSX: "ppsx",
    store.PPSM: "ppsm",
    store.ODP: "odp",
    store.PPT: "ppt",
}
EXTENSIONS = WORD | SHEETS | PRESENTATIONS
# Macros and templates differ from the plain file only in parts the readers leave out.
OPEN_XML = {
    "docx": {store.DOCX, store.DOCM, store.DOTX, store.DOTM},
    "xlsx": {store.XLSX, store.XLSM, store.XLTX, store.XLTM},
    "pptx": {store.PPTX, store.PPTM, store.POTX, store.POTM, store.PPSX, store.PPSM},
}


def read_as(media_type: str) -> str:
    return "xlsx" if media_type in SHEETS else "pptx" if media_type in PRESENTATIONS else "docx"
