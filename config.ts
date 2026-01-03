/**
 * Application Configuration
 * Centralizes environment-dependent settings
 */

// Backend API configuration
export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  WS_URL: import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/frontend',
  TIMEOUT_MS: Number(import.meta.env.VITE_API_TIMEOUT_MS) || 45000, // Increased from 30s
  MAX_RETRIES: Number(import.meta.env.VITE_API_MAX_RETRIES) || 3,
  // Per-endpoint timeouts for slower operations
  TIMEOUTS: {
    profile: 45000,
    checklist: 45000,
    clinical: 60000,
    narrative: 90000,  // AI generation takes longer
  },
};

// Extension configuration
export const EXTENSION_CONFIG = {
  ID: import.meta.env.VITE_EXTENSION_ID || '',
  POLL_INTERVAL_MS: 1000,
  MAX_POLL_ATTEMPTS: 10,
  RECONNECT_DELAY_MS: 2000,
  MAX_RECONNECT_ATTEMPTS: 5,
};

// Logging configuration
export const LOG_CONFIG = {
  // Set to 'verbose' for debugging, 'normal' for production
  LEVEL: (import.meta.env.VITE_LOG_LEVEL as string) || 'normal',
  // Only log these message types in normal mode
  NORMAL_TYPES: ['error', 'warn', 'success', 'patient'],
};

// Request deduplication settings
export const DEDUP_CONFIG = {
  WINDOW_MS: 500, // Ignore duplicate requests within this window
};

/**
 * Generate a unique request ID for tracking
 */
export const generateRequestId = (): string => {
  return `req_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
};
