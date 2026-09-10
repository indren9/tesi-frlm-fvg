"""Esegue l'intera pipeline ISTAT nell'ordine corretto."""

from pathlib import Path
import os

import nbformat
from nbclient import NotebookClient


BASE_DIR = Path(__file__).resolve().parent
NOTEBOOKS = [
    "elaborazione_flussi.ipynb",
    "elaborazione_tempi_distanze.ipynb",
]


def main() -> None:
    os.chdir(BASE_DIR)
    for nome in NOTEBOOKS:
        percorso = BASE_DIR / nome
        print(f"Esecuzione: {nome}")
        with percorso.open(encoding="utf-8") as file_notebook:
            notebook = nbformat.read(file_notebook, as_version=4)
        NotebookClient(
            notebook,
            timeout=300,
            kernel_name="python3",
            resources={"metadata": {"path": str(BASE_DIR)}},
        ).execute()
    print("Pipeline completata con successo.")


if __name__ == "__main__":
    main()
