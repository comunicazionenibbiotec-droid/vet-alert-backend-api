import express from 'express';
import { query } from '../db.js';
import { clamp, num, text } from '../utils.js';

const router = express.Router();

function rowToOccurrence(row) {
  return {
    id: row.id,
    scientific_name: row.scientific_name,
    common_group: row.common_group,
    pathogen_focus: row.pathogen_focus,
    occurrence_status: row.occurrence_status,
    event_date: row.event_date ? String(row.event_date).slice(0, 10) : null,
    year: row.year,
    country: row.country,
    region: row.region,
    province: row.province,
    municipality: row.municipality,
    locality: row.locality,
    lat: row.lat == null ? null : Number(row.lat),
    lon: row.lon == null ? null : Number(row.lon),
    distance_km: row.distance_km == null ? null : Number(row.distance_km),
    coordinate_uncertainty_m: row.coordinate_uncertainty_m == null ? null : Number(row.coordinate_uncertainty_m),
    source: row.source,
    source_dataset: row.source_dataset,
    source_url: row.source_url,
    license: row.license,
    confidence_score: row.confidence_score
  };
}

router.get('/', async (req, res, next) => {
  try {
    const lat = num(req.query.lat, null);
    const lon = num(req.query.lon, null);
    const radiusKm = clamp(num(req.query.radius_km, num(req.query.radius, Number(process.env.DEFAULT_RADIUS_KM || 50))), 1, Number(process.env.MAX_RADIUS_KM || 250));
    const species = text(req.query.species, 'all');
    const focus = text(req.query.focus, 'all').toLowerCase();
    const group = text(req.query.group || req.query.common_group, 'all').toLowerCase();
    const leishOnly = ['1', 'true', 'yes'].includes(String(req.query.leishmaniasis || req.query.leish_only || '').toLowerCase());
    const limit = clamp(num(req.query.limit, 1000), 1, Number(process.env.MAX_RESULTS || 1000));

    const params = [];
    const where = ['lat IS NOT NULL', 'lon IS NOT NULL', 'geom IS NOT NULL'];
    let selectDistance = 'NULL::double precision AS distance_km';
    let orderSql = 'ORDER BY event_date DESC NULLS LAST, year DESC NULLS LAST';

    if (lat !== null && lon !== null) {
      params.push(lon, lat, radiusKm * 1000);
      where.push(`ST_DWithin(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, $3)`);
      selectDistance = `ST_Distance(geom, ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography) / 1000 AS distance_km`;
      orderSql = 'ORDER BY distance_km ASC, event_date DESC NULLS LAST, year DESC NULLS LAST';
    }

    if (species && species !== 'all') {
      params.push(species);
      where.push(`LOWER(scientific_name) = LOWER($${params.length})`);
    }
    if (focus && focus !== 'all') {
      params.push(`%${focus}%`);
      where.push(`LOWER(COALESCE(pathogen_focus,'')) LIKE $${params.length}`);
    }
    if (group && group !== 'all') {
      params.push(group);
      where.push(`LOWER(COALESCE(common_group,'')) = $${params.length}`);
    }
    if (leishOnly) {
      where.push(`COALESCE(pathogen_focus,'') ILIKE '%leish%'`);
    }
    params.push(limit);
    const limitIdx = params.length;

    const { rows } = await query(
      `SELECT id, scientific_name, common_group, pathogen_focus, occurrence_status,
              event_date, year, country, region, province, municipality, locality,
              lat, lon, coordinate_uncertainty_m, source, source_dataset,
              source_url, license, confidence_score,
              ${selectDistance}
       FROM vector_occurrences
       WHERE ${where.join(' AND ')}
       ${orderSql}
       LIMIT $${limitIdx}`,
      params
    );

    res.json({
      query: { lat, lon, radius_km: radiusKm, species, focus, group, leishmaniasis: leishOnly, limit },
      occurrences: rows.map(rowToOccurrence)
    });
  } catch (err) {
    next(err);
  }
});

export default router;
