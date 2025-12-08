import { LogEntry, Patient, ScraperMode } from '../types';

// Mock Data to simulate AthenaNet internal API responses
const FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer"];
const LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia"];
const CONDITIONS = ["Hypertension", "T2DM", "Hyperlipidemia", "Osteoarthritis", "GERD", "Atrial Fibrillation"];
const MEDS = ["Lisinopril 10mg", "Metformin 500mg", "Atorvastatin 20mg", "Omeprazole 40mg"];

const generateRandomPatient = (): Patient => {
  const fn = FIRST_NAMES[Math.floor(Math.random() * FIRST_NAMES.length)];
  const ln = LAST_NAMES[Math.floor(Math.random() * LAST_NAMES.length)];
  
  return {
    id: Math.floor(Math.random() * 100000).toString(),
    mrn: `MRN-${Math.floor(Math.random() * 1000000)}`,
    name: `${fn} ${ln}`,
    dob: '1975-04-12',
    gender: Math.random() > 0.5 ? 'M' : 'F',
    lastEncounter: new Date().toISOString().split('T')[0],
    conditions: [CONDITIONS[Math.floor(Math.random() * CONDITIONS.length)]],
    medications: [MEDS[Math.floor(Math.random() * MEDS.length)]],
    vitals: {
      bp: `${110 + Math.floor(Math.random() * 30)}/${70 + Math.floor(Math.random() * 20)}`,
      hr: 60 + Math.floor(Math.random() * 40),
      temp: 98.6,
      spo2: 95 + Math.floor(Math.random() * 5),
    },
    notes: "Patient presents with generalized fatigue and mild joint pain. Denies chest pain or SOB. adherence to medication is good."
  };
};

// Simulation of intercepted API calls
export const generateLogEntry = (mode: ScraperMode): LogEntry => {
  const endpoints = [
    '/chart/patient/summary',
    '/chart/patient/{id}/medications',
    '/chart/patient/{id}/labs',
    '/chart/encounter/note/v2'
  ];
  
  const isCrawl = mode === ScraperMode.ACTIVE;
  const method = isCrawl ? 'GET' : (Math.random() > 0.8 ? 'POST' : 'GET');
  
  return {
    id: Math.random().toString(36).substring(7),
    timestamp: new Date().toISOString(),
    method: method,
    endpoint: endpoints[Math.floor(Math.random() * endpoints.length)],
    status: 200,
    size: `${Math.floor(Math.random() * 5)}kb`,
    payload: { status: 'mock_payload', timestamp: Date.now() } 
  };
};

export const fetchMockPatient = async (): Promise<Patient> => {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve(generateRandomPatient());
    }, 800);
  });
};
