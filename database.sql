-- PostgreSQL schema used by Supabase and the Flask application.
-- The application creates missing tables and seeds initial rows on startup.

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
  id SERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL DEFAULT 'Administrator'
);

CREATE TABLE IF NOT EXISTS cars (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  car_type TEXT NOT NULL,
  seats INTEGER NOT NULL DEFAULT 4,
  price_per_km REAL NOT NULL DEFAULT 12,
  base_fare REAL NOT NULL DEFAULT 500,
  ac INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS bookings (
  id SERIAL PRIMARY KEY,
  customer_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  email TEXT,
  pickup_location TEXT NOT NULL,
  drop_location TEXT NOT NULL,
  pickup_date TEXT NOT NULL,
  pickup_time TEXT NOT NULL,
  return_date TEXT,
  trip_type TEXT NOT NULL DEFAULT 'one_way',
  car_id INTEGER REFERENCES cars(id) ON DELETE SET NULL,
  passengers INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reviews (
  id SERIAL PRIMARY KEY,
  customer_name TEXT NOT NULL,
  trip_route TEXT,
  rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
  message TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contact_messages (
  id SERIAL PRIMARY KEY,
  customer_name TEXT NOT NULL,
  phone TEXT NOT NULL,
  email TEXT,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS route_prices (
  id SERIAL PRIMARY KEY,
  route_name TEXT NOT NULL,
  pickup_city TEXT NOT NULL,
  drop_city TEXT NOT NULL,
  duration_text TEXT NOT NULL,
  distance_km INTEGER NOT NULL DEFAULT 0,
  price REAL NOT NULL DEFAULT 0,
  sort_order INTEGER NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1,
  image_url TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS bookings_pickup_date_idx ON bookings(pickup_date);
CREATE INDEX IF NOT EXISTS reviews_status_created_at_idx ON reviews(status, created_at DESC);
CREATE INDEX IF NOT EXISTS routes_active_order_idx ON route_prices(is_active, sort_order, id);
