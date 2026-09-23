# Supplied comparison fixtures

The local demo uses the two anonymized internal audit regulations supplied with this task:

- `before.pdf`: `Положение_о_внутреннем_аудите_редакция_8_обезличено.docx.pdf`, edition 8, approved 25 June 2021, 25 PDF pages.
- `after.pdf`: `Положение_о_внутреннем_аудите_редакция_9_обезличено.docx.pdf`, edition 9, approved 23 December 2022, 25 PDF pages.

Assigning edition 8 to BEFORE and edition 9 to AFTER is an explicit implementation assumption based on their version labels. It is not an organizer-provided answer key. `manifest.json` preserves original filenames and SHA-256 hashes. These are real source documents; the application derives its results from their extracted contents on each run. No expected findings are inserted into the analysis.

The separate three-page HackAlem task brief was reviewed as product context. It is not part of either organizational document set and is not passed into the comparison.

## Re-import

If fixture PDFs are absent from your copy, place the original supplied files in your Downloads directory, then run from the repository root:

```bash
python scripts/import_fixtures.py
```

For a different source directory:

```bash
python scripts/import_fixtures.py --source-dir /path/to/provided/files
```

The importer checks that both source files exist and have a PDF signature before copying them. Alternatively, use the application's two upload areas with your own DOCX, PDF, or XLSX files.

## Source review notes

These notes describe directly inspectable document content; they are not a complete analysis or a fixed regression answer:

- Both PDFs have extractable Russian text. Extracted text contains unusual line wrapping and repeated spaces; the ingestion layer normalizes whitespace while retaining page and clause references.
- Section 3.4, PDF page 6 in both editions, lists the departments of the internal audit block. Edition 8 lists continuous internal control monitoring and audit quality/methodology departments. Edition 9 lists those departments plus IT audit/data analysis and operational audit departments.
- Edition 9, page 8, section 5.3.2 explicitly distinguishes IT/data-related audit duties and operational process audit duties. A list of role titles alone is weaker evidence of a department's function than this explicit assignment.
- General internal audit functions appear in sections 2.4.1–2.4.21 on pages 4–5. Department/leadership duties appear in section 5. Several clauses have moved or been renumbered, so a changed clause number alone does not prove function loss.
- Edition 9, page 7, section 4.4 adds provisions for participation in subsidiary governing bodies and associated independence/conflict disclosure safeguards. Mentioning a potential conflict and safeguards does not establish that an actual conflict occurred.
- Page 25 contains a contents list whose displayed section pagination does not consistently match the PDF pages. Citations use the physical PDF page number. Pages 22–24 include glossary definitions; mentions there alone should not be treated as a complete organizational inventory.
- Page 25 refers to an attached Code of Ethics DOCX; the referenced document is not present as readable source text in these PDFs and is outside the comparison scope.
- These documents describe only the supplied internal audit scope. They cannot establish the full company's organization or prove that an apparently absent function ceased everywhere.

