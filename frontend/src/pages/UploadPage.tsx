import { FileUp, Loader2 } from "lucide-react";
import { useRef, useState } from "react";
import { createProject, uploadProjectCompoundFile } from "../api/client";
import type { MoleculeRecord } from "../types/molecule";

interface UploadPageProps {
  onUploadComplete: (uploadId: string, molecules: MoleculeRecord[], projectId?: string, projectName?: string) => void;
}

export function UploadPage({ onUploadComplete }: UploadPageProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("Lead Optimization Project");

  async function handleUpload() {
    if (!file) return;
    setError(null);
    setSummary(null);
    setIsUploading(true);
    try {
      const project = await createProject({ name: projectName.trim() || "Lead Optimization Project" });
      const response = await uploadProjectCompoundFile(project.id, file);
      setSummary(`${response.imported_count} compounds imported, ${response.skipped_count} skipped`);
      onUploadComplete(response.upload_id, response.molecules, project.id, project.name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <section className="page-section">
      <div className="section-heading">
        <p className="eyebrow">Compound intake</p>
        <h2>Upload compound data</h2>
      </div>

      <div className="project-intake-row">
        <label>
          Project name
          <input value={projectName} onChange={(event) => setProjectName(event.target.value)} />
        </label>
      </div>

      <div
        className="upload-zone"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          setFile(event.dataTransfer.files?.[0] ?? null);
        }}
      >
        <FileUp size={36} />
        <div>
          <strong>{file ? file.name : "Drop a CSV, SDF, or patent PDF file"}</strong>
          <span>PDF extraction imports text-encoded SMILES from patent examples and tables.</span>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.sdf,.pdf,application/pdf"
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          hidden
        />
      </div>

      <div className="actions-row">
        <button className="primary-button" disabled={!file || isUploading} onClick={handleUpload}>
          {isUploading ? <Loader2 className="spin" size={18} /> : <FileUp size={18} />}
          Import compounds
        </button>
      </div>

      {error && <p className="status error">{error}</p>}
      {summary && <p className="status success">{summary}</p>}
    </section>
  );
}
