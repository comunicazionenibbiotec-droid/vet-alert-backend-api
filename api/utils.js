export function num(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function text(value, fallback = '') {
  if (value === undefined || value === null) return fallback;
  return String(value).trim();
}

export function parseBool(value, fallback = false) {
  if (value === undefined || value === null || value === '') return fallback;
  return ['1', 'true', 'yes', 'y'].includes(String(value).toLowerCase());
}

export function normalizeDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  return String(value).slice(0, 10);
}

export function rowToEvent(row) {
  return {
    id: row.id,
    external_id: row.id,
    disease: row.disease,
    disease_original: row.disease,
    species: row.species,
    animal_group: row.animal_group,
    diagnosis_status: row.diagnosis_status,
    source: row.source,
    source_type: row.source_type,
    report_type: row.report_type,
    observation_date: normalizeDate(row.observation_date),
    report_date: normalizeDate(row.report_date),
    date: normalizeDate(row.observation_date || row.report_date),
    location: row.location,
    region: row.region,
    province: row.province,
    country: row.country,
    lat: row.lat == null ? null : Number(row.lat),
    lon: row.lon == null ? null : Number(row.lon),
    distance_km: row.distance_km == null ? null : Number(row.distance_km),
    risk_score: row.risk_score,
    confidence_label: row.confidence_label,
    url_source: row.url_source,
    display_source: row.source,
    display_status: row.diagnosis_status
  };
}

export function rowToLayer(row) {
  return {
    id: row.id,
    category: row.category,
    label: row.label,
    scientific_name: row.scientific_name,
    data_type: row.data_type,
    count: row.count,
    count_label: row.count_label,
    country: row.country,
    region: row.region,
    province: row.province,
    location: row.location,
    lat: Number(row.lat),
    lon: Number(row.lon),
    radius_km: Number(row.radius_km || 10),
    aggregation_level: row.aggregation_level,
    source: row.source,
    display_source: row.display_source || row.source,
    period_start: normalizeDate(row.period_start),
    period_end: normalizeDate(row.period_end),
    url_source: row.url_source,
    note: row.notes,
    notes: row.notes,
    distance_km: row.distance_km == null ? null : Number(row.distance_km)
  };
}
