# helpers/extract_docx.py
from docx import Document

def extract_docx_text(path: str) -> str:
    try:
        doc = Document(path)
        return '\n'.join(p.text for p in doc.paragraphs)
    except Exception:
        return ''
