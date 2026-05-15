CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS japan_listings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id VARCHAR(100),
    source_platform VARCHAR(50) NOT NULL,
    url TEXT,
    make VARCHAR(80),
    model VARCHAR(100),
    grade VARCHAR(100),
    year INTEGER,
    mileage_km INTEGER,
    engine_size_cc INTEGER,
    fuel_type VARCHAR(30),
    transmission VARCHAR(30),
    body_type VARCHAR(50),
    drive_type VARCHAR(20),
    color VARCHAR(50),
    doors INTEGER,
    seats INTEGER,
    steering VARCHAR(10) DEFAULT 'RHD',
    price_jpy NUMERIC(12,2),
    price_usd NUMERIC(12,2),
    price_kes NUMERIC(16,2),
    fob_port VARCHAR(50),
    auction_grade VARCHAR(10),
    chassis_number VARCHAR(50),
    specs JSONB,
    images JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_platform, url)
);

CREATE TABLE IF NOT EXISTS local_listings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source VARCHAR(80),
    url TEXT,
    make VARCHAR(80),
    model VARCHAR(100),
    year INTEGER,
    mileage_km INTEGER,
    engine_size_cc INTEGER,
    fuel_type VARCHAR(30),
    transmission VARCHAR(30),
    body_type VARCHAR(50),
    color VARCHAR(50),
    price_kes NUMERIC(16,2),
    location VARCHAR(100),
    condition VARCHAR(30),
    is_active BOOLEAN DEFAULT TRUE,
    scraped_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS import_cost_params (
    id SERIAL PRIMARY KEY,
    param_key VARCHAR(100) UNIQUE NOT NULL,
    param_value NUMERIC(18,6),
    param_text VARCHAR(500),
    description TEXT,
    effective_from DATE DEFAULT CURRENT_DATE,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS import_cost_estimates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    listing_id UUID REFERENCES japan_listings(id) ON DELETE SET NULL,
    make VARCHAR(80),
    model VARCHAR(100),
    year INTEGER,
    engine_size_cc INTEGER,
    price_usd NUMERIC(12,2),
    shipping_usd NUMERIC(12,2),
    customs_value_usd NUMERIC(12,2),
    import_duty_kes NUMERIC(16,2),
    excise_duty_kes NUMERIC(16,2),
    vat_kes NUMERIC(16,2),
    idf_kes NUMERIC(16,2),
    rdl_kes NUMERIC(16,2),
    port_charges_kes NUMERIC(16,2),
    clearing_fees_kes NUMERIC(16,2),
    ntsa_registration_kes NUMERIC(16,2),
    inspection_kes NUMERIC(16,2),
    total_landed_kes NUMERIC(16,2),
    exchange_rate_usd_kes NUMERIC(10,4),
    calculated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ml_predictions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    make VARCHAR(80),
    model VARCHAR(100),
    year INTEGER,
    mileage_km INTEGER,
    engine_size_cc INTEGER,
    fuel_type VARCHAR(30),
    transmission VARCHAR(30),
    body_type VARCHAR(50),
    source_platform VARCHAR(50),
    predicted_price_usd NUMERIC(12,2),
    prediction_lower_usd NUMERIC(12,2),
    prediction_upper_usd NUMERIC(12,2),
    model_version VARCHAR(50),
    predicted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS scrape_logs (
    id SERIAL PRIMARY KEY,
    platform VARCHAR(50),
    run_type VARCHAR(30),
    status VARCHAR(20),
    records_fetched INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    duration_seconds NUMERIC(10,2),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

INSERT INTO import_cost_params (param_key, param_value, param_text, description) VALUES
('import_duty_rate',          0.35,    NULL,       'Import duty rate on customs value (CIF) — 35%'),
('excise_duty_0_1000cc',      0.10,    NULL,       'Excise duty for engine <= 1000cc — 10%'),
('excise_duty_1001_2000cc',   0.20,    NULL,       'Excise duty for engine 1001–2000cc — 20%'),
('excise_duty_2001_3000cc',   0.25,    NULL,       'Excise duty for engine 2001–3000cc — 25%'),
('excise_duty_above_3000cc',  0.35,    NULL,       'Excise duty for engine > 3000cc — 35%'),
('vat_rate',                  0.16,    NULL,       'Value Added Tax — 16%'),
('idf_rate',                  0.035,   NULL,       'Import Declaration Fee — 3.5% of customs value'),
('rdl_rate',                  0.02,    NULL,       'Railway Development Levy — 2%'),
('shipping_cost_usd',         1500,    NULL,       'Average shipping cost Japan to Mombasa (USD)'),
('port_charges_kes',          35000,   NULL,       'Port handling and storage charges (KES)'),
('clearing_fees_kes',         45000,   NULL,       'Clearing agent fees (KES)'),
('ntsa_registration_kes',     15000,   NULL,       'NTSA registration and plates (KES)'),
('inspection_fees_kes',       10000,   NULL,       'Pre-shipment and KEBS inspection (KES)'),
('crsp_depreciation_year1',   0.10,    NULL,       'CRSP depreciation year 1'),
('crsp_depreciation_year2',   0.20,    NULL,       'CRSP depreciation year 2'),
('crsp_depreciation_year3',   0.30,    NULL,       'CRSP depreciation year 3'),
('crsp_depreciation_year4',   0.40,    NULL,       'CRSP depreciation year 4'),
('crsp_depreciation_year5',   0.50,    NULL,       'CRSP depreciation year 5'),
('crsp_depreciation_year6',   0.55,    NULL,       'CRSP depreciation year 6'),
('crsp_depreciation_year7',   0.60,    NULL,       'CRSP depreciation year 7'),
('crsp_depreciation_year8',   0.65,    NULL,       'CRSP depreciation year 8'),
('crsp_depreciation_over8',   0.70,    NULL,       'CRSP depreciation for vehicles > 8 years')
ON CONFLICT (param_key) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_japan_listings_make_model ON japan_listings(make, model);
CREATE INDEX IF NOT EXISTS idx_japan_listings_year ON japan_listings(year);
CREATE INDEX IF NOT EXISTS idx_japan_listings_price_usd ON japan_listings(price_usd);
CREATE INDEX IF NOT EXISTS idx_japan_listings_platform ON japan_listings(source_platform);
CREATE INDEX IF NOT EXISTS idx_japan_listings_scraped_at ON japan_listings(scraped_at);
CREATE INDEX IF NOT EXISTS idx_local_listings_make_model ON local_listings(make, model);
CREATE INDEX IF NOT EXISTS idx_local_listings_year ON local_listings(year);
CREATE INDEX IF NOT EXISTS idx_import_estimates_listing_id ON import_cost_estimates(listing_id);