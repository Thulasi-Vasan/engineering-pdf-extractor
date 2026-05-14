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
type CellTone = 'normal' | 'muted' | 'success' | 'warning' | 'danger';

interface TableCellData {
  primary: string;
  secondary?: string;
  meta?: string;
  tone?: CellTone;
  warnings?: string[];
}

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
          count={summary.warningCount}
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
            {summary.warningCount === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="w-14 h-14 bg-emerald-50 rounded-lg flex items-center justify-center mb-4">
                  <Check className="w-7 h-7 text-emerald-500" />
                </div>
                <h4 className="text-slate-700 font-semibold">No Warnings</h4>
                <p className="text-slate-400 text-sm mt-1">Extraction completed without any detected issues.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {summary.finalWarnings.map((warning) => (
                  <div key={warning} className="flex gap-4 p-4 bg-amber-50 border border-amber-100 rounded-lg">
                    <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                    <p className="text-sm text-amber-900 leading-relaxed">{warning}</p>
                  </div>
                ))}
                {summary.reviewItems.map((item) => (
                  <div key={reviewItemKey(item)} className="flex gap-4 p-4 bg-slate-50 border border-slate-200 rounded-lg">
                    <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-400">
                        {stringField(item, 'item_type') || 'Review Item'}
                      </p>
                      <p className="text-sm text-slate-800 leading-relaxed mt-1">
                        {stringField(item, 'reason') || stringField(item, 'warning') || stringField(item, 'description') || formatValue(item.value)}
                      </p>
                    </div>
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
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Metric label="Dimensions" value={summary.dimensions.length} />
        <Metric label="Threads" value={summary.threads.length} />
        <Metric label="GD&T" value={summary.gdtItems.length} tone={summary.gdtItems.length ? 'warning' : 'normal'} />
        <Metric label="Requirements" value={summary.requirements.length} />
        <Metric label="Review Items" value={summary.reviewItems.length} tone={summary.reviewItems.length ? 'warning' : 'normal'} />
      </div>

      <section className="bg-white border border-slate-200 rounded-lg overflow-hidden">
        <SectionHeader title="Title Block" />
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
          {summary.titleFields.length === 0 ? (
            <EmptyState label="No title block fields were returned." />
          ) : (
            summary.titleFields.slice(0, 12).map(([key, value]) => {
              const field = normalizeField(value, key);
              return (
                <div key={key} className="p-3 border-b border-r border-slate-100 min-h-[116px]">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-[10px] uppercase tracking-wider text-slate-400 font-bold">{field.label || formatLabel(key)}</p>
                    <ConfidenceBadge value={field.confidence} />
                  </div>
                  <p className="text-sm font-semibold text-slate-800 mt-1 break-words">{field.displayValue || '-'}</p>
                  {field.description && <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">{field.description}</p>}
                  <FieldMeta page={field.page} warnings={field.warnings} />
                </div>
              );
            })
          )}
        </div>
      </section>

      <DataTable
        title="Dimensions"
        columns={['Callout', 'Meaning', 'View / Region', 'Confidence', 'Evidence']}
        rows={summary.dimensions.slice(0, 18).map((item) => [
          cell(compactDimension(item), {
            secondary: dimensionMeta(item),
            meta: stringField(item, 'normalized_callout') && stringField(item, 'normalized_callout') !== compactDimension(item)
              ? `normalized: ${stringField(item, 'normalized_callout')}`
              : '',
          }),
          cell(stringField(item, 'label') || formatLabel(stringField(item, 'dimension_type') || stringField(item, 'role') || 'dimension'), {
            secondary: stringField(item, 'description'),
            warnings: warningList(item),
          }),
          cell(stringField(item, 'view_label') || stringField(item, 'region_id'), {
            secondary: stringField(item, 'region_id'),
            meta: stringField(item, 'page') ? `page ${stringField(item, 'page')}` : '',
          }),
          cell(stringField(item, 'confidence') || '-', {
            secondary: stringField(item, 'role_confidence') ? `role: ${stringField(item, 'role_confidence')}` : '',
            tone: confidenceTone(stringField(item, 'confidence')),
          }),
          cell(stringField(item, 'evidence') || compactDimension(item), {
            secondary: [stringField(item, 'source'), stringField(item, 'page') ? `page ${stringField(item, 'page')}` : ''].filter(Boolean).join(' · '),
          }),
        ])}
        emptyLabel="No dimensions returned."
      />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <DataTable
          title="Threads"
          columns={['Thread', 'Meaning', 'Source / Class', 'Evidence']}
          rows={summary.threads.slice(0, 12).map((item) => [
            cell(stringField(item, 'display_value') || threadLabel(item), {
              secondary: stringField(item, 'thread_designation') || stringField(item, 'thread_size'),
            }),
            cell(stringField(item, 'label') || 'Thread requirement', {
              secondary: stringField(item, 'description'),
              warnings: warningList(item),
            }),
            cell(stringField(item, 'source_type') || stringField(item, 'source'), {
              secondary: stringField(item, 'thread_class') ? `class ${stringField(item, 'thread_class')}` : '',
            }),
            cell(stringField(item, 'evidence') || stringField(item, 'raw_text') || '-'),
          ])}
          emptyLabel="No thread requirements returned."
        />

        <DataTable
          title="GD&T / Feature Control Frames"
          columns={['Control', 'Value', 'View / Region', 'Confidence', 'Review Notes']}
          rows={summary.gdtItems.slice(0, 12).map((item) => [
            cell(stringField(item, 'label') || formatLabel(stringField(item, 'requirement_type') || 'GD&T control'), {
              secondary: stringField(item, 'description'),
              warnings: warningList(item),
            }),
            cell(stringField(item, 'display_value') || formatValue(item.value), {
              secondary: stringField(item, 'evidence'),
            }),
            cell(stringField(item, 'view_label') || stringField(item, 'region_id'), {
              secondary: stringField(item, 'region_id'),
              meta: stringField(item, 'page') ? `page ${stringField(item, 'page')}` : '',
            }),
            cell(stringField(item, 'confidence') || 'review', {
              tone: confidenceTone(stringField(item, 'confidence') || 'review'),
            }),
            cell(stringField(item, 'review_reason') || stringField(item, 'reason') || '-', {
              secondary: warningList(item).join(' · '),
            }),
          ])}
          emptyLabel="No GD&T controls returned."
        />
      </div>

      <DataTable
        title="Manufacturing Requirements"
        columns={['Requirement', 'Value', 'Confidence', 'Evidence / Notes']}
        rows={summary.requirements.slice(0, 12).map((item) => [
          cell(stringField(item, 'label') || formatLabel(stringField(item, 'requirement_type') || 'requirement'), {
            secondary: stringField(item, 'description'),
            warnings: warningList(item),
          }),
          cell(stringField(item, 'display_value') || formatValue(item.value)),
          cell(stringField(item, 'confidence') || '-', {
            tone: confidenceTone(stringField(item, 'confidence')),
          }),
          cell(stringField(item, 'evidence') || stringField(item, 'raw_text') || '-', {
            secondary: [stringField(item, 'source'), stringField(item, 'page') ? `page ${stringField(item, 'page')}` : ''].filter(Boolean).join(' · '),
          }),
        ])}
        emptyLabel="No manufacturing requirements returned."
      />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <DataTable
          title="Drawing Regions"
          columns={['Region', 'Label', 'Description', 'Confidence']}
          rows={summary.drawingRegions.slice(0, 10).map((item) => [
            cell(stringField(item, 'region_id') || stringField(item, 'region_type')),
            cell(stringField(item, 'semantic_label') || stringField(item, 'label')),
            cell(stringField(item, 'description')),
            cell(stringField(item, 'confidence') || '-', { tone: confidenceTone(stringField(item, 'confidence')) }),
          ])}
          emptyLabel="No drawing regions returned."
        />

        <DataTable
          title="Review Items"
          columns={['Type', 'Value', 'Reason']}
          rows={summary.reviewItems.slice(0, 10).map((item) => [
            cell(stringField(item, 'item_type') || 'warning', { tone: 'warning' }),
            cell(formatValue(item.value) || stringField(item, 'evidence') || '-'),
            cell(stringField(item, 'reason') || stringField(item, 'warning') || stringField(item, 'description')),
          ])}
          emptyLabel="No review items returned."
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

function DataTable({ title, columns, rows, emptyLabel }: { title: string; columns: string[]; rows: TableCellData[][]; emptyLabel: string }) {
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
                <tr key={`${title}-${row.map((item) => item.primary).join('|')}`} className="hover:bg-slate-50/60">
                  {row.map((cell, cellIndex) => (
                    <td key={`${title}-${columns[cellIndex]}`} className="px-3 py-2 text-slate-700 align-top max-w-[340px]">
                      <TableCell cell={cell} />
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

function TableCell({ cell: tableCell }: { cell: TableCellData }) {
  return (
    <div>
      <p className={clsx('break-words', toneClass(tableCell.tone))}>{tableCell.primary || '-'}</p>
      {tableCell.secondary && <p className="text-xs text-slate-500 mt-1 leading-relaxed break-words">{tableCell.secondary}</p>}
      {tableCell.meta && <p className="text-[10px] text-slate-400 mt-1 uppercase tracking-wide break-words">{tableCell.meta}</p>}
      {tableCell.warnings && tableCell.warnings.length > 0 && (
        <div className="mt-1.5 space-y-1">
          {tableCell.warnings.slice(0, 2).map((warning) => (
            <p key={warning} className="flex items-start gap-1 text-[11px] text-amber-700 leading-snug">
              <AlertTriangle className="w-3 h-3 shrink-0 mt-0.5" />
              <span>{warning}</span>
            </p>
          ))}
          {tableCell.warnings.length > 2 && <p className="text-[10px] text-amber-600">+{tableCell.warnings.length - 2} more warnings</p>}
        </div>
      )}
    </div>
  );
}

interface SummaryData {
  titleFields: [string, unknown][];
  dimensions: JsonRecord[];
  threads: JsonRecord[];
  requirements: JsonRecord[];
  gdtItems: JsonRecord[];
  drawingRegions: JsonRecord[];
  reviewItems: JsonRecord[];
  finalWarnings: string[];
  warningCount: number;
}

function buildSummary(finalData: JsonRecord, result: ExtractionResponse): SummaryData {
  const titleBlock = asRecord(finalData.title_block) ?? {};
  const reviewItems = asRecordArray(finalData.review_items).concat(result.warnings.map((warning) => ({ warning })));
  const finalWarnings = asStringArray(finalData.warnings);
  const allRequirements = asRecordArray(finalData.manufacturing_requirements);
  const gdtItems = allRequirements.filter(isGdtItem);
  return {
    titleFields: Object.entries(titleBlock),
    dimensions: asRecordArray(finalData.dimensions),
    threads: asRecordArray(finalData.threads),
    requirements: allRequirements.filter((item) => !isGdtItem(item)),
    gdtItems,
    drawingRegions: asRecordArray(finalData.drawing_regions),
    reviewItems,
    finalWarnings,
    warningCount: reviewItems.length + finalWarnings.length,
  };
}

function asRecord(value: unknown): JsonRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonRecord : null;
}

function asRecordArray(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.map(asRecord).filter(Boolean) as JsonRecord[] : [];
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(formatValue).filter(Boolean) : [];
}

function cell(primary: unknown, options: Omit<Partial<TableCellData>, 'primary'> = {}): TableCellData {
  return {
    primary: formatValue(primary) || '-',
    ...options,
  };
}

function stringField(record: JsonRecord, key: string): string {
  return formatValue(record[key]);
}

interface DisplayField {
  label: string;
  displayValue: string;
  description: string;
  confidence: string;
  page: string;
  warnings: string[];
}

function normalizeField(value: unknown, fallbackKey: string): DisplayField {
  const record = asRecord(value);
  if (!record) {
    return {
      label: formatLabel(fallbackKey),
      displayValue: formatValue(value),
      description: '',
      confidence: '',
      page: '',
      warnings: [],
    };
  }

  return {
    label: stringField(record, 'label') || formatLabel(fallbackKey),
    displayValue: stringField(record, 'display_value') || stringField(record, 'value'),
    description: stringField(record, 'description'),
    confidence: stringField(record, 'confidence'),
    page: stringField(record, 'page'),
    warnings: arrayField(record, 'warnings').map(formatValue).filter(Boolean),
  };
}

function arrayField(record: JsonRecord, key: string): unknown[] {
  const value = record[key];
  return Array.isArray(value) ? value : [];
}

function formatLabel(value: string): string {
  return value
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : String(value);
  if (typeof value === 'string') return value;
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  const nested = asRecord(value);
  if (nested) return stringField(nested, 'display_value') || stringField(nested, 'value') || stringField(nested, 'label') || '';
  return '';
}

function compactDimension(record: JsonRecord): string {
  const raw = stringField(record, 'raw_callout');
  if (raw) return raw;
  const value = formatValue(record.value);
  const unit = stringField(record, 'unit');
  return [value, unit].filter(Boolean).join(' ');
}

function dimensionMeta(record: JsonRecord): string {
  const pieces = [
    stringField(record, 'dimension_type'),
    stringField(record, 'role'),
    stringField(record, 'quantity') ? `qty ${stringField(record, 'quantity')}` : '',
    stringField(record, 'angle_value') ? `${stringField(record, 'angle_value')} ${stringField(record, 'angle_unit') || 'deg'}` : '',
  ].filter(Boolean);
  return pieces.join(' · ');
}

function threadLabel(record: JsonRecord): string {
  const size = stringField(record, 'thread_size');
  const pitch = formatValue(record.pitch);
  const tpi = formatValue(record.threads_per_inch);
  if (pitch) return `${size} x ${pitch}`;
  if (tpi) return `${size}-${tpi}`;
  return size || stringField(record, 'label');
}

function confidenceTone(value: string): CellTone {
  const normalized = value.toLowerCase();
  if (normalized === 'high') return 'success';
  if (normalized === 'medium') return 'warning';
  if (normalized === 'low' || normalized === 'review') return 'danger';
  return 'normal';
}

function toneClass(tone: CellTone = 'normal'): string {
  if (tone === 'success') return 'text-emerald-700 font-semibold';
  if (tone === 'warning') return 'text-amber-700 font-semibold';
  if (tone === 'danger') return 'text-red-700 font-semibold';
  if (tone === 'muted') return 'text-slate-500';
  return 'text-slate-800';
}

function warningList(record: JsonRecord): string[] {
  return arrayField(record, 'warnings').map(formatValue).filter(Boolean);
}

function isGdtItem(record: JsonRecord): boolean {
  const label = stringField(record, 'label').toLowerCase();
  const requirementType = stringField(record, 'requirement_type').toLowerCase();
  const semanticLabel = stringField(record, 'semantic_label').toLowerCase();
  const text = [
    label,
    requirementType,
    semanticLabel,
    stringField(record, 'value'),
    stringField(record, 'display_value'),
    stringField(record, 'description'),
    stringField(record, 'evidence'),
  ].join(' ').toLowerCase();

  if (label.includes('gd&t') || requirementType.includes('gdt')) return true;
  if (text.includes('feature control frame')) return true;
  if (semanticLabel.includes('flatness') || semanticLabel.includes('perpendicularity') || semanticLabel.includes('position control')) return true;
  return text.includes('flatness') && text.includes('0.002');
}

function reviewItemKey(record: JsonRecord): string {
  const key = [
    stringField(record, 'target_id'),
    stringField(record, 'item_type'),
    stringField(record, 'reason'),
    stringField(record, 'warning'),
    stringField(record, 'evidence'),
    formatValue(record.value),
  ].filter(Boolean).join('|');
  return key || JSON.stringify(record);
}

function ConfidenceBadge({ value }: { value: string }) {
  if (!value) return null;
  const normalized = value.toLowerCase();
  const className = clsx(
    'rounded px-1.5 py-0.5 text-[10px] font-bold uppercase',
    normalized === 'high' && 'bg-emerald-50 text-emerald-700',
    normalized === 'medium' && 'bg-amber-50 text-amber-700',
    (normalized === 'low' || normalized === 'review') && 'bg-red-50 text-red-700',
    !['high', 'medium', 'low', 'review'].includes(normalized) && 'bg-slate-100 text-slate-500',
  );
  return <span className={className}>{value}</span>;
}

function FieldMeta({ page, warnings }: { page: string; warnings: string[] }) {
  if (!page && warnings.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px]">
      {page && <span className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold text-slate-500">Page {page}</span>}
      {warnings.length > 0 && (
        <span className="rounded bg-amber-50 px-1.5 py-0.5 font-semibold text-amber-700">
          {warnings.length === 1 ? '1 warning' : `${warnings.length} warnings`}
        </span>
      )}
    </div>
  );
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
