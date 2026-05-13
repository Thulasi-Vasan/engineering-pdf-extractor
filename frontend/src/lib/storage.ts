/**
 * LocalStorage Utility for Recent Extractions
 */

import type { ExtractionResponse } from './api.ts';

export interface SavedRun {
  id: string;
  timestamp: number;
  fileName: string;
  fileSize: number;
  status: 'success' | 'failed' | 'partial_success';
  response?: ExtractionResponse;
}

const STORAGE_KEY = 'engineering_pdf_runs';
const MAX_RUNS = 20;

export const storage = {
  /**
   * Save a run to history
   */
  saveRun(run: SavedRun): void {
    const runs = this.getRuns();
    const updatedRuns = [run, ...runs].slice(0, MAX_RUNS);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedRuns));
  },

  /**
   * Get all runs from history
   */
  getRuns(): SavedRun[] {
    const data = localStorage.getItem(STORAGE_KEY);
    if (!data) return [];
    try {
      return JSON.parse(data);
    } catch (e) {
      console.error('Failed to parse history:', e);
      return [];
    }
  },

  /**
   * Clear all history
   */
  clearHistory(): void {
    localStorage.removeItem(STORAGE_KEY);
  }
};
