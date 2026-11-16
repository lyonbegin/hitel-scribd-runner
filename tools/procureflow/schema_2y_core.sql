-- ProcureFlow recent-two-year normalized storage, isolated from existing procureflow.*
-- 2026-11-16. PostgreSQL 16. This is a schema definition, not a claim of data ingestion.
-- Execute in a new isolated schema. Never mutate existing 930379-key index or bidder archives.
BEGIN;
CREATE SCHEMA IF NOT EXISTS procureflow_2y;

CREATE TABLE IF NOT EXISTS procureflow_2y.source_evidence (
  source_id BIGSERIAL PRIMARY KEY,
  source_system TEXT NOT NULL,
  original_url TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL,
  raw_locator TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
  raw_bytes BIGINT NOT NULL CHECK (raw_bytes >= 0),
  page_no INTEGER CHECK (page_no > 0),
  http_status INTEGER CHECK (http_status BETWEEN 100 AND 599),
  extraction_version TEXT NOT NULL,
  completeness_status TEXT NOT NULL CHECK (completeness_status IN
    ('verified','no_data_confirmed','partial','error','unknown')),
  source_record_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pf2_evidence_system_time
  ON procureflow_2y.source_evidence (source_system, fetched_at);

CREATE TABLE IF NOT EXISTS procureflow_2y.suppliers (
  supplier_id BIGSERIAL PRIMARY KEY,
  business_no TEXT UNIQUE,
  official_supplier_id TEXT UNIQUE,
  observed_name TEXT NOT NULL,
  first_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  CHECK (business_no IS NOT NULL OR official_supplier_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS procureflow_2y.notice_rounds (
  bid_no TEXT NOT NULL,
  bid_ord TEXT NOT NULL DEFAULT '000',
  bid_clsfc_no TEXT NOT NULL DEFAULT '0',
  bid_prgrs_ord TEXT NOT NULL DEFAULT '000',
  notice_title TEXT,
  agency_id TEXT,
  notice_published_at TIMESTAMPTZ,
  primary_source_id BIGINT REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord)
);

CREATE TABLE IF NOT EXISTS procureflow_2y.opening_results (
  bid_no TEXT NOT NULL,
  bid_ord TEXT NOT NULL,
  bid_clsfc_no TEXT NOT NULL,
  bid_prgrs_ord TEXT NOT NULL,
  opening_status TEXT NOT NULL,
  opened_at TIMESTAMPTZ,
  declared_bidder_count BIGINT CHECK (declared_bidder_count >= 0),
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord),
  FOREIGN KEY (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord)
    REFERENCES procureflow_2y.notice_rounds (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord)
);

CREATE TABLE IF NOT EXISTS procureflow_2y.bid_participations (
  bid_no TEXT NOT NULL,
  bid_ord TEXT NOT NULL,
  bid_clsfc_no TEXT NOT NULL,
  bid_prgrs_ord TEXT NOT NULL,
  raw_row_sha256 TEXT NOT NULL CHECK (raw_row_sha256 ~ '^[0-9a-f]{64}$'),
  supplier_id BIGINT REFERENCES procureflow_2y.suppliers(supplier_id),
  bidder_name TEXT NOT NULL,
  official_business_no TEXT,
  rank_no INTEGER CHECK (rank_no > 0),
  bid_amount NUMERIC(22, 2),
  bid_rate NUMERIC(14, 7),
  bid_status TEXT,
  disqualification_reason TEXT,
  evidence_page INTEGER NOT NULL CHECK (evidence_page > 0),
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord, raw_row_sha256),
  FOREIGN KEY (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord)
    REFERENCES procureflow_2y.notice_rounds (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord)
);
CREATE INDEX IF NOT EXISTS ix_pf2_bid_supplier ON procureflow_2y.bid_participations(supplier_id);

