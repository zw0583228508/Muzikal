/**
 * Shared validation utilities for Express routes.
 *
 * All route parameter parsing must go through these helpers.
 * Never allow NaN or unvalidated values into DB queries.
 */

import type { Request, Response } from "express";

/**
 * Parse and validate an integer route parameter.
 * Sends a 400 response and returns null if invalid.
 */
export function parseIntParam(
  req: Request,
  res: Response,
  paramName: string,
  options: { min?: number; max?: number } = {},
): number | null {
  const raw = req.params[paramName];
  if (!raw) {
    res.status(400).json({ error: `Missing parameter: ${paramName}` });
    return null;
  }

  const parsed = parseInt(raw, 10);
  if (isNaN(parsed)) {
    res.status(400).json({ error: `Invalid parameter '${paramName}': must be an integer, got '${raw}'` });
    return null;
  }

  if (options.min !== undefined && parsed < options.min) {
    res.status(400).json({ error: `Parameter '${paramName}' must be >= ${options.min}, got ${parsed}` });
    return null;
  }

  if (options.max !== undefined && parsed > options.max) {
    res.status(400).json({ error: `Parameter '${paramName}' must be <= ${options.max}, got ${parsed}` });
    return null;
  }

  return parsed;
}

/**
 * Parse and validate a project ID from req.params.id.
 * Sends 400 if invalid. Returns null on failure.
 */
export function parseProjectId(req: Request, res: Response): number | null {
  return parseIntParam(req, res, "id", { min: 1 });
}

/**
 * Assert that a required body field is present.
 * Returns the value or sends 400 + returns undefined.
 */
export function requireField<T>(
  res: Response,
  body: Record<string, unknown>,
  field: string,
): T | undefined {
  if (body[field] === undefined || body[field] === null || body[field] === "") {
    res.status(400).json({ error: `Missing required field: ${field}` });
    return undefined;
  }
  return body[field] as T;
}
