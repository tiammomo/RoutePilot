import type { ArtifactHistoryResponse, LatestArtifactResponse } from '@/types';
import { API_PREFIX, apiClient } from './core';

class ArtifactClient {
  async getLatestArtifact(sessionId: string): Promise<LatestArtifactResponse> {
    const response = await apiClient.get(`${API_PREFIX}/artifacts/${sessionId}/latest`);
    return response.data;
  }

  async getArtifactHistory(sessionId: string, limit = 10): Promise<ArtifactHistoryResponse> {
    const response = await apiClient.get(`${API_PREFIX}/artifacts/${sessionId}/history`, {
      params: { limit },
    });
    return response.data;
  }
}

export const artifactClient = new ArtifactClient();
