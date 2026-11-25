"""Tests for semantic chunking, overlap, metadata retention, and table header preservation."""
from __future__ import annotations

from django.test import SimpleTestCase

from rag.services import chunking_service
from rag.services.text_extraction_service import Block


class ChunkingTestCase(SimpleTestCase):
    def test_large_table_repeats_headers_in_each_chunk_and_never_splits_rows(self):
        rows = [f"Product: Item-{i} | Price: {100 + i} INR | Unit: piece" for i in range(60)]
        blk = Block(
            kind="table",
            sheet="PriceSheet",
            heading="PriceSheet",
            header_line="Columns: Product | Price | Unit",
            rows=rows,
        )
        chunks = chunking_service.chunk_blocks([blk], size=120, overlap=20, max_tokens=150)
        self.assertGreater(len(chunks), 1)
        for ch in chunks:
            self.assertEqual(ch.sheet, "PriceSheet")
            self.assertIn("Columns: Product | Price | Unit", ch.text)
            # Every Item-N row in the chunk still has its Price on the same line
            for line in ch.text.splitlines():
                if line.startswith("Product: Item-"):
                    self.assertIn("| Price:", line)
                    self.assertIn("INR | Unit: piece", line)

    def test_prose_chunking_preserves_page_and_section_metadata(self):
        blocks = [
            Block(kind="heading", text="1. Shipping Terms", page=2, heading="1. Shipping Terms"),
            Block(
                kind="paragraph",
                text="Orders above 5000 INR qualify for free same-day delivery in Coimbatore.",
                page=2,
                heading="1. Shipping Terms",
            ),
        ]
        chunks = chunking_service.chunk_blocks(blocks, size=500, overlap=80)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].page, 2)
        self.assertEqual(chunks[0].heading, "1. Shipping Terms")
        emb_input = chunking_service.embedding_input_for_chunk(
            "policy.pdf",
            chunks[0].text,
            sheet=chunks[0].sheet,
            heading=chunks[0].heading,
            page=chunks[0].page,
        )
        self.assertIn("Document: policy.pdf", emb_input)
        self.assertIn("Section: 1. Shipping Terms", emb_input)
        self.assertIn("Page: 2", emb_input)
