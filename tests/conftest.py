import os
import tempfile

# Never initialize or overwrite a user's real settings/models from tests.
os.environ["JARVIS_DATA_DIR"] = tempfile.mkdtemp(prefix="jarvis-tests-")
