-- Recent-two-year MAS agreement layer; isolated, additive and source-backed.
-- Execute AFTER tools/procureflow/schema_2y_core.sql.
BEGIN;
CREATE TABLE IF NOT EXISTS procureflow_2y.mas_agreements (
  mas_contract_no TEXT NOT NULL,
  mas_revision TEXT NOT NULL,
  agreement_kind TEXT NOT NULL DEFAULT 'MAS',
  valid_from DATE,
  valid_until DATE,
  agreement_signed_at TIMESTAMPTZ,
  contracting_agency_id TEXT,
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (mas_contract_no, mas_revision),
  CHECK (valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from)
);
CREATE TABLE IF NOT EXISTS procureflow_2y.mas_suppliers (
  mas_contract_no TEXT NOT NULL,
  mas_revision TEXT NOT NULL,
  supplier_id BIGINT NOT NULL REFERENCES procureflow_2y.suppliers(supplier_id),
  source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (mas_contract_no, mas_revision, supplier_id),
  FOREIGN KEY (mas_contract_no, mas_revision)
    REFERENCES procureflow_2y.mas_agreements(mas_contract_no, mas_revision)
);
CREATE TABLE IF NOT EXISTS procureflow_2y.mas_catalog_items (
  mas_contract_no TEXT NOT NULL,
  mas_revision TEXT NOT NULL,
  item_row_sha256 TEXT NOT NULL CHECK (item_row_sha256 ~ '^[0-9a-f]{64}$'),
  supplier_id BIGINT NOT NULL,
  official_product_code TEXT,
  item_name TEXT,
  published_unit_price NUMERIC(22,2),
  price_effective_from DATE,
  price_effective_until DATE,
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (mas_contract_no, mas_revision, item_row_sha256),
  FOREIGN KEY (mas_contract_no, mas_revision, supplier_id)
    REFERENCES procureflow_2y.mas_suppliers(mas_contract_no, mas_revision, supplier_id),
  CHECK (price_effective_until IS NULL OR price_effective_from IS NULL
    OR price_effective_until >= price_effective_from)
);
-- Do not infer MAS-to-delivery linkage from product name, amount or dates.
CREATE TABLE IF NOT EXISTS procureflow_2y.mas_delivery_links (
  mas_contract_no TEXT NOT NULL,
  mas_revision TEXT NOT NULL,
  delivery_no TEXT NOT NULL,
  delivery_revision TEXT NOT NULL,
  exact_official_reference TEXT NOT NULL,
  evidence_source_id BIGINT NOT NULL REFERENCES procureflow_2y.source_evidence(source_id),
  PRIMARY KEY (mas_contract_no, mas_revision, delivery_no, delivery_revision),
  FOREIGN KEY (mas_contract_no, mas_revision)
    REFERENCES procureflow_2y.mas_agreements(mas_contract_no, mas_revision),
  FOREIGN KEY (delivery_no, delivery_revision)
    REFERENCES procureflow_2y.delivery_orders(delivery_no, delivery_revision)
);
-- MAS contract dates, contract signing dates, and delivery requested dates remain distinct.
CREATE OR REPLACE VIEW procureflow_2y.v_mas_delivery_distinct AS
SELECT m.mas_contract_no, m.mas_revision, m.agreement_signed_at,
       count(DISTINCT (l.delivery_no, l.delivery_revision)) AS linked_delivery_revisions
FROM procureflow_2y.mas_agreements m
LEFT JOIN procureflow_2y.mas_delivery_links l
  ON (m.mas_contract_no,m.mas_revision)=(l.mas_contract_no,l.mas_revision)
GROUP BY m.mas_contract_no,m.mas_revision,m.agreement_signed_at;
COMMIT;
