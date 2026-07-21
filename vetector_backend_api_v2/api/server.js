import 'dotenv/config';
import cors from 'cors';
import express from 'express';
import helmet from 'helmet';
import morgan from 'morgan';

import { query } from './db.js';
import { errorHandler, notFound } from './middleware/errorHandler.js';
import citiesRouter from './routes/cities.js';
import eventsRouter from './routes/events.js';
import importStatusRouter from './routes/importStatus.js';
import territorialLayersRouter from './routes/territorialLayers.js';
import vectorOccurrencesRouter from './routes/vectorOccurrences.js';
import vectorSpeciesRouter from './routes/vectorSpecies.js';


const app = express();
const port = Number(process.env.PORT || 3000);

const allowedOrigins = (process.env.CORS_ORIGIN || '*')
  .split(',')
  .map(s => s.trim())
  .filter(Boolean);

app.use(helmet({ crossOriginResourcePolicy: false }));
app.use(cors({
  origin(origin, callback) {
    if (!origin || allowedOrigins.includes('*') || allowedOrigins.includes(origin)) return callback(null, true);
    return callback(new Error(`CORS origin not allowed: ${origin}`));
  }
}));
app.use(express.json({ limit: '2mb' }));
app.use(morgan(process.env.NODE_ENV === 'production' ? 'combined' : 'dev'));

app.get('/health', async (req, res, next) => {
  try {
    const result = await query('SELECT NOW() AS now');
    res.json({ ok: true, name: 'vetector-backend-api-v2', db_time: result.rows[0].now });
  } catch (err) {
    next(err);
  }
});

app.use('/cities', citiesRouter);
app.use('/events', eventsRouter);
app.use('/territorial-layers', territorialLayersRouter);
app.use('/import/status', importStatusRouter);
app.use('/vector-occurrences', vectorOccurrencesRouter);
app.use('/vector-species', vectorSpeciesRouter);

app.use(notFound);
app.use(errorHandler);

app.listen(port, () => {
  console.log(`[vetector-api] listening on port ${port}`);
});
