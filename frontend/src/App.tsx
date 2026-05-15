import { useEffect, useState } from 'react';
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Database,
  FileJson,
  FileText,
  History,
  LayoutDashboard,
  RefreshCw,
  Search,
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import { api } from './lib/api.ts';
import type { ExtractionResponse } from './lib/api.ts';
import { storage } from './lib/storage.ts';
import type { SavedRun } from './lib/storage.ts';

import FileUpload from './components/FileUpload.tsx';
import ExtractionOptions from './components/ExtractionOptions.tsx';
import ResultPanel from './components/ResultPanel.tsx';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [isExtracting, setIsExtracting] = useState(false);
  const [result, setResult] = useState<ExtractionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);
  const [history, setHistory] = useState<SavedRun[]>(() => storage.getRuns());
  const [options, setOptions] = useState({
    use_llm_final_json: true,
    use_vision_dimensions: false,
    llm_final_model: '',
    vision_model: '',
  });

  useEffect(() => {
    const checkHealth = async () => {
      const isOnline = await api.checkHealth();
      setBackendOnline(isOnline);
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleRunExtraction = async () => {
    if (!file) return;

    setIsExtracting(true);
    setError(null);
    setResult(null);

    try {
      const response = await api.extract({
        file,
        ...options,
      });

      setResult(response);
      const savedRun: SavedRun = {
        id: response.run_id,
        timestamp: Date.now(),
        fileName: file.name,
        fileSize: file.size,
        status: response.status,
        response,
      };
      storage.saveRun(savedRun);
      setHistory(storage.getRuns());
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'An unexpected error occurred during extraction.';
      setError(message);
      console.error(err);
    } finally {
      setIsExtracting(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setResult(null);
    setError(null);
  };

  const loadRunFromHistory = (run: SavedRun) => {
    if (run.response) {
      setResult(run.response);
      setError(null);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="h-16 bg-white border-b border-slate-200 px-5 flex items-center justify-between sticky top-0 z-30">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-brand-primary rounded-lg flex items-center justify-center shadow-sm">
            <FileText className="text-white w-5 h-5" />
          </div>
          <div>
            <h1 className="text-lg">Engineering PDF Extractor</h1>
            <p className="text-[11px] text-slate-500 font-medium uppercase tracking-wider">Extraction Workspace</p>
          </div>
        </div>

        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-50 border border-slate-200">
          <Activity
            className={cn(
              'w-4 h-4',
              backendOnline === true ? 'text-brand-success' : backendOnline === false ? 'text-brand-error' : 'text-slate-400',
            )}
          />
          <span className="text-xs font-semibold text-slate-600">
            Server: {backendOnline === true ? 'Online' : backendOnline === false ? 'Offline' : 'Checking...'}
          </span>
        </div>
      </header>

      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)] overflow-hidden">
        <aside className="bg-white border-r border-slate-200 overflow-y-auto">
          <div className="p-5 space-y-5">
            <section className="space-y-5">
              <div className="flex items-center gap-2">
                <LayoutDashboard className="w-5 h-5 text-brand-accent" />
                <h2 className="text-base">Configuration</h2>
              </div>

              <FileUpload file={file} setFile={setFile} disabled={isExtracting} />

              <ExtractionOptions
                options={options}
                setOptions={setOptions}
                disabled={isExtracting || !file}
              />

              <div className="pt-1">
                <button
                  onClick={handleRunExtraction}
                  disabled={isExtracting || !file}
                  className="btn btn-primary w-full py-3 text-sm shadow-sm gap-2"
                >
                  {isExtracting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Extracting PDF
                    </>
                  ) : (
                    <>
                      <Activity className="w-4 h-4" />
                      Extract PDF
                    </>
                  )}
                </button>

                {file && !isExtracting && (
                  <button
                    onClick={handleReset}
                    className="w-full mt-3 text-xs text-slate-400 hover:text-slate-600 font-medium transition-colors"
                  >
                    Reset and start over
                  </button>
                )}
              </div>
            </section>

            {isExtracting && <SidebarProgress />}

            {backendOnline === false && (
              <div className="p-3 bg-amber-50 border border-amber-100 rounded-lg flex gap-3">
                <AlertCircle className="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-xs font-semibold text-amber-800">Server Unreachable</h4>
                  <p className="text-xs text-amber-600 mt-1 leading-relaxed">
                    The extraction may fail if the backend is not running.
                  </p>
                </div>
              </div>
            )}

            {error && (
              <div className="p-3 bg-red-50 border border-red-100 rounded-lg flex gap-3">
                <AlertCircle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-xs font-semibold text-red-800">Extraction Failed</h4>
                  <p className="text-xs text-red-600 mt-1 leading-relaxed">{error}</p>
                </div>
              </div>
            )}

            <section className="border-t border-slate-100 pt-5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-slate-700 font-semibold text-sm">
                  <History className="w-4 h-4" />
                  <span>Recent Runs</span>
                </div>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-bold uppercase">
                  {history.length}
                </span>
              </div>

              <div className="space-y-2">
                {history.length === 0 ? (
                  <div className="py-6 text-center text-slate-400 border border-dashed border-slate-200 rounded-lg">
                    <p className="text-sm">No recent runs</p>
                  </div>
                ) : (
                  history.map((run) => (
                    <button
                      key={run.id}
                      onClick={() => loadRunFromHistory(run)}
                      className="w-full p-3 text-left hover:bg-slate-50 transition-colors group relative border border-slate-100 rounded-lg"
                    >
                      <div className="flex items-start justify-between mb-1">
                        <span className="text-[11px] font-mono text-slate-400 truncate w-28">#{run.id.slice(0, 8)}</span>
                        <span
                          className={cn(
                            'text-[9px] px-1.5 py-0.5 rounded font-bold uppercase',
                            run.status === 'success' ? 'bg-emerald-50 text-emerald-600' : 'bg-amber-50 text-amber-600',
                          )}
                        >
                          {run.status}
                        </span>
                      </div>
                      <p className="text-sm font-medium text-slate-700 truncate mb-1 pr-4">{run.fileName}</p>
                      <p className="text-[10px] text-slate-400">{new Date(run.timestamp).toLocaleString()}</p>
                      <ChevronRight className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-300 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </button>
                  ))
                )}
              </div>
            </section>
          </div>
        </aside>

        <section className="min-w-0 overflow-y-auto p-5 md:p-6">
          <div className="h-full min-h-[640px]">
            {isExtracting && <ProcessingWorkspace />}

            {!isExtracting && !result && !error && (
              <div className="h-full flex flex-col items-center justify-center text-center p-12 border border-dashed border-slate-200 rounded-lg bg-white">
                <div className="w-16 h-16 bg-slate-50 rounded-lg flex items-center justify-center mb-5 border border-slate-100">
                  <FileText className="w-8 h-8 text-slate-300" />
                </div>
                <h3 className="text-slate-700 text-lg font-semibold">Ready for extraction</h3>
                <p className="text-slate-400 mt-2 max-w-sm text-sm">
                  Upload an engineering PDF in the sidebar. Results will appear here as tables and JSON.
                </p>
              </div>
            )}

            {result && (
              <div className="animate-in fade-in slide-in-from-right-4 duration-500 h-full">
                <ResultPanel result={result} onReset={handleReset} />
              </div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

const WORKFLOW_STEPS = [
  { label: 'Upload PDF', icon: FileText },
  { label: 'Detect pages', icon: Search },
  { label: 'Extract evidence', icon: Database },
  { label: 'Build final JSON', icon: FileJson },
];

function SidebarProgress() {
  return (
    <section className="border border-blue-100 bg-blue-50/40 rounded-lg p-3">
      <div className="flex items-center gap-2 text-brand-primary font-semibold text-sm mb-3">
        <Clock className="w-4 h-4 text-brand-accent" />
        <span>Processing</span>
      </div>
      <div className="space-y-2">
        {WORKFLOW_STEPS.map((step, index) => {
          const active = index === WORKFLOW_STEPS.length - 1;
          return (
            <div key={step.label} className="flex items-center gap-2 text-xs">
              <div
                className={cn(
                  'w-6 h-6 rounded-md flex items-center justify-center border',
                  active ? 'bg-white border-brand-accent text-brand-accent' : 'bg-emerald-50 border-emerald-100 text-emerald-500',
                )}
              >
                {active ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
              </div>
              <span className={active ? 'font-semibold text-slate-700' : 'text-slate-500'}>{step.label}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ProcessingWorkspace() {
  return (
    <div className="h-full min-h-[640px] border border-slate-200 rounded-lg bg-white flex items-center justify-center text-center p-10">
      <div className="max-w-md">
        <div className="w-14 h-14 mx-auto rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center mb-5">
          <RefreshCw className="w-7 h-7 text-brand-accent animate-spin" />
        </div>
        <h3 className="text-lg font-semibold text-slate-800">Extracting engineering data</h3>
        <p className="text-sm text-slate-500 mt-2">
          The backend is generating deterministic artifacts and the final downstream JSON.
        </p>
      </div>
    </div>
  );
}
