import express from 'express';
import { query } from '../db.js';
import { clamp, num, parseBool, rowToEvent, text } from '../utils.js';

const router = express.Router();

function animalWhere(animalFilter, params) {
  if (!animalFilter || animalFilter === 'all') return '';
  params.push(animalFilter);
  const idx = params.length;
  return `AND (LOWER(animal_group) = LOWER($${idx}) OR LOWER(species) LIKE LOWER('%' || $${idx} || '%'))`;
}

router.get('/', async (req, res, next) => {
  try {
    const lat = num(req.query.lat, null);
    const lon = num(req.query.lon, null);
    if (lat === null || lon === null) return res.status(400).json({ error: 'lat_lon_required' });

    const radiusKm = clamp(num(req.query.radius_km, num(req.query.radius, Number(process.env.DEFAULT_RADIUS_KM || 50))), 1, Number(process.env.MAX_RADIUS_KM || 250));
    const days = clamp(num(req.query.days, Number(process.env.DEFAULT_DAYS || 180)), 1, Number(process.env.MAX_DAYS || 730));
    const animalFilter = text(req.query.animal_filter || req.query.animalFilter, 'all');
    const includeOfficial = parseBool(req.query.include_official, true);
    const includeUser = parseBool(req.query.include_user, true);
    const limit = clamp(num(req.query.limit, Number(process.env.MAX_RESULTS || 1000)), 1, Number(process.env.MAX_RESULTS || 1000));

    const params = [lon, lat, radiusKm * 1000, days, limit];
    let sourceClause = '';
    if (!includeOfficial || !includeUser) {
      if (includeOfficial && !includeUser) sourceClause = "AND COALESCE(source_type,'') <> 'user'";
      if (!includeOfficial && includeUser) sourceClause = "AND COALESCE(source_type,'') = 'user'";
    }
    const animalClause = animalWhere(animalFilter, params);

    const { rows } = await query(
      `SELECT *,
              ST_Distance(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) / 1000 AS distance_km
       FROM events
       WHERE geom IS NOT NULL
         AND ST_DWithin(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3)
         AND (observation_date IS NULL OR observation_date >= CURRENT_DATE - ($4::int * INTERVAL '1 day'))
         ${sourceClause}
         ${animalClause}
       ORDER BY observation_date DESC NULLS LAST, distance_km ASC
       LIMIT $5`,
      params
    );

    res.json({
      query: { lat, lon, radius_km: radiusKm, days, animal_filter: animalFilter },
      events: rows.map(rowToEvent)
    });
  } catch (err) {
    next(err);
  }
});

export default router;
