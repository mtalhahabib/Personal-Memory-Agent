# helpers/extract_pdf.py
from pdfminer.high_level import extract_text

def extract_pdf_text(path: str) -> str:
    try:
        return extract_text(path)
    except Exception:
        return ''
