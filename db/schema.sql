-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Bills
CREATE TABLE bills (
    id SERIAL PRIMARY KEY,
    legiscan_bill_id INTEGER UNIQUE NOT NULL,
    session_id INTEGER NOT NULL,
    bill_number VARCHAR(20) NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    body VARCHAR(10),
    current_status VARCHAR(50),
    status_date DATE,
    url TEXT,
    bill_text TEXT,
    state VARCHAR(2) DEFAULT 'LA',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- AI Analysis results
CREATE TABLE bill_analyses (
    id SERIAL PRIMARY KEY,
    bill_id INTEGER REFERENCES bills(id) ON DELETE CASCADE,
    plain_english TEXT NOT NULL,
    key_changes JSONB,
    who_benefits TEXT,
    who_is_harmed TEXT,
    referenced_statutes JSONB,
    statute_context TEXT,
    policy_area VARCHAR(100),
    controversy_score FLOAT,
    analysis_model VARCHAR(50),
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(bill_id)
);

-- Bill embeddings for similarity search
CREATE TABLE bill_embeddings (
    id SERIAL PRIMARY KEY,
    bill_id INTEGER REFERENCES bills(id) ON DELETE CASCADE UNIQUE,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create HNSW index for fast similarity search
CREATE INDEX ON bill_embeddings USING hnsw (embedding vector_cosine_ops);

-- Legislators
CREATE TABLE legislators (
    id SERIAL PRIMARY KEY,
    legiscan_people_id INTEGER UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    party VARCHAR(20),
    role VARCHAR(50),
    district VARCHAR(20),
    state VARCHAR(2) DEFAULT 'LA',
    ftm_eid VARCHAR(50),
    opensecrets_id VARCHAR(20),
    ballotpedia_url TEXT,
    active BOOLEAN DEFAULT TRUE
);

-- Bill sponsorships
CREATE TABLE sponsorships (
    id SERIAL PRIMARY KEY,
    bill_id INTEGER REFERENCES bills(id) ON DELETE CASCADE,
    legislator_id INTEGER REFERENCES legislators(id) ON DELETE CASCADE,
    sponsor_type VARCHAR(20),
    UNIQUE(bill_id, legislator_id)
);

-- Campaign contributions (from FollowTheMoney)
CREATE TABLE contributions (
    id SERIAL PRIMARY KEY,
    legislator_id INTEGER REFERENCES legislators(id) ON DELETE CASCADE,
    donor_name VARCHAR(300) NOT NULL,
    donor_employer VARCHAR(300),
    donor_industry VARCHAR(200),
    donor_sector VARCHAR(200),
    amount DECIMAL(12,2) NOT NULL,
    contribution_date DATE,
    election_year INTEGER,
    contributor_type VARCHAR(50),
    ftm_record_id VARCHAR(50)
);

-- Lobbyist registrations
CREATE TABLE lobbyists (
    id SERIAL PRIMARY KEY,
    name VARCHAR(300) NOT NULL,
    firm VARCHAR(300),
    client VARCHAR(300),
    registration_date DATE,
    state VARCHAR(2) DEFAULT 'LA',
    source_url TEXT
);

-- Bill passage predictions
CREATE TABLE predictions (
    id SERIAL PRIMARY KEY,
    bill_id INTEGER REFERENCES bills(id) ON DELETE CASCADE UNIQUE,
    pass_probability FLOAT NOT NULL,
    features JSONB,
    model_version VARCHAR(20),
    predicted_at TIMESTAMPTZ DEFAULT NOW(),
    actual_outcome VARCHAR(20),
    resolved_at TIMESTAMPTZ
);

-- Model legislation matches
CREATE TABLE model_matches (
    id SERIAL PRIMARY KEY,
    bill_id INTEGER REFERENCES bills(id) ON DELETE CASCADE,
    matched_source VARCHAR(200),
    matched_title TEXT,
    similarity_score FLOAT,
    matching_sections TEXT,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

-- Conflict of interest flags
CREATE TABLE conflict_flags (
    id SERIAL PRIMARY KEY,
    bill_id INTEGER REFERENCES bills(id) ON DELETE CASCADE,
    legislator_id INTEGER REFERENCES legislators(id) ON DELETE CASCADE,
    flag_type VARCHAR(50),
    description TEXT NOT NULL,
    severity VARCHAR(20),
    evidence JSONB,
    flagged_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_bills_state ON bills(state);
CREATE INDEX idx_bills_status ON bills(current_status);
CREATE INDEX idx_contributions_legislator ON contributions(legislator_id);
CREATE INDEX idx_contributions_industry ON contributions(donor_industry);
CREATE INDEX idx_sponsorships_bill ON sponsorships(bill_id);
CREATE INDEX idx_sponsorships_legislator ON sponsorships(legislator_id);