CREATE TABLE IF NOT EXISTS procureflow_2y.award_results (
  bid_no TEXT NOT NULL,
  bid_ord TEXT NOT NULL,
  bid_clsfc_no TEXT NOT NULL,
  bid_prgrs_ord TEXT NOT NULL,
  award_version TEXT NOT NULL,
  award_state TEXT NOT NULL,
  selected_supplier_id BIGINT REFERENCES procureflow_2y.suppliers(supplier_id),
  selected_supplier_name TEXT,
  selected_amount NUMERIC(22,2),
  selected_at TIMESTAMPTZ,
  observed_at TIMESTAMPTZ NOT NULL,
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord, award_version),
  FOREIGN KEY (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord)
    REFERENCES procureflow_2y.notice_rounds (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord)
);

CREATE TABLE IF NOT EXISTS procureflow_2y.contracts (
  contract_no TEXT NOT NULL,
  contract_revision TEXT NOT NULL,
  contract_method TEXT,
  contract_state TEXT,
  contract_name TEXT,
  signed_at TIMESTAMPTZ,
  agreed_amount NUMERIC(22,2),
  contracting_agency_id TEXT,
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (contract_no, contract_revision)
);
CREATE INDEX IF NOT EXISTS ix_pf2_contract_date ON procureflow_2y.contracts(signed_at);

CREATE TABLE IF NOT EXISTS procureflow_2y.private_contract_details (
  contract_no TEXT NOT NULL,
  contract_revision TEXT NOT NULL,
  sole_source_reason TEXT,
  quotation_method TEXT,
  conversion_from_failed_tender BOOLEAN,
  reason_evidence_id BIGINT REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (contract_no, contract_revision),
  FOREIGN KEY (contract_no, contract_revision)
    REFERENCES procureflow_2y.contracts(contract_no, contract_revision)
);

CREATE TABLE IF NOT EXISTS procureflow_2y.contract_partners (
  contract_no TEXT NOT NULL,
  contract_revision TEXT NOT NULL,
  partner_row_sha256 TEXT NOT NULL CHECK (partner_row_sha256 ~ '^[0-9a-f]{64}$'),
  supplier_id BIGINT REFERENCES procureflow_2y.suppliers(supplier_id),
  observed_business_no TEXT,
  observed_name TEXT NOT NULL,
  partner_role TEXT,
  share_pct NUMERIC(9,5),
  attributed_amount NUMERIC(22,2),
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (contract_no, contract_revision, partner_row_sha256),
  FOREIGN KEY (contract_no, contract_revision)
    REFERENCES procureflow_2y.contracts(contract_no, contract_revision)
);

CREATE TABLE IF NOT EXISTS procureflow_2y.contract_changes (
  contract_no TEXT NOT NULL,
  contract_revision TEXT NOT NULL,
  change_row_sha256 TEXT NOT NULL CHECK (change_row_sha256 ~ '^[0-9a-f]{64}$'),
  change_type TEXT,
  effective_at TIMESTAMPTZ,
  previous_amount NUMERIC(22,2),
  changed_amount NUMERIC(22,2),
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (contract_no, contract_revision, change_row_sha256),
  FOREIGN KEY (contract_no, contract_revision)
    REFERENCES procureflow_2y.contracts(contract_no, contract_revision)
);

CREATE TABLE IF NOT EXISTS procureflow_2y.delivery_orders (
  delivery_no TEXT NOT NULL,
  delivery_revision TEXT NOT NULL,
  requested_at TIMESTAMPTZ,
  requesting_agency_id TEXT,
  supplier_id BIGINT REFERENCES procureflow_2y.suppliers(supplier_id),
  total_requested_amount NUMERIC(22,2),
  delivery_state TEXT,
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY(delivery_no, delivery_revision)
);
CREATE TABLE IF NOT EXISTS procureflow_2y.delivery_order_items (
  delivery_no TEXT NOT NULL,
  delivery_revision TEXT NOT NULL,
  item_row_sha256 TEXT NOT NULL CHECK (item_row_sha256 ~ '^[0-9a-f]{64}$'),
  product_code TEXT,
  item_title TEXT,
  quantity NUMERIC(22,4),
  unit_price NUMERIC(22,2),
  line_amount NUMERIC(22,2),
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY(delivery_no, delivery_revision, item_row_sha256),
  FOREIGN KEY(delivery_no, delivery_revision)
    REFERENCES procureflow_2y.delivery_orders(delivery_no,delivery_revision)
);

