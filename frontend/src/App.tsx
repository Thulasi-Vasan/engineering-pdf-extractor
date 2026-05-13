import { useState, useEffect } from 'react';
import { 
  FileText, 
  History, 
  Activity, 
  AlertCircle, 
  ChevronRight,
  RefreshCw,
  LayoutDashboard
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

import { api } from './lib/api.ts';
import type { ExtractionResponse } from './lib/api.ts';
import { storage } from './lib/storage.ts';
import type { SavedRun } from './lib/storage.ts';

// --- Components ---
import FileUpload from './components/FileUpload.tsx';
import ExtractionOptions from './components/ExtractionOptions.tsx';
import ResultPanel from './components/ResultPanel.tsx';
import LoadingOverlay from './components/LoadingOverlay.tsx';

/**
 * Utility for tailwind class merging
 */
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
  
  // Extraction Options
  const [options, setOptions] = useState({
    use_llm_final_json: true,
    use_vision_dimensions: false,
    llm_final_model: '',
    vision_model: ''
  });

  // Check health on mount
  useEffect(() => {
    const checkHealth = async () => {
      const isOnline = await api.checkHealth();
      setBackendOnline(isOnline);
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30000); // Check every 30s
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
        ...options
      });

      setResult(response);
      
      // Save to history
      const savedRun: SavedRun = {
        id: response.run_id,
        timestamp: Date.now(),
        fileName: file.name,
        fileSize: file.size,
        status: response.status,
        response
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
      {/* Header */}
      <header className="h-16 glass border-b border-slate-200 px-6 flex items-center justify-between sticky top-0 z-30">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-brand-primary rounded-lg flex items-center justify-center shadow-lg shadow-brand-primary/20">
            <FileText className="text-white w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl">Engineering PDF Extractor</h1>
            <p className="text-xs text-slate-500 font-medium uppercase tracking-wider">Dashboard</p>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-100 border border-slate-200">
            <Activity className={cn(
              "w-4 h-4",
              backendOnline === true ? "text-brand-success" : backendOnline === false ? "text-brand-error" : "text-slate-400"
            )} />
            <span className="text-xs font-semibold text-slate-600">
              Server: {backendOnline === true ? 'Online' : backendOnline === false ? 'Offline' : 'Checking...'}
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 flex overflow-hidden">
        {/* Sidebar - History */}
        <aside className="w-72 border-r border-slate-200 bg-white overflow-y-auto hidden lg:block">
          <div className="p-4 border-b border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-700 font-semibold">
              <History className="w-4 h-4" />
              <span>Recent Runs</span>
            </div>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-bold uppercase">
              {history.length}
            </span>
          </div>
          <div className="divide-y divide-slate-50">
            {history.length === 0 ? (
              <div className="p-8 text-center text-slate-400">
                <p className="text-sm">No recent runs</p>
              </div>
            ) : (
              history.map((run) => (
                <button
                  key={run.id}
                  onClick={() => loadRunFromHistory(run)}
                  className="w-full p-4 text-left hover:bg-slate-50 transition-colors group relative"
                >
                  <div className="flex items-start justify-between mb-1">
                    <span className="text-xs font-mono text-slate-400 truncate w-32">#{run.id.slice(0, 8)}</span>
                    <span className={cn(
                      "text-[10px] px-1.5 py-0.5 rounded font-bold uppercase",
                      run.status === 'success' ? "bg-emerald-50 text-emerald-600" : "bg-amber-50 text-amber-600"
                    )}>
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
        </aside>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-6 md:p-8">
          <div className="max-w-7xl mx-auto grid grid-cols-1 xl:grid-cols-12 gap-8">
            
            {/* Left Column: Upload & Options */}
            <div className="xl:col-span-4 space-y-6">
              <section className="card p-5 space-y-6">
                <div className="flex items-center gap-2 mb-2">
                  <LayoutDashboard className="w-5 h-5 text-brand-accent" />
                  <h2 className="text-lg">Configuration</h2>
                </div>

                <FileUpload 
                  file={file} 
                  setFile={setFile} 
                  disabled={isExtracting} 
                />

                <ExtractionOptions 
                  options={options} 
                  setOptions={setOptions} 
                  disabled={isExtracting || !file}
                />

                <div className="pt-2">
                  <button
                    onClick={handleRunExtraction}
                    disabled={isExtracting || !file}
                    className="btn btn-primary w-full py-3 text-base shadow-lg shadow-brand-accent/20 gap-2"
                  >
                    {isExtracting ? (
                      <>
                        <RefreshCw className="w-5 h-5 animate-spin" />
                        Extracting...
                      </>
                    ) : (
                      <>
                        <Activity className="w-5 h-5" />
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

              {backendOnline === false && (
                <div className="p-4 bg-amber-50 border border-amber-100 rounded-lg flex gap-3 animate-in fade-in slide-in-from-top-2 duration-300">
                  <AlertCircle className="w-5 h-5 text-amber-500 shrink-0" />
                  <div>
                    <h4 className="text-sm font-semibold text-amber-800">Server Unreachable</h4>
                    <p className="text-xs text-amber-600 mt-1 leading-relaxed">The extraction might fail if the server is not running.</p>
                  </div>
                </div>
              )}

              {error && (
                <div className="p-4 bg-red-50 border border-red-100 rounded-lg flex gap-3 animate-in fade-in slide-in-from-top-2 duration-300">
                  <AlertCircle className="w-5 h-5 text-red-500 shrink-0" />
                  <div>
                    <h4 className="text-sm font-semibold text-red-800">Extraction Failed</h4>
                    <p className="text-xs text-red-600 mt-1 leading-relaxed">{error}</p>
                  </div>
                </div>
              )}
            </div>

            {/* Right Column: Results */}
            <div className="xl:col-span-8 relative min-h-[600px]">
              {isExtracting && <LoadingOverlay />}
              
              {!isExtracting && !result && !error && (
                <div className="h-full flex flex-col items-center justify-center text-center p-12 border-2 border-dashed border-slate-200 rounded-xl bg-slate-50/50">
                  <div className="w-20 h-20 bg-white rounded-2xl flex items-center justify-center shadow-sm mb-6 border border-slate-100">
                    <FileText className="w-10 h-10 text-slate-300" />
                  </div>
                  <h3 className="text-slate-600 text-xl font-medium">Ready for extraction</h3>
                  <p className="text-slate-400 mt-2 max-w-sm">
                    Upload an engineering PDF and configure the extraction options to begin processing.
                  </p>
                </div>
              )}

              {result && (
                <div className="animate-in fade-in slide-in-from-right-4 duration-500">
                  <ResultPanel result={result} onReset={handleReset} />
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
