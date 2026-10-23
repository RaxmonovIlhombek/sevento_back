"""Hisobot formatlari (adapter): yangi format — klass + register_renderer (masalan CSV)."""

from .base import RenderedReport, Renderer, get_renderer, register_renderer, renderer_formats
from .pdf import PdfRenderer
from .xlsx import XlsxRenderer

register_renderer(PdfRenderer)
register_renderer(XlsxRenderer)

__all__ = [
    "PdfRenderer",
    "RenderedReport",
    "Renderer",
    "XlsxRenderer",
    "get_renderer",
    "register_renderer",
    "renderer_formats",
]