CREATE TABLE IF NOT EXISTS procureflow_2y.supplier_registration_history (
  registration_row_sha256 TEXT PRIMARY KEY CHECK (registration_row_sha256 ~ '^[0-9a-f]{64}$'),
  supplier_id BIGINT NOT NULL REFERENCES procureflow_2y.suppliers(supplier_id),
  registration_kind TEXT NOT NULL,
  registration_code TEXT,
  valid_from DATE,
  valid_until DATE,
  observed_at TIMESTAMPTZ NOT NULL,
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id)
);

-- Never infer notice-to-contract or contract-to-delivery relationships by fuzzy names/dates.
CREATE TABLE IF NOT EXISTS procureflow_2y.notice_contract_links (
  bid_no TEXT NOT NULL,
  bid_ord TEXT NOT NULL,
  bid_clsfc_no TEXT NOT NULL,
  bid_prgrs_ord TEXT NOT NULL,
  contract_no TEXT NOT NULL,
  contract_revision TEXT NOT NULL,
  exact_reference TEXT NOT NULL,
  link_evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord, contract_no, contract_revision),
  FOREIGN KEY (bid_no, bid_ord, bid_clsfc_no, bid_prgrs_ord)
    REFERENCES procureflow_2y.notice_rounds(bid_no,bid_ord,bid_clsfc_no,bid_prgrs_ord),
  FOREIGN KEY (contract_no, contract_revision)
    REFERENCES procureflow_2y.contracts(contract_no, contract_revision)
);
CREATE TABLE IF NOT EXISTS procureflow_2y.contract_delivery_links (
  contract_no TEXT NOT NULL,
  contract_revision TEXT NOT NULL,
  delivery_no TEXT NOT NULL,
  delivery_revision TEXT NOT NULL,
  exact_reference TEXT NOT NULL,
  link_evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY(contract_no, contract_revision, delivery_no, delivery_revision),
  FOREIGN KEY(contract_no, contract_revision)
    REFERENCES procureflow_2y.contracts(contract_no,contract_revision),
  FOREIGN KEY(delivery_no, delivery_revision)
    REFERENCES procureflow_2y.delivery_orders(delivery_no,delivery_revision)
);

-- The count views cannot inflate one contract into N contracts due to bidding rows.
CREATE OR REPLACE VIEW procureflow_2y.v_opening_bid_counts AS
SELECT nr.bid_no, nr.bid_ord, nr.bid_clsfc_no, nr.bid_prgrs_ord,
       count(bp.raw_row_sha256) AS stored_bid_rows,
       count(DISTINCT bp.supplier_id) FILTER(WHERE bp.supplier_id IS NOT NULL)
         AS resolved_distinct_suppliers
FROM procureflow_2y.notice_rounds nr
LEFT JOIN procureflow_2y.bid_participations bp
  ON (nr.bid_no,nr.bid_ord,nr.bid_clsfc_no,nr.bid_prgrs_ord)
   = (bp.bid_no,bp.bid_ord,bp.bid_clsfc_no,bp.bid_prgrs_ord)
GROUP BY nr.bid_no,nr.bid_ord,nr.bid_clsfc_no,nr.bid_prgrs_ord;

CREATE OR REPLACE VIEW procureflow_2y.v_contract_amounts AS
SELECT contract_no, contract_revision, agreed_amount, signed_at, contract_method
FROM procureflow_2y.contracts;
COMMIT;
