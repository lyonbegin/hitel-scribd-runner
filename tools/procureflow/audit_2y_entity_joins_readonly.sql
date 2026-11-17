-- Read-only audit queries for the isolated recent-two-year schema.
-- This file does NOT attest that any production source rows were collected.
-- Execute only after schema_2y_core.sql and schema_2y_mas_extension.sql.
-- A zero-row result for missing evidence is NOT a completed crawl.
BEGIN READ ONLY;
-- 1. Evidence classification: incomplete/unknown sources must remain visible.
SELECT source_system, completeness_status, count(*) AS evidence_count,
       count(*) FILTER (WHERE http_status=200 AND raw_bytes=0) AS empty_http_200,
       count(*) FILTER (WHERE page_no IS NULL) AS without_page_number
FROM procureflow_2y.source_evidence
GROUP BY source_system, completeness_status
ORDER BY source_system, completeness_status;
-- 2. Three separate temporal axes. Do not use notice date to filter contract/delivery.
SELECT 'notice_published' AS event_kind, count(*) AS rows_with_date,
       min(notice_published_at) AS first_date, max(notice_published_at) AS last_date
FROM procureflow_2y.notice_rounds WHERE notice_published_at IS NOT NULL
UNION ALL
SELECT 'contract_signed', count(*), min(signed_at), max(signed_at)
FROM procureflow_2y.contracts WHERE signed_at IS NOT NULL
UNION ALL
SELECT 'delivery_requested', count(*), min(requested_at), max(requested_at)
FROM procureflow_2y.delivery_orders WHERE requested_at IS NOT NULL;
-- 3. Referential links must carry explicit official references and source evidence.
SELECT 'notice_contract' AS link_type, count(*) AS linked_rows,
       count(*) FILTER (WHERE btrim(exact_reference)='') AS blank_official_reference
FROM procureflow_2y.notice_contract_links
UNION ALL
SELECT 'contract_delivery', count(*), count(*) FILTER (WHERE btrim(exact_reference)='')
FROM procureflow_2y.contract_delivery_links
UNION ALL
SELECT 'mas_delivery', count(*), count(*) FILTER (WHERE btrim(exact_official_reference)='')
FROM procureflow_2y.mas_delivery_links;
-- 4. Detect supplier keys present in raw rows but not resolved to official supplier entity.
SELECT count(*) AS bidder_rows,
       count(*) FILTER (WHERE supplier_id IS NULL) AS unresolved_supplier_rows,
       count(*) FILTER (WHERE supplier_id IS NULL AND official_business_no IS NOT NULL)
         AS unresolved_despite_business_no
FROM procureflow_2y.bid_participations;
-- 5. Distinct counts avoid multiplying contracts by partners or delivery items.
SELECT (SELECT count(*) FROM procureflow_2y.contracts) AS contract_revisions,
       (SELECT count(*) FROM procureflow_2y.contract_partners) AS partner_rows,
       (SELECT count(*) FROM procureflow_2y.delivery_orders) AS delivery_revisions,
       (SELECT count(*) FROM procureflow_2y.delivery_order_items) AS delivery_item_rows,
       (SELECT count(*) FROM procureflow_2y.mas_agreements) AS mas_agreement_revisions;
-- 6. Explicitly show evidence gaps, rather than equating zero stored rows to zero source records.
SELECT (SELECT count(*) FROM procureflow_2y.source_evidence WHERE completeness_status='verified') AS verified_evidence,
       (SELECT count(*) FROM procureflow_2y.source_evidence WHERE completeness_status IN ('unknown','partial','error')) AS unresolved_evidence,
       (SELECT count(*) FROM procureflow_2y.contracts) AS stored_contracts,
       (SELECT count(*) FROM procureflow_2y.delivery_orders) AS stored_delivery_orders;
COMMIT;
