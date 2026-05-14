#!/usr/bin/env python3
"""Exporta un archivo Markdown a PDF usando pandoc + lualatex.

Uso:
    python3 export_pdf.py                       # lista los .md y pregunta cuál exportar
    python3 export_pdf.py otro_archivo.md       # exporta otro archivo
    python3 export_pdf.py archivo.md salida.pdf # especifica nombre de salida
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APPENDIX_MD = """

```{=latex}
\\clearpage
```

## Aviso de uso académico

Este documento es una **transcripción digital con fines educativos** del libro:

> Giacosa, Dante. *Motores Endotérmicos*. 3ra edición.
> Editorial Hoepli / Editorial Omega (edición en español), 1979.

El contenido original —texto, fórmulas y figuras— pertenece a su autor y a la editorial correspondiente. Esta versión fue tipeada y formateada por docentes de la **Cátedra de Máquinas Térmicas, UTN — Facultad Regional Haedo**, con el único objetivo de facilitar el estudio del material a los cursantes de la materia.

- **No se persigue fin comercial alguno.**
- **No se reclama autoría** sobre el contenido original.
- **Distribución restringida** al ámbito académico interno de la cátedra.
- Cualquier titular de derechos puede solicitar la baja o modificación de este material escribiendo a la cátedra.

Edición digital: Cátedra de Máquinas Térmicas, UTN-FRH.
"""

HEADER_TEX = r"""
\renewcommand{\figurename}{Figura}
\renewcommand{\tablename}{Tabla}
\usepackage{graphicx}
\usepackage{caption}
\setkeys{Gin}{width=0.7\linewidth, keepaspectratio}
\let\oldincludegraphics\includegraphics
\renewcommand{\includegraphics}[2][]{\begin{center}\oldincludegraphics[#1]{#2}\end{center}}
% Figura numerada con epígrafe vacío (sin ":" final).
% Acepta opciones de \includegraphics como argumento opcional.
\newcommand{\figunnamed}[2][]{%
  \begin{figure}[H]\centering%
    \oldincludegraphics[#1]{#2}%
    \captionsetup{labelsep=none}\caption{}%
  \end{figure}%
}
\usepackage{float}
"""

PANDOC_ARGS = [
    "--pdf-engine=lualatex",
    "-V",
    "mainfont=DejaVu Sans",
    "-V",
    "geometry:margin=2cm",
]


def _md_attrs_to_latex(attrs: str) -> str:
    """Convierte atributos pandoc-md (width=50%, width=10cm, etc.) a opciones de \\includegraphics."""
    if not attrs:
        return ""
    parts = []
    for token in attrs.split():
        if "=" not in token:
            continue
        key, val = token.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key == "width" and val.endswith("%"):
            try:
                ratio = float(val.rstrip("%")) / 100
                parts.append(f"width={ratio}\\linewidth")
            except ValueError:
                parts.append(f"{key}={val}")
        else:
            parts.append(f"{key}={val}")
    return ",".join(parts)


def preprocess(content: str) -> str:
    """Convierte imágenes con alt vacío en figuras LaTeX numeradas sin epígrafe.

    Soporta tanto `![](path)` como `![](path){width=50%}` u otros atributos.
    """
    pattern = re.compile(r"^!\[\]\(([^)]+)\)(?:\{([^}]*)\})?\s*$", re.MULTILINE)

    def repl(m: re.Match) -> str:
        path = m.group(1)
        attrs = _md_attrs_to_latex(m.group(2) or "")
        opt = f"[{attrs}]" if attrs else ""
        return f"```{{=latex}}\n\\figunnamed{opt}{{{path}}}\n```"

    return pattern.sub(repl, content)


def export(md_path: Path, pdf_path: Path) -> int:
    if not md_path.exists():
        print(f"Error: no existe el archivo {md_path}", file=sys.stderr)
        return 1
    if shutil.which("pandoc") is None:
        print("Error: pandoc no está instalado", file=sys.stderr)
        return 1

    with tempfile.NamedTemporaryFile("w", suffix=".tex", delete=False) as f:
        f.write(HEADER_TEX)
        header_path = Path(f.name)

    preprocessed = preprocess(md_path.read_text(encoding="utf-8")) + APPENDIX_MD
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, dir=md_path.parent, encoding="utf-8"
    ) as f:
        f.write(preprocessed)
        tmp_md = Path(f.name)

    cmd = [
        "pandoc",
        str(tmp_md),
        "-o",
        str(pdf_path),
        *PANDOC_ARGS,
        "-H",
        str(header_path),
    ]

    print(f"Exportando: {md_path.name} -> {pdf_path.name}")
    try:
        result = subprocess.run(cmd, cwd=md_path.parent, capture_output=True, text=True)
    finally:
        header_path.unlink(missing_ok=True)
        tmp_md.unlink(missing_ok=True)

    if result.returncode != 0:
        print("Pandoc falló:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return result.returncode

    size_kb = pdf_path.stat().st_size / 1024
    print(f"OK -> {pdf_path} ({size_kb:.1f} KB)")
    return 0


def pick_md_interactively(script_dir: Path) -> list[Path]:
    search_dir = script_dir / "2_Transcriptos"
    if not search_dir.is_dir():
        print(f"No existe la carpeta {search_dir}", file=sys.stderr)
        return []

    md_files = sorted(
        (p for p in search_dir.rglob("*.md") if p.is_file()),
        key=lambda p: p.name.lower(),
    )
    if not md_files:
        print(f"No se encontraron archivos .md en {search_dir}", file=sys.stderr)
        return []

    print("Archivos Markdown disponibles:")
    width = len(str(len(md_files)))
    for i, p in enumerate(md_files, start=1):
        print(f"  [{i:>{width}}] {p.name}")
    print(f"  [{'a':>{width}}] exportar todos")

    while True:
        try:
            choice = input(
                f"Elegí un número (1-{len(md_files)}, a para todos, q para salir): "
            ).strip()
        except EOFError:
            return []
        if choice.lower() in {"q", "quit", "salir"}:
            return []
        if choice.lower() in {"a", "all", "todos"}:
            return md_files
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(md_files):
                return [md_files[idx - 1]]
        print("Entrada inválida, probá de nuevo.")


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / "3_pdfs"
    args = sys.argv[1:]

    if args:
        md_path = Path(args[0])
        if not md_path.is_absolute():
            md_path = script_dir / md_path
        md_paths = [md_path]
    else:
        md_paths = pick_md_interactively(script_dir)
        if not md_paths:
            return 1

    if len(args) >= 2:
        pdf_path = Path(args[1])
        if not pdf_path.is_absolute():
            pdf_path = script_dir / pdf_path
        return export(md_paths[0], pdf_path)

    output_dir.mkdir(exist_ok=True)
    exit_code = 0
    for md_path in md_paths:
        pdf_path = output_dir / (md_path.stem + ".pdf")
        rc = export(md_path, pdf_path)
        if rc != 0:
            exit_code = rc
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
