"""Copy the supplied anonymized audit regulations into the optional local demo."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "before": "Положение_о_внутреннем_аудите_редакция_8_обезличено.docx.pdf",
    "after": "Положение_о_внутреннем_аудите_редакция_9_обезличено.docx.pdf",
}


def import_fixtures(source_dir: Path, destination: Path) -> dict[str, object]:
    """Validate both sources before copying and preserve provenance in a manifest."""
    sources = {side: source_dir / name for side, name in SOURCES.items()}
    for path in sources.values():
        if not path.is_file():
            raise FileNotFoundError(f"Missing supplied fixture: {path}")
        if not path.read_bytes().startswith(b"%PDF-"):
            raise ValueError(f"Expected a PDF file: {path.name}")
    destination.mkdir(parents=True, exist_ok=True)
    documents = []
    for side, source in sources.items():
        target = destination / f"{side}.pdf"
        shutil.copyfile(source, target)
        documents.append({
            "side": side,
            "filename": target.name,
            "original_filename": source.name,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "bytes": target.stat().st_size,
            "edition": 8 if side == "before" else 9,
        })
    manifest: dict[str, object] = {
        "assignment_basis": "Edition 8 is BEFORE and edition 9 is AFTER, inferred from version numbering; not an organizer-provided answer key.",
        "documents": documents,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--destination", type=Path, default=ROOT / "fixtures")
    args = parser.parse_args()
    try:
        manifest = import_fixtures(args.source_dir, args.destination)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Fixture import failed: {exc}\n")
    print(f"Imported {len(manifest['documents'])} supplied PDFs to {args.destination.resolve()}")
    print("Edition 8 = BEFORE; edition 9 = AFTER. See fixtures/manifest.json for provenance.")


if __name__ == "__main__":
    main()
