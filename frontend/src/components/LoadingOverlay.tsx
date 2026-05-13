import { useState, useEffect } from 'react';
import { 
  FileUp, 
  Search, 
  Database, 
  Binary, 
  BrainCircuit, 
  FileJson,
  Clock,
  Loader2,
  CheckCircle2
} from 'lucide-react';
import { clsx } from 'clsx';

const STEPS = [
  { id: 'uploading', label: 'Uploading PDF', icon: FileUp },
  { id: 'detection', label: 'Running page detection', icon: Search },
  { id: 'extraction', label: 'Extracting raw text/tables/vectors', icon: Database },
  { id: 'structured', label: 'Building structured engineering data', icon: Binary },
  { id: 'llm', label: 'Generating final LLM JSON', icon: BrainCircuit },
  { id: 'preparing', label: 'Preparing output', icon: FileJson },
];

export default function LoadingOverlay() {
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [elapsedTime, setElapsedTime] = useState(0);

  useEffect(() => {
    // Timer for elapsed seconds
    const timer = setInterval(() => {
      setElapsedTime(prev => prev + 1);
    }, 1000);

    // Simulate progress through steps
    // Since backend is synchronous, we just move forward every few seconds
    const stepInterval = setInterval(() => {
      setCurrentStepIndex(prev => {
        if (prev < STEPS.length - 1) return prev + 1;
        return prev; // Stay at last step if not done
      });
    }, 4500); // Average time per step for simulation

    return () => {
      clearInterval(timer);
      clearInterval(stepInterval);
    };
  }, []);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="absolute inset-0 bg-white/90 backdrop-blur-sm z-20 flex flex-col items-center justify-center p-8 rounded-xl animate-in fade-in duration-500">
      <div className="w-full max-w-md space-y-8">
        {/* Timer Display */}
        <div className="flex flex-col items-center text-center space-y-2">
          <div className="flex items-center gap-2 px-4 py-2 bg-slate-100 rounded-full text-slate-600 font-mono text-sm border border-slate-200">
            <Clock className="w-4 h-4 text-brand-accent animate-pulse" />
            <span>Elapsed: {formatTime(elapsedTime)}</span>
          </div>
          <h3 className="text-xl font-bold text-slate-800">Processing Document</h3>
          <p className="text-sm text-slate-500">This may take a minute for complex drawings</p>
        </div>

        {/* Step List */}
        <div className="space-y-4">
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            const isCompleted = index < currentStepIndex;
            const isActive = index === currentStepIndex;
            
            return (
              <div 
                key={step.id}
                className={clsx(
                  "flex items-center gap-4 p-3 rounded-xl transition-all duration-300",
                  isActive ? "bg-blue-50 border border-blue-100 scale-[1.02] shadow-sm" : "bg-transparent",
                  isCompleted ? "opacity-100" : (isActive ? "opacity-100" : "opacity-30")
                )}
              >
                <div className={clsx(
                  "w-10 h-10 rounded-lg flex items-center justify-center shrink-0 border transition-all",
                  isCompleted ? "bg-emerald-50 border-emerald-100 text-emerald-500" : 
                  (isActive ? "bg-white border-brand-accent text-brand-accent shadow-sm" : "bg-slate-50 border-slate-100 text-slate-400")
                )}>
                  {isCompleted ? <CheckCircle2 className="w-5 h-5" /> : (isActive ? <Loader2 className="w-5 h-5 animate-spin" /> : <Icon className="w-5 h-5" />)}
                </div>
                
                <div className="flex-1">
                  <p className={clsx(
                    "text-sm font-semibold transition-colors",
                    isCompleted ? "text-slate-500" : (isActive ? "text-brand-primary" : "text-slate-400")
                  )}>
                    {step.label}
                  </p>
                  {isActive && (
                    <div className="w-full bg-slate-200 h-1 rounded-full mt-2 overflow-hidden">
                      <div className="h-full bg-brand-accent animate-[loading-bar_4s_infinite]" />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="text-center">
          <p className="text-[10px] text-slate-400 uppercase tracking-[0.2em] font-bold">
            Powered by Deep Drawing AI
          </p>
        </div>
      </div>

      <style>{`
        @keyframes loading-bar {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
      `}</style>
    </div>
  );
}
