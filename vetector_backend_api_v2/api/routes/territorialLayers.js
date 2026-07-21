import express from 'express';
import { query } from '../db.js';
import { clamp, num, rowToLayer, text } from '../utils.js';

const router = express.Router();

router.get('/', async (req, res, next) => {
  try {
    const lat = num(req.query.lat, null);
    const lon = num(req.query.lon, null);
    if (lat === null || lon === null) return res.status(400).json({ error: 'lat_lon_required' });

    const radiusKm = clamp(num(req.query.radius_km, num(req.query.radius, Number(process.env.DEFAULT_RADIUS_KM || 50))), 1, Number(process.env.MAX_RADIUS_KM || 250));
    const category = text(req.query.category, 'all');
    const species = text(req.query.species, 'all');
    const focus = text(req.query.focus, 'all').toLowerCase();
    const source = text(req.query.source, 'all').toLowerCase();
    const leishOnly = ['1', 'true', 'yes'].includes(String(req.query.leishmaniasis || req.query.leish_only || '').toLowerCase());
    const limit = clamp(num(req.query.limit, Number(process.env.MAX_RESULTS || 1000)), 1, Number(process.env.MAX_RESULTS || 1000));

    const params = [lon, lat, radiusKm * 1000];
    const where = [
      `geom IS NOT NULL`,
      `ST_DWithin(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3)`
    ];

    if (category && category !== 'all') {
      params.push(category);
      where.push(`category = $${params.length}`);
    }
    if (species && species !== 'all') {
      params.push(species);
      where.push(`LOWER(COALESCE(scientific_name,label,'')) = LOWER($${params.length})`);
    }
    if (focus && focus !== 'all') {
      params.push(`%${focus}%`);
      where.push(`LOWER(COALESCE(data_type,'') || ' ' || COALESCE(notes,'') || ' ' || COALESCE(label,'') || ' ' || COALESCE(scientific_name,'')) LIKE $${params.length}`);
    }
    if (source && source !== 'all') {
      params.push(`%${source}%`);
      where.push(`LOWER(COALESCE(source,'') || ' ' || COALESCE(display_source,'')) LIKE $${params.length}`);
    }
    if (leishOnly) {
      where.push(`LOWER(COALESCE(data_type,'') || ' ' || COALESCE(notes,'') || ' ' || COALESCE(label,'') || ' ' || COALESCE(scientific_name,'')) LIKE '%leish%'`);
    }

    params.push(limit);
    const limitIdx = params.length;

    const { rows } = await query(
      `SELECT *,
              ST_Distance(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) / 1000 AS distance_km
       FROM territorial_layers
       WHERE ${where.join(' AND ')}
       ORDER BY category, distance_km ASC, period_start DESC NULLS LAST
       LIMIT $${limitIdx}`,
      params
    );

    res.json({
      query: { lat, lon, radius_km: radiusKm, category, species, focus, source, leishmaniasis: leishOnly, limit },
      layers: rows.map(rowToLayer)
    });
  } catch (err) {
    next(err);
  }
});

export default router;
