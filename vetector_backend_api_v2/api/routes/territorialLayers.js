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
    const limit = clamp(num(req.query.limit, Number(process.env.MAX_RESULTS || 1000)), 1, Number(process.env.MAX_RESULTS || 1000));

    const params = [lon, lat, radiusKm * 1000, limit];
    let categoryClause = '';
    if (category && category !== 'all') {
      params.push(category);
      categoryClause = `AND category = $${params.length}`;
    }

    const { rows } = await query(
      `SELECT *,
              ST_Distance(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) / 1000 AS distance_km
       FROM territorial_layers
       WHERE geom IS NOT NULL
         AND ST_DWithin(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3)
         ${categoryClause}
       ORDER BY category, distance_km ASC, period_start DESC NULLS LAST
       LIMIT $4`,
      params
    );

    res.json({
      query: { lat, lon, radius_km: radiusKm, category },
      layers: rows.map(rowToLayer)
    });
  } catch (err) {
    next(err);
  }
});

export default router;
