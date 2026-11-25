"""Tests for PDF, DOCX, XLSX, CSV, TXT, and Markdown parsing."""
from __future__ import annotations

import io

import docx
import openpyxl
from django.test import SimpleTestCase
from pypdf import PdfWriter

from rag.exceptions import OCRRequiredError
from rag.services import document_parser_service


class DocumentParsingTestCase(SimpleTestCase):
    def test_csv_preserves_headers_and_prices_on_every_row(self):
        raw = b"Product,Price,Unit,Currency\nSteel Bolt M8,12.50,piece,INR\nCopper Wire 2mm,240,metre,INR\n"
        blocks, count = document_parser_service.parse_document("csv", raw)
        self.assertEqual(count, 1)
        self.assertEqual(len(blocks), 1)
        text = blocks[0].full_text()
        self.assertIn("Product: Steel Bolt M8 | Price: 12.50 | Unit: piece | Currency: INR", text)
        self.assertIn("Product: Copper Wire 2mm | Price: 240 | Unit: metre | Currency: INR", text)

    def test_xlsx_preserves_sheet_name_and_row_relationships(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Industrial Motors"
        ws.append(["Model", "Power", "Price INR"])
        ws.append(["MT-100", "2 HP", 14500])
        ws.append(["MT-200", "5 HP", 28900])
        buf = io.BytesIO()
        wb.save(buf)

        blocks, sheets = document_parser_service.parse_document("xlsx", buf.getvalue())
        self.assertEqual(sheets, 1)
        self.assertEqual(blocks[0].sheet, "Industrial Motors")
        full = blocks[0].full_text()
        self.assertIn("Model: MT-100 | Power: 2 HP | Price INR: 14500", full)
        self.assertIn("Model: MT-200 | Power: 5 HP | Price INR: 28900", full)

    def test_docx_extracts_headings_paragraphs_and_tables(self):
        doc = docx.Document()
        doc.add_heading("Warranty Policy", level=1)
        doc.add_paragraph("All industrial pumps include a 24-month replacement warranty.")
        tbl = doc.add_table(rows=2, cols=2)
        tbl.cell(0, 0).text = "Plan"
        tbl.cell(0, 1).text = "Annual Fee"
        tbl.cell(1, 0).text = "Gold AMC"
        tbl.cell(1, 1).text = "4500 INR"
        buf = io.BytesIO()
        doc.save(buf)

        blocks, _ = document_parser_service.parse_document("docx", buf.getvalue())
        joined = "\n".join(b.full_text() for b in blocks)
        self.assertIn("Warranty Policy", joined)
        self.assertIn("24-month replacement warranty", joined)
        self.assertIn("Plan: Gold AMC | Annual Fee: 4500 INR", joined)

    def test_blank_scanned_pdf_reports_ocr_required(self):
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        buf = io.BytesIO()
        writer.write(buf)

        with self.assertRaises(OCRRequiredError):
            document_parser_service.parse_document("pdf", buf.getvalue())

    def test_markdown_and_tamil_unicode_normalization(self):
        md = "# எங்கள் சேவைகள்\n\nநாங்கள் கோயம்புத்தூரில் 24 மணி நேரமும் சேவை வழங்குகிறோம்.\n".encode("utf-8")
        blocks, _ = document_parser_service.parse_document("md", md)
        self.assertEqual(blocks[0].kind, "heading")
        self.assertEqual(blocks[1].heading, "எங்கள் சேவைகள்")
        self.assertIn("கோயம்புத்தூரில்", blocks[1].text)
