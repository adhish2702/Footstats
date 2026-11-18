import type { ErrorRequestHandler, RequestHandler } from "express";

export interface ErrorDetail {
  param: string;
  message: string;
}

/** An error with an HTTP status that is safe to show to the client. */
export class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly details?: ErrorDetail[],
  ) {
    super(message);
  }
}

export const notFound: RequestHandler = (req, _res, next) => {
  next(new HttpError(404, `Not found: ${req.method} ${req.path}`));
};

/** Every error leaves as {"error": {"status", "message", "details"?}}. */
export const errorHandler: ErrorRequestHandler = (err, _req, res, _next) => {
  if (err instanceof HttpError) {
    res.status(err.status).json({
      error: { status: err.status, message: err.message, ...(err.details && { details: err.details }) },
    });
    return;
  }
  // Anything else is a bug or a database problem: log it, but don't leak it.
  console.error(err);
  res.status(500).json({ error: { status: 500, message: "Internal server error" } });
};
