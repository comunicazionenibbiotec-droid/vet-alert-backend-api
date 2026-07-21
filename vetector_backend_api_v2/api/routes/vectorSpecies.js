import express from 'express';
import { query } from '../db.js';
import { clamp, num, text } from '../utils.js';

const router = express.Router();

router.get('/', async (req, res, next) => {
  try {
    const focus = text(req.query.focus, 'all').toLowerCase();
    const group = text(req.query.group || req.query.common_group, 'all').toLowerCase();
    const leishOnly = ['1', 'true', 'yes'].includes(String(req.query.leishmaniasis || req.query.leish_only || '').toLowerCase());
    const limit = clamp(num(req.query.limit, 200), 1, 1000);

    const params = [limit];
    const where = [];
    if (focus && focus !== 'all') {
      params.push(`%${focus}%`);
      where.push(`LOWER(COALESCE(pathogen_focus,'')) LIKE $${params.length}`);
    }
    if (group && group !== 'all') {
      params.push(group);
      where.push(`LOWER(COALESCE(common_group,'')) = $${params.length}`);
    }
    if (leishOnly) {
      where.push(`is_leishmaniasis_vector = TRUE`);
    }
    const whereSql = where.length ? `WHERE ${where.join(' AND ')}` : '';

    const { rows } = await query(
      `SELECT id, scientific_name, common_group, pathogen_focus,
              is_leishmaniasis_vector, vector_status, priority,
              notes, source, source_url, updated_at
       FROM vector_species_catalog
       ${whereSql}
       ORDER BY priority ASC, scientific_name ASC
       LIMIT $1`,
      params
    );

    res.json({
      query: { focus, group, leishmaniasis: leishOnly, limit },
      species: rows
    });
  } catch (err) {
    next(err);
  }
});

export default router;
