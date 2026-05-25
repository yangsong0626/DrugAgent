import { FlaskConical, FileText, Network, Table2, UploadCloud } from "lucide-react";
import { useMemo, useState } from "react";
import { MoleculeTable } from "./components/MoleculeTable";
import { DesignPage } from "./pages/DesignPage";
import { ReportPage } from "./pages/ReportPage";
import { SarPage } from "./pages/SarPage";
import { UploadPage } from "./pages/UploadPage";
import type { MoleculeRecord } from "./types/molecule";

type Tab = "upload" | "molecules" | "sar" | "design" | "report";

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("upload");
  const [uploadId, setUploadId] = useState<string | undefined>();
  const [projectId, setProjectId] = useState<string | undefined>();
  const [projectName, setProjectName] = useState<string | undefined>();
  const [molecules, setMolecules] = useState<MoleculeRecord[]>([]);

  const selectedUploadLabel = useMemo(() => {
    if (projectName) return `${projectName} · ${molecules.length} compounds`;
    if (!uploadId) return "No upload selected";
    return `${molecules.length} compounds loaded`;
  }, [molecules.length, projectName, uploadId]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">SAR</div>
          <div>
            <h1>Patent-to-SAR Agent</h1>
            <p>{selectedUploadLabel}</p>
          </div>
        </div>
        <nav className="nav-list" aria-label="Primary">
          <button className={activeTab === "upload" ? "active" : ""} onClick={() => setActiveTab("upload")}>
            <UploadCloud size={18} />
            Upload
          </button>
          <button className={activeTab === "molecules" ? "active" : ""} onClick={() => setActiveTab("molecules")}>
            <FlaskConical size={18} />
            Molecules
          </button>
          <button className={activeTab === "sar" ? "active" : ""} onClick={() => setActiveTab("sar")}>
            <Table2 size={18} />
            SAR
          </button>
          <button className={activeTab === "design" ? "active" : ""} onClick={() => setActiveTab("design")}>
            <Network size={18} />
            Design
          </button>
          <button className={activeTab === "report" ? "active" : ""} onClick={() => setActiveTab("report")}>
            <FileText size={18} />
            Report
          </button>
        </nav>
      </aside>

      <main className="workspace">
        {activeTab === "upload" && (
          <UploadPage
            onUploadComplete={(nextUploadId, nextMolecules, nextProjectId, nextProjectName) => {
              setUploadId(nextUploadId);
              setProjectId(nextProjectId);
              setProjectName(nextProjectName);
              setMolecules(nextMolecules);
              setActiveTab("sar");
            }}
          />
        )}
        {activeTab === "molecules" && <MoleculeTable uploadId={uploadId} molecules={molecules} onMoleculesChange={setMolecules} />}
        {activeTab === "sar" && <SarPage uploadId={uploadId} projectId={projectId} />}
        {activeTab === "design" && <DesignPage uploadId={uploadId} projectId={projectId} />}
        {activeTab === "report" && <ReportPage uploadId={uploadId} projectId={projectId} projectName={projectName} />}
      </main>
    </div>
  );
}
