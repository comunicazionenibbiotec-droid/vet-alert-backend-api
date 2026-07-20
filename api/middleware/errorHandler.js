export function notFound(req, res) {
  res.status(404).json({ error: 'not_found', path: req.originalUrl });
}

export function errorHandler(err, req, res, next) {
  console.error('[api-error]', err);
  const status = err.status || 500;
  res.status(status).json({
    error: status === 500 ? 'internal_server_error' : 'request_error',
    message: process.env.NODE_ENV === 'production' && status === 500 ? 'Unexpected server error' : err.message
  });
}
