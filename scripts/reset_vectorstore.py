from pathlib import Path
import shutil

VECTORSTORE_DIR = Path("app/data/vectorstore")

if VECTORSTORE_DIR.exists():
    shutil.rmtree(VECTORSTORE_DIR)
    print("Vectorstore deleted successfully.")
else:
    print("No existing vectorstore found.")

VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)
print("Fresh vectorstore directory created.")