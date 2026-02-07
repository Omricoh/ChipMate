import apiClient from './client';
import type { ValidateTokenResponse } from './types';

/**
 * Validate the current session token (admin JWT or player token).
 * GET /api/auth/validate
 *
 * This is used to verify a stored session is still valid when the user
 * returns to the app after navigating away or refreshing.
 */
export async function validateSession(): Promise<ValidateTokenResponse> {
  const response = await apiClient.get<ValidateTokenResponse>(
    '/api/auth/validate',
  );
  return response.data;
}
