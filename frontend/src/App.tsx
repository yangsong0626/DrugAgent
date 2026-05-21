import { FlaskConical, FileText, Network, UploadCloud } from "lucide-react";
import { useMemo, useState } from "react";
import { MoleculeTable } from "./components/MoleculeTable";
import { DesignPage } from "./pages/DesignPage";
import { ReportPage } from "./pages/ReportPage";
import { UploadPage } from "./pages/UploadPage";
import type { MoleculeRecord } from "./types/molecule";

type Tab = "upload" | "molecules" | "design" | "report";

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("upload");
  const [uploadId, setUploadId] = useState<string | undefined>();
  const [molecules, setMolecules] = useState<MoleculeRecord[]>([]);

  const selectedUploadLabel = useMemo(() => {
    if (!uploadId) return "No upload selected";
    return `${molecules.length} compounds loaded`;
  }, [molecules.length, uploadId]);

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
            onUploadComplete={(nextUploadId, nextMolecules) => {
              setUploadId(nextUploadId);
              setMolecules(nextMolecules);
              setActiveTab("molecules");
            }}
          />
        )}
        {activeTab === "molecules" && <MoleculeTable uploadId={uploadId} molecules={molecules} onMoleculesChange={setMolecules} />}
        {activeTab === "design" && <DesignPage uploadId={uploadId} />}
        {activeTab === "report" && <ReportPage uploadId={uploadId} />}
      </main>
    </div>
  );
}
