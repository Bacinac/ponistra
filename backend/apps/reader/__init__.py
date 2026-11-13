"""The reader: the code that reads files someone else made (PDFium, Pillow, pikepdf, lxml over
Office files) runs in a service of its own, built from the backend's image but holding none of its
secrets, reaching no database and no stored file, each reading in a process of its own under a
ceiling of memory and time (D51). The backend sends it a file and gets back what was read."""
