"""One-off script to generate a synthetic fastener spec-sheet PDF for
local end-to-end testing of stages 1+2. Not part of the pipeline."""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUT_PATH = Path(__file__).resolve().parent / "sample_fastener_spec.pdf"

LINES = [
    ("Product Spec Sheet", 16, True),
    ("", 10, False),
    ("Product Name: Hex Head Cap Screw, 1/4-20 x 1 in, Stainless Steel 18-8", 11, False),
    ("Part Number: HHC-0250-100-SS", 11, False),
    ("", 10, False),
    ("Material: Stainless Steel 18-8 (A2)", 11, False),
    ("Thread Diameter: 6.35 mm (1/4 in nominal)", 11, False),
    ("Length: 25.4 mm (1 in)", 11, False),
    ("Thread Pitch: 1.27 mm (20 TPI)", 11, False),
    ("Head Type: Hex", 11, False),
    ("Drive Type: External Hex Wrench", 11, False),
    ("Finish: Passivated, plain", 11, False),
    ("Grade: 18-8 Stainless (not graded like alloy steel)", 11, False),
    ("Standard: ANSI B18.2.1", 11, False),
    ("Package Quantity: 100 per box", 11, False),
    ("", 10, False),
    ("Notes: Suitable for outdoor and corrosive environments. Not for", 10, False),
    ("structural load-bearing applications above 500 lbs shear.", 10, False),
]


def main() -> None:
    c = canvas.Canvas(str(OUT_PATH), pagesize=letter)
    width, height = letter
    y = height - 1 * inch

    for text, size, bold in LINES:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(1 * inch, y, text)
        y -= size + 8

    c.save()
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
