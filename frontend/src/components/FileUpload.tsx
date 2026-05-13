import { useCallback, useState, type DragEvent, type ChangeEvent } from 'react';
import { Upload, X, File as FileIcon, CheckCircle2 } from 'lucide-react';
import { clsx } from 'clsx';

interface FileUploadProps {
  file: File | null;
  setFile: (file: File | null) => void;
  disabled?: boolean;
}

export default function FileUpload({ file, setFile, disabled }: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);

  const onDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    if (disabled) return;
    setIsDragging(true);
  }, [disabled]);

  const onDragLeave = useCallback(() => {
    setIsDragging(false);
  }, []);

  const onDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (disabled) return;

    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile && droppedFile.type === 'application/pdf') {
      setFile(droppedFile);
    }
  }, [disabled, setFile]);

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile && selectedFile.type === 'application/pdf') {
      setFile(selectedFile);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="space-y-3">
      <label className="label">Engineering PDF File</label>
      
      {!file ? (
        <div
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          className={clsx(
            "relative border-2 border-dashed rounded-xl p-8 transition-all duration-200 flex flex-col items-center justify-center text-center group",
            isDragging 
              ? "border-brand-accent bg-blue-50/50" 
              : "border-slate-200 bg-slate-50 hover:border-slate-300 hover:bg-white",
            disabled && "opacity-50 cursor-not-allowed"
          )}
        >
          <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center shadow-sm border border-slate-100 mb-4 group-hover:scale-110 transition-transform pointer-events-none">
            <Upload className={clsx("w-6 h-6", isDragging ? "text-brand-accent" : "text-slate-400")} />
          </div>
          
          <p className="text-sm font-semibold text-slate-700 pointer-events-none">
            Click to upload or drag and drop
          </p>
          <p className="text-xs text-slate-400 mt-1 pointer-events-none">
            Standard engineering PDF documents only
          </p>

          <input
            type="file"
            accept=".pdf"
            onChange={onFileChange}
            disabled={disabled}
            className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed z-10"
          />
        </div>
      ) : (
        <div className="flex items-center gap-4 p-4 bg-blue-50/50 border border-blue-100 rounded-xl animate-in zoom-in-95 duration-200">
          <div className="w-12 h-12 bg-white rounded-lg flex items-center justify-center shadow-sm border border-blue-100 shrink-0">
            <FileIcon className="w-6 h-6 text-brand-accent" />
          </div>
          
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-slate-800 truncate">{file.name}</p>
              <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
            </div>
            <p className="text-xs text-slate-500 mt-0.5">{formatSize(file.size)}</p>
          </div>

          <button
            onClick={() => setFile(null)}
            disabled={disabled}
            className="p-2 hover:bg-white rounded-full text-slate-400 hover:text-red-500 transition-all disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      )}
    </div>
  );
}
