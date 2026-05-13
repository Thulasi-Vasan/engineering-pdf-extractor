/**
 * API Utility for Engineering PDF Extractor Backend
 */

export const BASE_URL = 'http://127.0.0.1:8000';

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
  final_json: string;
  report: string;
}

export interface ExtractionResponse {
  run_id: string;
  status: 'success' | 'failed' | 'partial_success';
  final_json: Record<string, unknown>;
  artifacts: Artifacts;
  warnings: string[];
  error?: string;
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
   * Helper to get full artifact URL
   */
  getArtifactUrl(path: string): string {
    if (path.startsWith('http')) return path;
    return `${BASE_URL}${path.startsWith('/') ? '' : '/'}${path}`;
  }
};
