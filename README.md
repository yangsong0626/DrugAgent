# Patent-to-SAR Agent

First MVP for uploading compound CSV/SDF data or patent PDFs with text-encoded SMILES, calculating RDKit descriptors, clustering by Morgan fingerprint similarity, reviewing structures in a React table, generating analog design proposals, exporting selected compounds, and building briefing reports.

Patent PDF extraction imports valid SMILES found in selectable PDF text, such as examples tables or `SMILES:` fields. When patents list IUPAC or chemical names instead, the backend can resolve those names to SMILES through PubChem PUG-REST before import. For image-based PDFs, the backend falls back to OCR when Tesseract is installed and can recognize text-encoded SMILES or IUPAC/name text from rendered page images. Pure chemical drawings still need structure-image extraction before import.

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API runs at `http://localhost:8000`.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

The app runs at `http://localhost:5173`.

## CSV Format

CSV uploads need a SMILES column. The parser recognizes common names such as `smiles`, `SMILES`, `canonical_smiles`, and `structure`. Optional compound name columns include `name`, `compound_id`, and `ID`.

Try `sample_data/example_compounds.csv` for a quick end-to-end check.

## Patent PDF Extraction

Upload a patent PDF through the same intake endpoint:

```bash
curl -X POST http://localhost:8000/api/uploads/csv-sdf \
  -F "file=@patent.pdf"
```

The parser extracts selectable text page-by-page, prioritizes labeled `SMILES:` entries, validates candidates with RDKit, de-duplicates canonical structures, and stores PDF page/snippet metadata on each imported compound.

If no selectable SMILES are found, the backend looks for labeled IUPAC or chemical names such as `IUPAC name:`, `Chemical name:`, `Compound name:`, or `Example 12: 2-acetoxybenzoic acid`, then resolves those names to SMILES using PubChem PUG-REST.

If no selectable text candidates are found, the backend attempts OCR on rendered PDF page images using Tesseract plus `pytesseract`/PyMuPDF. OCR can recover text-encoded SMILES or IUPAC/name text embedded in image scans, but it does not convert structure drawings into SMILES.

## SAR Summary

After uploading a CSV/SDF with a numeric potency column, generate structured SAR JSON:

```bash
curl -X POST http://localhost:8000/api/sar/summary \
  -H "Content-Type: application/json" \
  -d '{
    "upload_id": "UPLOAD_ID",
    "potency_column": "ic50_nm",
    "potency_direction": "lower_is_better",
    "admet_columns": ["clint_ul_min_mg"],
    "min_fold_change": 3
  }'
```

The response includes key SAR trends, risky modifications, promising positions, suggested next analogs, scaffold groups, and a matched-pair evidence table.

Try `sample_data/sar_example_compounds.csv` for a quick SAR-specific check.

## Briefing Report Export

Generate a medicinal chemistry briefing report as JSON-backed Markdown:

```bash
curl -X POST http://localhost:8000/api/reports/briefing \
  -H "Content-Type: application/json" \
  -d '{
    "upload_id": "UPLOAD_ID",
    "project_name": "Patent SAR Briefing",
    "potency_column": "ic50_nm",
    "admet_columns": ["clint_ul_min_mg"],
    "min_fold_change": 3
  }'
```

Download report files:

```bash
curl -X POST "http://localhost:8000/api/reports/briefing/export?format=markdown" \
  -H "Content-Type: application/json" \
  -d '{"upload_id":"UPLOAD_ID","potency_column":"ic50_nm"}' \
  -o medchem_briefing.md

curl -X POST "http://localhost:8000/api/reports/briefing/export?format=docx" \
  -H "Content-Type: application/json" \
  -d '{"upload_id":"UPLOAD_ID","potency_column":"ic50_nm"}' \
  -o medchem_briefing.docx
```
