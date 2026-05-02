#!/usr/bin/env python3
"""
Converts SVG files to PDF format using the Cairo library.
"""

import os
import sys


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: svg_to_pdf.py <input_svg_file> <output_pdf_file>")
        sys.exit(1)

    input_svg = sys.argv[1]
    output_pdf = sys.argv[2]

    if not os.path.isfile(input_svg):
        print(f"Error: File '{input_svg}' does not exist.")
        sys.exit(1)

    try:
        with open(input_svg, "r", encoding="utf-8") as f:
            svg = f.read()
    except Exception as e:
        print(f"Error reading SVG file: {e}")
        sys.exit(1)

    try:
        import cairosvg
        print(f"\nConverting to PDF: '{output_pdf}' ...")
        cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=output_pdf)
        print(f"PDF written to '{output_pdf}'\n")
    except ImportError:
        print("cairosvg not installed — skipping PDF conversion. Run: pip install cairosvg")

