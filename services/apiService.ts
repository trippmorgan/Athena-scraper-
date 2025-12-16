import { NarrativeResponse } from '../types';

const API_BASE_URL = 'http://localhost:8000';

/**
 * Fetches the AI-generated narrative summary from the backend service.
 * @param patientId The ID of the patient to generate the narrative for.
 * @param includeVision Whether to include vision processing of artifacts.
 * @returns A promise that resolves to the NarrativeResponse.
 */
export const fetchNarrative = async (
  patientId: string, 
  includeVision: boolean = false
): Promise<NarrativeResponse> => {
  try {
    const response = await fetch(`${API_BASE_URL}/ai/narrative/${patientId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ include_vision: includeVision }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ error: 'Network response was not ok and failed to parse error body.' }));
      console.error('Error fetching narrative:', errorData);
      throw new Error(errorData.error || 'Failed to fetch narrative');
    }

    const data: NarrativeResponse = await response.json();
    return data;
  } catch (error) {
    console.error('An unexpected error occurred while fetching the narrative:', error);
    // Return a mock error response to ensure the UI can handle it gracefully
    return {
      narrative: `Failed to generate narrative. Please ensure the backend is running and a patient is selected. 

Error: ${error instanceof Error ? error.message : 'Unknown Error'}`,
      sources_used: [],
      confidence: 'none',
      generated_at: new Date().toISOString(),
    };
  }
};
