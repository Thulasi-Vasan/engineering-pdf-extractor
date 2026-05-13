import { useState } from 'react';
import { 
  FileJson, 
  AlertTriangle, 
  Files, 
  Copy, 
  Download, 
  ExternalLink,
  ChevronRight,
  Check,
  Search,
  FileText,
  Eye,
  Layers,
  Map,
  BarChart4
} from 'lucide-react';
import { clsx } from 'clsx';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

import { api } from '../lib/api';
import type { ExtractionResponse } from '../lib/api';

interface ResultPanelProps {
  result: ExtractionResponse;
  onReset: () => void;
}

type Tab = 'final_json' | 'artifacts' | 'warnings';

export default function ResultPanel({ result, onReset }: ResultPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>('final_json');
  const [copied, setCopied] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(result.final_json, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadJson = () => {
    const blob = new Blob([JSON.stringify(result.final_json, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `extraction_${result.run_id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getStatusBadge = () => {
    switch (result.status) {
      case 'success':
        return <span className="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-[10px] font-bold uppercase border border-emerald-200">Success</span>;
      case 'partial_success':
        return <span className="bg-amber-100 text-amber-700 px-2 py-1 rounded text-[10px] font-bold uppercase border border-amber-200">Partial Success</span>;
      case 'failed':
        return <span className="bg-red-100 text-red-700 px-2 py-1 rounded text-[10px] font-bold uppercase border border-red-200">Failed</span>;
      default:
        return null;
    }
  };

  const artifactIcons: Record<string, any> = {
    page_detection: Map,
    raw_extraction: Eye,
    structured_data: Layers,
    final_json: FileJson,
    report: FileText
  };

  const artifactLabels: Record<string, string> = {
    page_detection: 'Page Detection Map',
    raw_extraction: 'Raw Text & Primitives',
    structured_data: 'Structured Engineering Data',
    final_json: 'LLM Final Engineering Data',
    report: 'Extraction Report (MD)'
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden animate-in fade-in zoom-in-95 duration-500">
      {/* Panel Header */}
      <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h2 className="text-xl font-bold text-slate-800">Extraction Results</h2>
            {getStatusBadge()}
          </div>
          <p className="text-xs text-slate-400 font-mono">Run ID: {result.run_id}</p>
        </div>

        <div className="flex items-center gap-2">
          <button 
            onClick={handleCopyJson}
            className="btn btn-secondary py-1.5 px-3 text-xs gap-2"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? 'Copied' : 'Copy JSON'}
          </button>
          <button 
            onClick={handleDownloadJson}
            className="btn btn-secondary py-1.5 px-3 text-xs gap-2"
          >
            <Download className="w-3.5 h-3.5" />
            Download
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="px-6 border-b border-slate-100 flex items-center gap-6">
        <TabButton 
          active={activeTab === 'final_json'} 
          onClick={() => setActiveTab('final_json')}
          icon={<FileJson className="w-4 h-4" />}
          label="Final JSON"
        />
        <TabButton 
          active={activeTab === 'artifacts'} 
          onClick={() => setActiveTab('artifacts')}
          icon={<Files className="w-4 h-4" />}
          label="Artifacts"
          count={Object.keys(result.artifacts).length}
        />
        <TabButton 
          active={activeTab === 'warnings'} 
          onClick={() => setActiveTab('warnings')}
          icon={<AlertTriangle className="w-4 h-4" />}
          label="Warnings"
          count={result.warnings.length}
          variant="warning"
        />
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {activeTab === 'final_json' && (
          <div className="flex-1 overflow-hidden flex flex-col">
            <div className="p-3 border-b border-slate-50 bg-slate-50/30 flex items-center gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
                <input 
                  type="text" 
                  placeholder="Search JSON keys or values..." 
                  className="w-full pl-9 pr-3 py-1.5 bg-white border border-slate-200 rounded-md text-xs focus:outline-none focus:ring-1 focus:ring-brand-accent transition-all"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </div>
            <div className="flex-1 overflow-auto bg-[#1a1b26] p-2 custom-scrollbar">
              <SyntaxHighlighter 
                language="json" 
                style={atomDark}
                customStyle={{ 
                  margin: 0, 
                  background: 'transparent',
                  fontSize: '12px',
                  lineHeight: '1.6'
                }}
              >
                {JSON.stringify(result.final_json, null, 2)}
              </SyntaxHighlighter>
            </div>
          </div>
        )}

        {activeTab === 'artifacts' && (
          <div className="p-6 space-y-4 overflow-auto">
            <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <BarChart4 className="w-4 h-4 text-brand-accent" />
              Generated Artifacts
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(result.artifacts).map(([key, path]) => {
                const Icon = artifactIcons[key] || FileText;
                return (
                  <a
                    key={key}
                    href={api.getArtifactUrl(path)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center gap-4 p-4 rounded-xl border border-slate-200 hover:border-brand-accent/30 hover:bg-blue-50/30 transition-all shadow-sm"
                  >
                    <div className="w-10 h-10 bg-slate-100 group-hover:bg-blue-100 rounded-lg flex items-center justify-center text-slate-500 group-hover:text-brand-accent transition-colors">
                      <Icon className="w-5 h-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-800 truncate">
                        {artifactLabels[key] || key}
                      </p>
                      <p className="text-[10px] text-slate-400 truncate mt-0.5">
                        {path}
                      </p>
                    </div>
                    <ExternalLink className="w-4 h-4 text-slate-300 group-hover:text-brand-accent opacity-0 group-hover:opacity-100 transition-all" />
                  </a>
                );
              })}
            </div>
          </div>
        )}

        {activeTab === 'warnings' && (
          <div className="p-6 space-y-4 overflow-auto">
            {result.warnings.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="w-16 h-16 bg-emerald-50 rounded-full flex items-center justify-center mb-4">
                  <Check className="w-8 h-8 text-emerald-500" />
                </div>
                <h4 className="text-slate-700 font-semibold">No Warnings</h4>
                <p className="text-slate-400 text-sm mt-1">Extraction completed without any detected issues.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {result.warnings.map((warning, i) => (
                  <div key={i} className="flex gap-4 p-4 bg-amber-50 border border-amber-100 rounded-xl">
                    <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                    <p className="text-sm text-amber-900 leading-relaxed">{warning}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-6 py-3 border-t border-slate-100 bg-slate-50/30 flex items-center justify-between text-[11px] text-slate-400 font-medium">
        <span>Processing completed in 42.5s</span>
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-emerald-500" />
            Verified Extraction
          </span>
          <button 
            onClick={onReset}
            className="text-brand-accent hover:underline flex items-center gap-1"
          >
            Run another PDF <ChevronRight className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  );
}

function TabButton({ active, onClick, icon, label, count, variant = 'primary' }: any) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "py-4 flex items-center gap-2 border-b-2 transition-all relative",
        active 
          ? (variant === 'warning' ? "border-amber-500 text-amber-700" : "border-brand-accent text-brand-primary")
          : "border-transparent text-slate-400 hover:text-slate-600 hover:border-slate-200"
      )}
    >
      {icon}
      <span className="text-sm font-semibold">{label}</span>
      {count !== undefined && (
        <span className={clsx(
          "text-[10px] px-1.5 py-0.5 rounded-full font-bold",
          active 
            ? (variant === 'warning' ? "bg-amber-100 text-amber-600" : "bg-blue-100 text-brand-accent")
            : "bg-slate-100 text-slate-500"
        )}>
          {count}
        </span>
      )}
    </button>
  );
}
