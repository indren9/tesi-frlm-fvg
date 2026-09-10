#!/usr/bin/env python3
r"""Auto-watch del notebook autorevole della tesi.

Osserva SOLO:
    Notebook\Tesi_FRLM_FVG.ipynb

Quando il contenuto cambia realmente:
- attende che il file sia stabile;
- confronta SHA-256 con l'ultimo build PASS;
- richiama la pipeline canonica build_tesi.py;
- crea un nuovo Output_Tesi\build_YYYYMMDD_HHMMSS.

V2: forza UTF-8 anche per il subprocess di build, così percorsi come
"Università" restano corretti nei log.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

STATE_ROOT = Path.home() / ".tesi-build-watch"
STATE_FILE = STATE_ROOT / "watch_state.json"
LOG_FILE = STATE_ROOT / "watch.log"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def log(message: str) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    with LOG_FILE.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")
    try:
        print(line, flush=True)
    except Exception:
        pass


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(data: dict) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, STATE_FILE)


def latest_pass_hash(out_dir: Path) -> str | None:
    if not out_dir.exists():
        return None

    builds = sorted(
        (p for p in out_dir.iterdir() if p.is_dir() and p.name.startswith("build_")),
        key=lambda p: p.name,
        reverse=True,
    )

    for build in builds:
        report = build / "BUILD_REPORT.txt"
        if not report.exists():
            continue
        try:
            text = report.read_text(encoding="utf-8")
        except Exception:
            continue
        if "STATUS = PASS" not in text:
            continue
        for line in text.splitlines():
            if line.startswith("NOTEBOOK_SHA256 = "):
                return line.split("=", 1)[1].strip()

    return None


def run_build(build_script: Path, notebook: Path, out_dir: Path) -> int:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    log("AUTO BUILD START")

    p = subprocess.run(
        [
            sys.executable,
            str(build_script),
            str(notebook),
            "--out-dir",
            str(out_dir),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    log(f"AUTO BUILD EXIT={p.returncode}")

    for line in p.stdout.splitlines():
        log("BUILD | " + line)

    return p.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notebook", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--debounce-seconds", type=float, default=15.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    notebook = Path(args.notebook).resolve()
    out_dir = Path(args.out_dir).resolve()
    build_script = Path(__file__).with_name("build_tesi.py").resolve()

    if not notebook.exists():
        log(f"ERROR notebook non trovato: {notebook}")
        return 2
    if not build_script.exists():
        log(f"ERROR build_tesi.py non trovato: {build_script}")
        return 2

    if args.force:
        return run_build(build_script, notebook, out_dir)

    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    current_hash = sha256(notebook)
    pass_hash = latest_pass_hash(out_dir)

    state = load_state()
    state.update({
        "notebook": str(notebook),
        "out_dir": str(out_dir),
        "last_seen_sha256": current_hash,
    })
    save_state(state)

    # Se all'avvio il master è diverso dall'ultimo PASS, recupera automaticamente.
    if current_hash != pass_hash:
        log("Master diverso dall'ultimo build PASS: avvio recovery build.")
        rc = run_build(build_script, notebook, out_dir)
        if rc == 0:
            current_hash = sha256(notebook)
            state["last_seen_sha256"] = current_hash
            save_state(state)

    if args.once:
        return 0

    log(f"WATCH START: {notebook}")
    last_observed = sha256(notebook)
    last_failed_hash = None

    while True:
        try:
            time.sleep(args.poll_seconds)
            observed = sha256(notebook)

            if observed == last_observed:
                continue

            log("Cambio rilevato; attendo stabilizzazione file.")
            time.sleep(args.debounce_seconds)
            stable = sha256(notebook)

            if stable != observed:
                last_observed = stable
                log("File ancora in modifica; rimando al prossimo ciclo.")
                continue

            pass_hash = latest_pass_hash(out_dir)

            if stable == pass_hash:
                last_observed = stable
                last_failed_hash = None
                log("Cambio già coperto da un build PASS; nessun nuovo output.")
                continue

            if stable == last_failed_hash:
                last_observed = stable
                continue

            rc = run_build(build_script, notebook, out_dir)

            if rc == 0:
                # build_tesi esegue il master in place; acquisisci l'hash finale.
                last_observed = sha256(notebook)
                last_failed_hash = None
                state["last_seen_sha256"] = last_observed
                save_state(state)
            else:
                last_observed = stable
                last_failed_hash = stable

        except FileNotFoundError:
            log("Notebook temporaneamente non disponibile; attendo.")
            time.sleep(max(args.poll_seconds, 10.0))
        except Exception as exc:
            log(f"WATCH ERROR: {exc}")
            time.sleep(max(args.poll_seconds, 10.0))


if __name__ == "__main__":
    raise SystemExit(main())
