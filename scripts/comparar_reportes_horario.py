"""
Compara la salida de 2 reportes (PDF) generados con flag on vs off.

Uso:
    python scripts/comparar_reportes_horario.py \\
        --con-flag-on /tmp/reporte_on.pdf \\
        --con-flag-off /tmp/reporte_off.pdf

Compara:
  - Hash MD5 de los bytes.
  - Si `pypdf` está disponible, extrae texto y muestra diff.

Esto verifica empíricamente que el flag `horario_por_grupo` no altera la
salida de los reportes para personas con solo horario legacy
(compatibilidad hacia atrás, V4 del ADR-0003).
"""
import argparse
import hashlib


def md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def text(path):
    try:
        from pypdf import PdfReader
        return "\n".join(
            p.extract_text() or "" for p in PdfReader(path).pages
        )
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
            return "\n".join(
                p.extract_text() or "" for p in PdfReader(path).pages
            )
        except Exception:
            return None


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Comparador A/B de reportes PDF (ADR-0003, plan Tarea 7.2)."
        ),
    )
    parser.add_argument("--con-flag-on", required=True)
    parser.add_argument("--con-flag-off", required=True)
    args = parser.parse_args()

    h_on = md5(args.con_flag_on)
    h_off = md5(args.con_flag_off)
    t_on = text(args.con_flag_on)
    t_off = text(args.con_flag_off)

    print(f"MD5 on:  {h_on}")
    print(f"MD5 off: {h_off}")
    if h_on == h_off:
        print("OK: bytes idénticos.")
    else:
        print("DIFIEREN: los PDFs son distintos (esperable si flag=on aplica "
              "default_grupo a alguna persona).")

    if t_on is not None and t_off is not None:
        if t_on == t_off:
            print("OK: texto extraído idéntico.")
        else:
            print("DIFIEREN en texto. Diff:")
            import difflib
            for line in difflib.unified_diff(
                t_off.splitlines(), t_on.splitlines(),
                fromfile="off", tofile="on", lineterm="",
            ):
                print(line)
    else:
        print(
            "(No se pudo extraer texto — instala `pypdf` o `PyPDF2` para "
            "comparar el contenido.)"
        )


if __name__ == "__main__":
    main()
