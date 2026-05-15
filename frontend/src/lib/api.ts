/**
 * API Utility for Engineering PDF Extractor Backend
 */

export const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export interface ExtractionRequest {
  file: File;
  use_llm_final_json: boolean;
  use_vision_dimensions: boolean;
  llm_final_model?: string;
  vision_model?: string;
}

export interface Artifacts {
  page_detection: string;
  raw_extraction: string;
  structured_data: string;
  final_json: string | null;
  report: string;
}

export interface ExtractionResponse {
  run_id: string;
  status: 'success' | 'failed' | 'partial_success';
  final_json: Record<string, unknown> | null;
  artifacts: Artifacts;
  warnings: string[];
  error?: string;
}

export interface ChatCitation {
  section: string;
  target_id: string;
  label: string;
  value: unknown;
  page: number | null;
  region_id: string;
  confidence: string;
  evidence: string;
  warnings: string[];
}

export interface ChatMatch {
  section: string;
  target_id: string;
  score: number;
  record: Record<string, unknown>;
  citation: ChatCitation;
}

export interface ChatResponse {
  run_id: string;
  question: string;
  answer: string;
  matches: ChatMatch[];
  citations: ChatCitation[];
  needs_clarification: boolean;
  clarification_question: string | null;
  warnings: string[];
}

export const api = {
  /**
   * Check backend health
   */
  async checkHealth(): Promise<boolean> {
    try {
      const response = await fetch(`${BASE_URL}/health`);
      return response.ok;
    } catch (error) {
      console.error('Health check failed:', error);
      return false;
    }
  },

  /**
   * Run extraction
   */
  async extract(data: ExtractionRequest): Promise<ExtractionResponse> {
    const formData = new FormData();
    formData.append('file', data.file);
    formData.append('use_llm_final_json', String(data.use_llm_final_json));
    formData.append('use_vision_dimensions', String(data.use_vision_dimensions));
    
    if (data.llm_final_model) {
      formData.append('llm_final_model', data.llm_final_model);
    }
    if (data.vision_model) {
      formData.append('vision_model', data.vision_model);
    }

    const response = await fetch(`${BASE_URL}/extract`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Extraction failed');
    }

    return response.json();
  },

  /**
   * Ask a grounded question against a run's final JSON
   */
  async chat(runId: string, question: string): Promise<ChatResponse> {
    const response = await fetch(`${BASE_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ run_id: runId, question }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || 'Chat request failed');
    }

    return response.json();
  },

  /**
   * Helper to get full artifact URL
   */
  getArtifactUrl(path: string): string {
    if (path.startsWith('http')) return path;
    return `${BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`;
  }
};
