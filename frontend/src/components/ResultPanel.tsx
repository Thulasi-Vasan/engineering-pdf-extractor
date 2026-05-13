import { useState } from 'react';
import {
  AlertTriangle,
  BarChart4,
  Check,
  ChevronRight,
  Copy,
  Download,
  ExternalLink,
  Eye,
  FileJson,
  Files,
  FileText,
  Layers,
  Map,
  Search,
  Table2,
} from 'lucide-react';
import { clsx } from 'clsx';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

import { api } from '../lib/api.ts';
import type { ExtractionResponse } from '../lib/api.ts';

interface ResultPanelProps {
  result: ExtractionResponse;
  onReset: () => void;
}

type Tab = 'summary' | 'final_json' | 'artifacts' | 'warnings';
type JsonRecord = Record<string, unknown>;

export default function ResultPanel({ result, onReset }: ResultPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>('summary');
  const [copied, setCopied] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const finalJsonPayload = asRecord(result.final_json)?.final_data;
  const displayJson = asRecord(finalJsonPayload) ?? asRecord(result.final_json) ?? {};
  const summary = buildSummary(displayJson, result);

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(displayJson, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadJson = () => {
    const blob = new Blob([JSON.stringify(displayJson, null, 2)], { type: 'application/json' });
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

  const artifactIcons: Record<string, typeof Map> = {
    page_detection: Map,
    raw_extraction: Eye,
    structured_data: Layers,
    final_json: FileJson,
    report: FileText,
  };

  const artifactLabels: Record<string, string> = {
    page_detection: 'Page Detection Map',
    raw_extraction: 'Raw Text & Primitives',
    structured_data: 'Structured Engineering Data',
    final_json: 'LLM Final Engineering Data',
    report: 'Extraction Report (MD)',
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden animate-in fade-in zoom-in-95 duration-500">
      <div className="px-5 py-4 border-b border-slate-100 bg-white flex flex-col xl:flex-row xl:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h2 className="text-lg font-bold text-slate-800">Extraction Results</h2>
            {getStatusBadge()}
          </div>
          <p className="text-xs text-slate-400 font-mono">Run ID: {result.run_id}</p>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={handleCopyJson} className="btn btn-secondary py-1.5 px-3 text-xs gap-2">
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? 'Copied' : 'Copy JSON'}
          </button>
          <button onClick={handleDownloadJson} className="btn btn-secondary py-1.5 px-3 text-xs gap-2">
            <Download className="w-3.5 h-3.5" />
            Download
          </button>
        </div>
      </div>

      <div className="px-5 border-b border-slate-100 flex items-center gap-5 overflow-x-auto">
        <TabButton
          active={activeTab === 'summary'}
          onClick={() => setActiveTab('summary')}
          icon={<Table2 className="w-4 h-4" />}
          label="Summary"
        />
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
          count={Object.values(result.artifacts).filter(Boolean).length}
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

      <div className="flex-1 overflow-hidden flex flex-col">
        {activeTab === 'summary' && <SummaryView summary={summary} />}

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
                  lineHeight: '1.6',
                }}
              >
                {JSON.stringify(displayJson, null, 2)}
              </SyntaxHighlighter>
            </div>
          </div>
        )}

        {activeTab === 'artifacts' && (
          <div className="p-5 space-y-4 overflow-auto">
            <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
              <BarChart4 className="w-4 h-4 text-brand-accent" />
              Generated Artifacts
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {Object.entries(result.artifacts).filter((entry): entry is [string, string] => Boolean(entry[1])).map(([key, path]) => {
                const Icon = artifactIcons[key] || FileText;
                return (
                  <a
                    key={key}
                    href={api.getArtifactUrl(path)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center gap-3 p-3 rounded-lg border border-slate-200 hover:border-brand-accent/30 hover:bg-blue-50/30 transition-all"
                  >
                    <div className="w-9 h-9 bg-slate-100 group-hover:bg-blue-100 rounded-lg flex items-center justify-center text-slate-500 group-hover:text-brand-accent transition-colors">
                      <Icon className="w-4.5 h-4.5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-slate-800 truncate">{artifactLabels[key] || key}</p>
                      <p className="text-[10px] text-slate-400 truncate mt-0.5">{path}</p>
                    </div>
                    <ExternalLink className="w-4 h-4 text-slate-300 group-hover:text-brand-accent opacity-0 group-hover:opacity-100 transition-all" />
                  </a>
                );
              })}
            </div>
          </div>
        )}

        {activeTab === 'warnings' && (
          <div className="p-5 space-y-4 overflow-auto">
            {result.warnings.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="w-14 h-14 bg-emerald-50 rounded-lg flex items-center justify-center mb-4">
                  <Check className="w-7 h-7 text-emerald-500" />
                </div>
                <h4 className="text-slate-700 font-semibold">No Warnings</h4>
                <p className="text-slate-400 text-sm mt-1">Extraction completed without any detected issues.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {result.warnings.map((warning) => (
                  <div key={warning} className="flex gap-4 p-4 bg-amber-50 border border-amber-100 rounded-lg">
                    <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                    <p className="text-sm text-amber-900 leading-relaxed">{warning}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="px-5 py-3 border-t border-slate-100 bg-slate-50/30 flex items-center justify-between text-[11px] text-slate-400 font-medium">
        <span>{summary.dimensions.length} dimensions extracted</span>
        <button onClick={onReset} className="text-brand-accent hover:underline flex items-center gap-1">
          Run another PDF <ChevronRight className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

function SummaryView({ summary }: { summary: SummaryData }) {
  return (
    <div className="flex-1 overflow-auto bg-slate-50/40 p-5 space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Metric label="Dimensions" value={summary.dimensions.length} />
        <Metric label="Threads" value={summary.threads.length} />
        <Metric label="Requirements" value={summary.requirements.length} />
        <Metric label="Review Items" value={summary.reviewItems.length} tone={summary.reviewItems.length ? 'warning' : 'normal'} />
      </div>

      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <SectionHeader title="Title Block" />
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-slate-100">
          {summary.titleFields.length === 0 ? (
            <EmptyState label="No title block fields were returned." />
          ) : (
            summary.titleFields.slice(0, 12).map(([key, value]) => (
              <div key={key} className="p-3">
                <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">{formatLabel(key)}</p>
                <p className="text-sm text-slate-800 mt-1 break-words">{formatValue(value)}</p>
              </div>
            ))
          )}
        </div>
      </section>

      <DataTable
        title="Dimensions"
        columns={['Value', 'Label', 'View', 'Confidence', 'Evidence']}
        rows={summary.dimensions.slice(0, 18).map((item) => [
          compactDimension(item),
          stringField(item, 'label'),
          stringField(item, 'view_label'),
          stringField(item, 'confidence'),
          stringField(item, 'evidence') || stringField(item, 'raw_callout'),
        ])}
        emptyLabel="No dimensions returned."
      />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <DataTable
          title="Threads"
          columns={['Thread', 'Class', 'Source', 'Evidence']}
          rows={summary.threads.slice(0, 12).map((item) => [
            threadLabel(item),
            stringField(item, 'thread_class'),
            stringField(item, 'source_type'),
            stringField(item, 'evidence'),
          ])}
          emptyLabel="No thread requirements returned."
        />

        <DataTable
          title="Manufacturing Requirements"
          columns={['Type', 'Value', 'Confidence']}
          rows={summary.requirements.slice(0, 12).map((item) => [
            stringField(item, 'requirement_type') || stringField(item, 'label'),
            formatValue(item.value),
            stringField(item, 'confidence'),
          ])}
          emptyLabel="No manufacturing requirements returned."
        />
      </div>
    </div>
  );
}

function Metric({ label, value, tone = 'normal' }: { label: string; value: number; tone?: 'normal' | 'warning' }) {
  return (
    <div className="bg-white border border-slate-200 rounded-lg p-3">
      <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">{label}</p>
      <p className={clsx('text-2xl font-semibold mt-1', tone === 'warning' ? 'text-amber-600' : 'text-slate-800')}>{value}</p>
    </div>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="px-3 py-2 border-b border-slate-100 bg-slate-50/60">
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
    </div>
  );
}

function DataTable({ title, columns, rows, emptyLabel }: { title: string; columns: string[]; rows: string[][]; emptyLabel: string }) {
  return (
    <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
      <SectionHeader title={title} />
      {rows.length === 0 ? (
        <EmptyState label={emptyLabel} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-[10px] uppercase tracking-wider text-slate-400">
              <tr>
                {columns.map((column) => (
                  <th key={column} className="text-left font-bold px-3 py-2 border-b border-slate-100 whitespace-nowrap">{column}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((row) => (
                <tr key={`${title}-${row.join('|')}`} className="hover:bg-slate-50/60">
                  {row.map((cell, cellIndex) => (
                    <td key={`${title}-${columns[cellIndex]}-${cell}`} className="px-3 py-2 text-slate-700 align-top max-w-[280px]">
                      <span className={cellIndex === 3 && title === 'Dimensions' ? confidenceClass(cell) : ''}>{cell || '-'}</span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="p-5 text-sm text-slate-400">{label}</div>;
}

interface SummaryData {
  titleFields: [string, unknown][];
  dimensions: JsonRecord[];
  threads: JsonRecord[];
  requirements: JsonRecord[];
  reviewItems: JsonRecord[];
}

function buildSummary(finalData: JsonRecord, result: ExtractionResponse): SummaryData {
  const titleBlock = asRecord(finalData.title_block) ?? {};
  return {
    titleFields: Object.entries(titleBlock),
    dimensions: asRecordArray(finalData.dimensions),
    threads: asRecordArray(finalData.threads),
    requirements: asRecordArray(finalData.manufacturing_requirements),
    reviewItems: asRecordArray(finalData.review_items).concat(result.warnings.map((warning) => ({ reason: warning }))),
  };
}

function asRecord(value: unknown): JsonRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : null;
}

function asRecordArray(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.map(asRecord).filter(Boolean) as JsonRecord[] : [];
}

function stringField(record: JsonRecord, key: string): string {
  return formatValue(record[key]);
}

function formatLabel(value: string): string {
  return value.replace(/_/g, ' ');
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : String(value);
  if (typeof value === 'string') return value;
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return JSON.stringify(value);
}

function compactDimension(record: JsonRecord): string {
  const raw = stringField(record, 'raw_callout');
  if (raw) return raw;
  const value = formatValue(record.value);
  const unit = stringField(record, 'unit');
  return [value, unit].filter(Boolean).join(' ');
}

function threadLabel(record: JsonRecord): string {
  const size = stringField(record, 'thread_size');
  const pitch = formatValue(record.pitch);
  const tpi = formatValue(record.threads_per_inch);
  if (pitch) return `${size} x ${pitch}`;
  if (tpi) return `${size}-${tpi}`;
  return size || stringField(record, 'label');
}

function confidenceClass(value: string): string {
  const normalized = value.toLowerCase();
  if (normalized === 'high') return 'text-emerald-700 font-semibold';
  if (normalized === 'medium') return 'text-amber-700 font-semibold';
  if (normalized === 'low' || normalized === 'review') return 'text-red-700 font-semibold';
  return '';
}

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  count?: number;
  variant?: 'primary' | 'warning';
}

function TabButton({ active, onClick, icon, label, count, variant = 'primary' }: TabButtonProps) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        'py-4 flex items-center gap-2 border-b-2 transition-all relative whitespace-nowrap',
        active
          ? (variant === 'warning' ? 'border-amber-500 text-amber-700' : 'border-brand-accent text-brand-primary')
          : 'border-transparent text-slate-400 hover:text-slate-600 hover:border-slate-200',
      )}
    >
      {icon}
      <span className="text-sm font-semibold">{label}</span>
      {count !== undefined && (
        <span
          className={clsx(
            'text-[10px] px-1.5 py-0.5 rounded-full font-bold',
            active
              ? (variant === 'warning' ? 'bg-amber-100 text-amber-600' : 'bg-blue-100 text-brand-accent')
              : 'bg-slate-100 text-slate-500',
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}
