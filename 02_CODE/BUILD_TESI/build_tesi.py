#!/usr/bin/env python3
r"""Permanent Overleaf-only build pipeline for Tesi_FRLM_FVG.ipynb.

V5: APPEND-ONLY PUBLISH
=======================
The authoritative notebook is the only editable source.

Local responsibilities:
- dedicated Python virtual environment;
- dedicated Jupyter kernel;
- Pandoc;
- authoring lint;
- notebook execution;
- nbconvert Markdown/LaTeX generation;
- Overleaf-ready ZIP creation.

Canonical PDF compilation:
- Overleaf with XeLaTeX.

Publishing policy:
- NO delete/rename/rotation of Output_Tesi on OneDrive;
- every successful build is copied into a NEW timestamped directory;
- failed builds publish nothing;
- prior successful builds remain untouched.

This avoids Windows/OneDrive locking failures such as Access Denied on
directory rename/delete.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

KERNEL_NAME = "tesi-build"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, *, cwd=None, timeout=900) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    p = subprocess.run(
        cmd,
        cwd=cwd,
        timeout=timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if p.returncode != 0:
        tail = "\n".join(p.stdout.splitlines()[-160:])
        raise RuntimeError(
            f"Command failed ({p.returncode}): {' '.join(map(str, cmd))}\n\n{tail}"
        )
    return p


def preflight_environment() -> dict[str, str]:
    expected_python = (
        Path.home() / ".venvs" / "tesi-build" / "Scripts" / "python.exe"
        if os.name == "nt"
        else Path.home() / ".venvs" / "tesi-build" / "bin" / "python"
    )
    actual_python = Path(sys.executable).resolve()

    if not expected_python.exists():
        raise RuntimeError(f"Dedicated Tesi venv not found: {expected_python}")

    if actual_python != expected_python.resolve():
        raise RuntimeError(
            "Wrong Python runtime.\n"
            f"Expected: {expected_python.resolve()}\n"
            f"Actual:   {actual_python}"
        )

    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        raise RuntimeError("The build is not running inside a virtual environment.")

    for module in ("nbconvert", "ipykernel", "jupyter_client"):
        if importlib.util.find_spec(module) is None:
            raise RuntimeError(
                f"Required Python module not installed in tesi-build venv: {module}"
            )

    pandoc = shutil.which("pandoc")
    if pandoc is None:
        raise RuntimeError("Pandoc not found in PATH.")

    from jupyter_client.kernelspec import KernelSpecManager
    try:
        ks = KernelSpecManager().get_kernel_spec(KERNEL_NAME)
    except Exception as exc:
        raise RuntimeError(
            f"Required Jupyter kernel '{KERNEL_NAME}' not found."
        ) from exc

    if not ks.argv:
        raise RuntimeError(f"Kernel '{KERNEL_NAME}' has an empty argv.")

    raw = ks.argv[0]
    kernel_python = Path(raw).expanduser()
    if not kernel_python.is_absolute():
        found = shutil.which(raw)
        if found is None:
            raise RuntimeError(
                f"Cannot resolve Python used by kernel '{KERNEL_NAME}': {raw}"
            )
        kernel_python = Path(found)

    kernel_python = kernel_python.resolve()

    if kernel_python != actual_python:
        raise RuntimeError(
            f"Kernel '{KERNEL_NAME}' does not point to the dedicated Tesi venv.\n"
            f"Expected: {actual_python}\n"
            f"Kernel:   {kernel_python}"
        )

    return {
        "python": str(actual_python),
        "kernel": KERNEL_NAME,
        "kernel_python": str(kernel_python),
        "pandoc": pandoc,
    }


def strip_code(markdown: str) -> str:
    parts = re.split(r"(```.*?```)", markdown, flags=re.S)
    plain = []
    for i in range(0, len(parts), 2):
        plain.append(re.sub(r"`[^`\n]*`", "", parts[i]))
    return "".join(plain)


def lint_notebook(nb_path: Path) -> None:
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    if not nb.get("cells"):
        raise RuntimeError("Notebook has no cells.")

    md = "\n".join(
        "".join(c.get("source", []))
        for c in nb["cells"]
        if c.get("cell_type") == "markdown"
    )
    plain = strip_code(md)

    errors = []

    if r"\(" in plain or r"\)" in plain:
        errors.append(
            r"Forbidden MathJax inline delimiters \(...\) found outside code. Use $...$."
        )

    for n, line in enumerate(plain.splitlines(), 1):
        if line.strip() in {r"\[", r"\]"}:
            errors.append(
                f"Forbidden standalone MathJax display delimiter at Markdown line {n}. "
                "Use $$ instead."
            )

    if md.count("```") % 2:
        errors.append("Unbalanced fenced code blocks (``` count is odd).")

    p2 = re.sub(r"\\\$", "", plain)
    if p2.count("$$") % 2:
        errors.append("Unbalanced $$ display-math delimiters.")

    if errors:
        raise RuntimeError("AUTHORING LINT FAILED:\n- " + "\n- ".join(errors))


def make_overleaf_bundle(stage: Path, stem: str) -> Path:
    instructions = stage / "README_OVERLEAF.txt"
    instructions.write_text(
        "\n".join([
            "TESI FRLM FVG - OVERLEAF PACKAGE",
            "=================================",
            "",
            f"Main document: {stem}.tex",
            "Canonical compiler: XeLaTeX",
            "",
            "OVERLEAF:",
            "1. Create/open the thesis project.",
            "2. Upload the contents of this ZIP.",
            f"3. Set {stem}.tex as Main document if needed.",
            "4. Menu / Settings -> Compiler -> XeLaTeX.",
            "5. Recompile.",
            "",
            "The generated .tex was not manually post-processed.",
        ]) + "\n",
        encoding="utf-8",
    )

    zpath = stage / f"{stem}_OVERLEAF_READY.zip"
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            if not p.is_file() or p == zpath:
                continue
            if p.name in {f"{stem}.ipynb", f"{stem}.md", "BUILD_REPORT.txt"}:
                continue
            z.write(p, p.relative_to(stage).as_posix())
    return zpath


def make_unique_run_dir(out_root: Path) -> Path:
    out_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = out_root / f"build_{stamp}"
    counter = 1
    while candidate.exists():
        candidate = out_root / f"build_{stamp}_{counter:02d}"
        counter += 1
    return candidate


def publish_append_only(stage: Path, out_root: Path, stem: str) -> Path:
    """Create a brand-new output directory. Never alter prior successful runs."""
    target = make_unique_run_dir(out_root)
    target.mkdir(parents=False, exist_ok=False)

    try:
        required = [
            f"{stem}.md",
            f"{stem}.tex",
            f"{stem}_OVERLEAF_READY.zip",
            "BUILD_REPORT.txt",
        ]
        for name in required:
            src = stage / name
            if not src.exists():
                raise RuntimeError(f"Validated artifact missing before publish: {src}")
            shutil.copy2(src, target / name)

        for child in stage.iterdir():
            if child.is_dir():
                shutil.copytree(child, target / child.name)

        # Verify copied artifacts before declaring publish successful.
        for name in required:
            dst = target / name
            if not dst.exists() or dst.stat().st_size == 0:
                raise RuntimeError(f"Published artifact invalid: {dst}")

    except Exception:
        # Best-effort cleanup of only the newly-created run; never touch older runs.
        try:
            shutil.rmtree(target)
        except Exception:
            pass
        raise

    return target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("notebook", nargs="?", default="Tesi_FRLM_FVG.ipynb")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    env = preflight_environment()

    nb_path = Path(args.notebook).resolve()
    if not nb_path.exists():
        raise RuntimeError(f"Notebook not found: {nb_path}")

    lint_notebook(nb_path)

    stem = nb_path.stem
    out_root = (
        Path(args.out_dir).resolve()
        if args.out_dir
        else nb_path.parent / f"{stem}_builds"
    )

    nbconvert = [sys.executable, "-m", "nbconvert"]

    # Execute the authoritative notebook in place.
    run(
        nbconvert + [
            "--to", "notebook",
            "--execute",
            "--inplace",
            f"--ExecutePreprocessor.kernel_name={KERNEL_NAME}",
            str(nb_path),
        ],
        cwd=nb_path.parent,
        timeout=1200,
    )

    lint_notebook(nb_path)

    work_root = Path.home() / ".tesi-build-work"
    work_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="run_", dir=work_root) as tmp:
        stage = Path(tmp)
        staged_nb = stage / f"{stem}.ipynb"
        shutil.copy2(nb_path, staged_nb)

        run(
            nbconvert + [
                "--to", "markdown",
                "--output-dir", str(stage),
                "--output", stem,
                str(staged_nb),
            ],
            cwd=stage,
            timeout=900,
        )

        run(
            nbconvert + [
                "--to", "latex",
                "--output-dir", str(stage),
                "--output", stem,
                str(staged_nb),
            ],
            cwd=stage,
            timeout=900,
        )

        md = stage / f"{stem}.md"
        tex = stage / f"{stem}.tex"

        if not md.exists() or md.stat().st_size == 0:
            raise RuntimeError("Generated Markdown output is missing/empty.")
        if not tex.exists() or tex.stat().st_size == 0:
            raise RuntimeError("Generated LaTeX output is missing/empty.")

        zpath = make_overleaf_bundle(stage, stem)

        report = stage / "BUILD_REPORT.txt"
        report.write_text(
            "\n".join([
                "TESI BUILD REPORT",
                "=================",
                "STATUS = PASS",
                "PIPELINE_VERSION = v5_OVERLEAF_APPEND_ONLY",
                "AUTHORITATIVE_SOURCE = " + str(nb_path),
                "ENVIRONMENT_PREFLIGHT = PASS",
                "PYTHON_RUNTIME = " + env["python"],
                "JUPYTER_KERNEL = " + env["kernel"],
                "KERNEL_PYTHON = " + env["kernel_python"],
                "PANDOC = " + env["pandoc"],
                "AUTHORING_LINT = PASS",
                "NOTEBOOK_EXECUTION = PASS",
                "NBCONVERT_MARKDOWN = PASS",
                "NBCONVERT_LATEX = PASS",
                "GENERATED_MARKDOWN_NONEMPTY = PASS",
                "GENERATED_LATEX_NONEMPTY = PASS",
                "OVERLEAF_BUNDLE_READY = PASS",
                "LOCAL_LATEX_COMPILATION = NOT_REQUIRED",
                "CANONICAL_PDF_COMPILER = OVERLEAF_XELATEX",
                "PUBLISH_POLICY = APPEND_ONLY_NEW_DIRECTORY",
                "OVERLEAF_BUNDLE = " + zpath.name,
                "NOTEBOOK_SHA256 = " + sha256(nb_path),
                "MARKDOWN_SHA256 = " + sha256(md),
                "LATEX_SHA256 = " + sha256(tex),
                "",
                "Generated .md/.tex were not post-processed or manually edited.",
                "A local PASS certifies generation readiness, not PDF compilation.",
                "Prior successful output directories are never modified by this build.",
            ]) + "\n",
            encoding="utf-8",
        )

        published = publish_append_only(stage, out_root, stem)

    print((published / "BUILD_REPORT.txt").read_text(encoding="utf-8"))
    print("PUBLISHED_RUN = " + str(published))
    print("OVERLEAF_ZIP = " + str(published / f"{stem}_OVERLEAF_READY.zip"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"BUILD FAILED: {exc}", file=sys.stderr)
        raise SystemExit(2)
