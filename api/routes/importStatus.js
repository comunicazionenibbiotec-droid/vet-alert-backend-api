import express from 'express';
import { query } from '../db.js';
import { clamp, num } from '../utils.js';

const router = express.Router();

router.get('/', async (req, res, next) => {
  try {
    const limit = clamp(num(req.query.limit, 30), 1, 200);
    const { rows } = await query(
      `SELECT r.id, r.source_id, s.name AS source_name, r.status, r.started_at,
              r.finished_at, r.records_fetched, r.records_inserted,
              r.records_updated, r.error_message, r.metadata
       FROM data_import_runs r
       LEFT JOIN data_sources s ON s.id = r.source_id
       ORDER BY r.started_at DESC
       LIMIT $1`,
      [limit]
    );

    const sources = await query(
      `SELECT id, name, source_type, url, update_frequency, ingestion_mode,
              enabled, priority, notes, updated_at
       FROM data_sources
       ORDER BY priority ASC, id ASC`
    );

    res.json({ sources: sources.rows, runs: rows });
  } catch (err) {
    next(err);
  }
});

export default router;
