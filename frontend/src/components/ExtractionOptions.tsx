import { useState, type ChangeEvent } from 'react';
import { Settings, ChevronDown, ChevronUp, Cpu, Eye, Info } from 'lucide-react';
import { clsx } from 'clsx';

interface ExtractionOptionsProps {
  options: {
    use_llm_final_json: boolean;
    use_vision_dimensions: boolean;
    llm_final_model: string;
    vision_model: string;
  };
  setOptions: (options: any) => void;
  disabled?: boolean;
}

export default function ExtractionOptions({ options, setOptions, disabled }: ExtractionOptionsProps) {
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);

  const toggleOption = (key: string) => {
    if (disabled) return;
    setOptions((prev: any) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSelectChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const { name, value } = e.target;
    setOptions((prev: any) => ({ ...prev, [name]: value }));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-slate-700 font-semibold text-sm border-b border-slate-100 pb-2">
        <Settings className="w-4 h-4" />
        <span>Extraction Settings</span>
      </div>

      <div className="space-y-3">
        {/* LLM Toggle */}
        <div 
          onClick={() => toggleOption('use_llm_final_json')}
          className={clsx(
            "flex items-start gap-3 p-3 rounded-lg border transition-all cursor-pointer",
            options.use_llm_final_json 
              ? "bg-blue-50/30 border-blue-100" 
              : "bg-white border-slate-200 opacity-60 grayscale-[0.5]",
            disabled && "cursor-not-allowed opacity-50"
          )}
        >
          <div className={clsx(
            "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border",
            options.use_llm_final_json ? "bg-blue-100 border-blue-200 text-brand-accent" : "bg-slate-100 border-slate-200 text-slate-400"
          )}>
            <Cpu className="w-4 h-4" />
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-800">Use LLM Final JSON</span>
              <div className={clsx(
                "w-10 h-5 rounded-full relative transition-colors",
                options.use_llm_final_json ? "bg-brand-accent" : "bg-slate-200"
              )}>
                <div className={clsx(
                  "absolute top-1 w-3 h-3 bg-white rounded-full transition-all",
                  options.use_llm_final_json ? "left-6" : "left-1"
                )} />
              </div>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5 leading-tight">
              Generates the final form-ready JSON using Bedrock/Claude.
            </p>
          </div>
        </div>

        {/* Vision Toggle */}
        <div 
          onClick={() => toggleOption('use_vision_dimensions')}
          className={clsx(
            "flex items-start gap-3 p-3 rounded-lg border transition-all cursor-pointer",
            options.use_vision_dimensions 
              ? "bg-blue-50/30 border-blue-100" 
              : "bg-white border-slate-200 opacity-60 grayscale-[0.5]",
            disabled && "cursor-not-allowed opacity-50"
          )}
        >
          <div className={clsx(
            "w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border",
            options.use_vision_dimensions ? "bg-blue-100 border-blue-200 text-brand-accent" : "bg-slate-100 border-slate-200 text-slate-400"
          )}>
            <Eye className="w-4 h-4" />
          </div>
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-800">Use Vision Dimensions</span>
              <div className={clsx(
                "w-10 h-5 rounded-full relative transition-colors",
                options.use_vision_dimensions ? "bg-brand-accent" : "bg-slate-200"
              )}>
                <div className={clsx(
                  "absolute top-1 w-3 h-3 bg-white rounded-full transition-all",
                  options.use_vision_dimensions ? "left-6" : "left-1"
                )} />
              </div>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5 leading-tight">
              Adds separate visual dimension detection. Slower and optional.
            </p>
          </div>
        </div>
      </div>

      {/* Advanced Section */}
      <div className="pt-2">
        <button
          onClick={() => setIsAdvancedOpen(!isAdvancedOpen)}
          className="flex items-center justify-between w-full text-[11px] font-bold text-slate-400 uppercase tracking-widest hover:text-slate-600 transition-colors"
        >
          Advanced Options
          {isAdvancedOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </button>

        {isAdvancedOpen && (
          <div className="mt-3 space-y-4 p-4 rounded-xl bg-slate-50 border border-slate-200 animate-in slide-in-from-top-2 duration-200">
            <div>
              <div className="flex items-center gap-1.5 mb-1.5">
                <label className="text-[11px] font-semibold text-slate-600 uppercase">LLM Final Model</label>
                <div className="group relative">
                  <Info className="w-3 h-3 text-slate-300 cursor-help" />
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-2 bg-slate-800 text-white text-[10px] rounded opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                    Specify a custom model identifier for Bedrock (e.g. anthropic.claude-3-sonnet-20240229-v1:0)
                  </div>
                </div>
              </div>
              <select
                name="llm_final_model"
                value={options.llm_final_model}
                onChange={handleSelectChange}
                disabled={disabled}
                className="input text-sm py-1.5 h-9 appearance-none bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2020%2020%22%3E%3Cpath%20stroke%3D%22%236b7280%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20stroke-width%3D%221.5%22%20d%3D%22m6%208%204%204%204-4%22%2F%3E%3C%2Fsvg%3E')] bg-[position:right_0.5rem_center] bg-[size:1.5em_1.5em] bg-no-repeat pr-10"
              >
                <option value="">Default (Claude 3 Sonnet)</option>
                <option value="anthropic.claude-3-sonnet-20240229-v1:0">Claude 3 Sonnet</option>
                <option value="anthropic.claude-3-haiku-20240307-v1:0">Claude 3 Haiku</option>
                <option value="anthropic.claude-3-5-sonnet-20240620-v1:0">Claude 3.5 Sonnet</option>
              </select>
            </div>

            <div>
              <div className="flex items-center gap-1.5 mb-1.5">
                <label className="text-[11px] font-semibold text-slate-600 uppercase">Vision Model</label>
                <div className="group relative">
                  <Info className="w-3 h-3 text-slate-300 cursor-help" />
                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-2 bg-slate-800 text-white text-[10px] rounded opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                    Specify a custom vision model identifier.
                  </div>
                </div>
              </div>
              <select
                name="vision_model"
                value={options.vision_model}
                onChange={handleSelectChange}
                disabled={disabled}
                className="input text-sm py-1.5 h-9 appearance-none bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20fill%3D%22none%22%20viewBox%3D%220%200%2020%2020%22%3E%3Cpath%20stroke%3D%22%236b7280%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%20stroke-width%3D%221.5%22%20d%3D%22m6%208%204%204%204-4%22%2F%3E%3C%2Fsvg%3E')] bg-[position:right_0.5rem_center] bg-[size:1.5em_1.5em] bg-no-repeat pr-10"
              >
                <option value="">Default</option>
                <option value="amazon.titan-image-generator-v1">Titan Image Generator</option>
                <option value="anthropic.claude-3-sonnet-20240229-v1:0">Claude 3 Sonnet (Vision)</option>
              </select>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
