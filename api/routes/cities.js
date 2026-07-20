import express from 'express';
import { query } from '../db.js';

const router = express.Router();

router.get('/', async (req, res, next) => {
  try {
    const { rows } = await query(
      `SELECT name, region, province, country, lat, lon
       FROM cities
       ORDER BY country, region NULLS LAST, name`
    );
    res.json({ cities: rows.map(r => ({ ...r, lat: Number(r.lat), lon: Number(r.lon) })) });
  } catch (err) {
    next(err);
  }
});

export default router;
