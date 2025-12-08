import { GoogleGenAI } from "@google/genai";
import { Patient, AgentOutput } from '../types';

// Initialize the client
// NOTE: We assume process.env.API_KEY is available. 
// If running locally without env vars, one might need to handle this gracefully in a real app.
const ai = new GoogleGenAI({ apiKey: process.env.API_KEY || '' });

const MODEL_NAME = 'gemini-2.5-flash';

export const generateAgentResponse = async (
  agentName: string,
  systemInstruction: string,
  patientData: Patient
): Promise<AgentOutput> => {
  
  if (!process.env.API_KEY) {
    // Fallback for demo without key
    return {
      agentName,
      status: 'complete',
      content: "API Key missing. Please configure process.env.API_KEY to see live GenAI results. \n\n[Mock Output] based on patient data...",
      timestamp: new Date().toISOString(),
      modelUsed: 'mock-model'
    };
  }

  try {
    const prompt = `
      Analyze the following patient data JSON:
      ${JSON.stringify(patientData, null, 2)}
      
      Perform your task as defined in the system instructions. Keep it concise (under 150 words) unless asked otherwise.
    `;

    const response = await ai.models.generateContent({
      model: MODEL_NAME,
      contents: prompt,
      config: {
        systemInstruction: systemInstruction,
        temperature: 0.2, // Low temp for medical accuracy
        maxOutputTokens: 500,
      }
    });

    return {
      agentName,
      status: 'complete',
      content: response.text || "No response generated.",
      timestamp: new Date().toISOString(),
      modelUsed: MODEL_NAME
    };

  } catch (error) {
    console.error(`Error in ${agentName}:`, error);
    return {
      agentName,
      status: 'idle',
      content: `Error generating content: ${(error as Error).message}`,
      timestamp: new Date().toISOString(),
      modelUsed: MODEL_NAME
    };
  }
};