import os
import shutil
import tempfile
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.reader import serve  # noqa: E402

# A folder of the reader's own, emptied of what the readings held when it last stopped.
held = Path(tempfile.gettempdir()) / "reading"
shutil.rmtree(held, ignore_errors=True)
held.mkdir()
tempfile.tempdir = str(held)
serve.serve().serve_forever()
