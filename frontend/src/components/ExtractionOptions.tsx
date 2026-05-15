import { Settings, Cpu, Eye } from 'lucide-react';
import { clsx } from 'clsx';

interface ExtractionOptionsProps {
  options: {
    use_llm_final_json: boolean;
    use_vision_dimensions: boolean;
    llm_final_model: string;
    vision_model: string;
  };
  setOptions: (updater: (prev: ExtractionOptionsProps['options']) => ExtractionOptionsProps['options']) => void;
  disabled?: boolean;
}

export default function ExtractionOptions({ options, setOptions, disabled }: ExtractionOptionsProps) {
  const toggleOption = (key: string) => {
    if (disabled) return;
    setOptions((prev) => ({ ...prev, [key]: !prev[key as keyof typeof prev] }));
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
    </div>
  );
}
