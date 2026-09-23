# Input fidelity — trust the render, not always the text layer

Extracted text is a convenience, not the truth. Before any finding depends on the
exact characters or spacing of a source, know how reliable the extraction is.

## When the text layer is suspect

- **Legacy / non-Unicode fonts** for complex scripts (Khmer, Lao, Myanmar, Thai in
  old encodings, Indic scripts, Arabic): the PDF stores glyphs in *visual* order and
  with ligature substitutions, so the extracted code points can be reordered,
  duplicated, or mangled relative to what a reader sees. A `ុី` vs `៊ី` difference,
  or an inserted space, may be an extraction artifact, not the real content.
- **Scanned pages / images**: no reliable text layer at all — OCR, and treat OCR
  output as a draft to verify against the image.
- **Outlined / vectorized text** (common on artwork): no text layer; the words exist
  only as shapes. Read them from the render.
- **Right-to-left and bidi** content: extraction order often differs from reading
  order.

## What to do

1. Render the page/panel at high resolution (e.g. a 6–16× zoom crop of the region
   you care about) and read the text from the image.
2. Use the extracted text layer only for a first-pass diff and for mechanical checks
   that are robust to reordering (does a number appear at all, is a placeholder
   present). Do not use it as the authority for spacing, character order, or
   individual diacritics.
3. **Never emit a whitespace, character-order, or single-diacritic finding from a
   text layer alone.** Confirm it against the render first. Legacy-Khmer text layers
   in particular routinely report spacing the render does not show — a "missing
   space" that exists only in the extraction. Filed from the text layer alone, that
   is a wrong finding sent to a client.
4. Note in the report which basis you used ("verified against rendered artwork at
   high resolution"), so the reviewer knows the check was visual, not just textual.

## Tools

`pdfplumber` / `PyMuPDF (fitz)` for text and for rendering page pixmaps at high DPI;
crop to the region and zoom before reading. For scans, an OCR pass first. These are
plain Python — write a short script; don't hand-transcribe from a low-res view.
