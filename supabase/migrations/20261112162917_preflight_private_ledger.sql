-- Server-only schema. Never expose ledger evidence or bank details via the Data API.
CREATE SCHEMA IF NOT EXISTS preflight;
REVOKE ALL ON SCHEMA preflight FROM PUBLIC;
CREATE TABLE preflight.vendors (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    known_domains TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE preflight.vendor_bank_accounts (
    vendor_id BIGINT NOT NULL REFERENCES preflight.vendors(id),
    account_identifier_normalised TEXT NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL,
    approved_by_user BOOLEAN NOT NULL DEFAULT FALSE,
    approved_at TIMESTAMPTZ,
    approved_by_name TEXT,
    PRIMARY KEY (vendor_id, account_identifier_normalised),
    CHECK (NOT approved_by_user OR (approved_at IS NOT NULL AND approved_by_name IS NOT NULL))
);
CREATE TABLE preflight.invoices (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vendor_id BIGINT NOT NULL REFERENCES preflight.vendors(id),
    invoice_number TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('PASS', 'REVIEW', 'BLOCK'))
);
CREATE INDEX invoices_vendor_date ON preflight.invoices(vendor_id, received_at);
CREATE INDEX invoices_hash ON preflight.invoices(content_hash);
CREATE TABLE preflight.reports (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    report TEXT NOT NULL
);
ALTER TABLE preflight.vendors ENABLE ROW LEVEL SECURITY;
ALTER TABLE preflight.vendor_bank_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE preflight.invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE preflight.reports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON ALL TABLES IN SCHEMA preflight FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA preflight FROM PUBLIC;
-- No anon/authenticated grants or browser policies: access is the server connection only.
