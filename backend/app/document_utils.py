from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import pymupdf

MAX_PDF_PAGES = 5
PDF_DPI = 140
JPEG_QUALITY = 84

@dataclass
class PreparedDocument:
    images: list[bytes]
    media_types: list[str]
    source_kind: Literal["image", "pdf"]
    total_pages: int
    processed_pages: int
    warning: str | None = None

def prepare_document(file_bytes: bytes, content_type: str | None, filename: str | None) -> PreparedDocument:
    content_type=(content_type or '').lower()
    filename=(filename or '').lower()
    is_pdf=content_type=='application/pdf' or filename.endswith('.pdf')
    if not is_pdf:
        return PreparedDocument([file_bytes],[content_type or 'image/jpeg'],'image',1,1)
    try:
        doc=pymupdf.open(stream=file_bytes,filetype='pdf')
    except Exception as exc:
        raise ValueError(f'Could not open PDF: {exc}') from exc
    try:
        count=len(doc)
        if count == 0:
            raise ValueError('The PDF contains no pages.')
        n=min(count, MAX_PDF_PAGES)
        images=[]
        for i in range(n):
            pix=doc[i].get_pixmap(dpi=PDF_DPI, colorspace=pymupdf.csRGB, alpha=False, annots=True)
            images.append(pix.tobytes('jpeg', jpg_quality=JPEG_QUALITY))
        warning=None
        if count > MAX_PDF_PAGES:
            warning=f'This PDF has {count} pages. To keep local vision inference responsive, only the first {MAX_PDF_PAGES} pages were analyzed.'
        return PreparedDocument(images,['image/jpeg']*len(images),'pdf',count,n,warning)
    finally:
        doc.close()
