-- Structural regression tests; no claim of live G2B ingestion.
DO $$
DECLARE
  missing text;
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'mas_agreements','mas_suppliers','mas_catalog_items','mas_delivery_links'
  ] LOOP
    IF to_regclass('procureflow_2y.'||table_name) IS NULL THEN
      RAISE EXCEPTION 'Missing MAS table %',table_name;
    END IF;
  END LOOP;
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='procureflow_2y'
      AND table_name='mas_agreements' AND column_name='agreement_signed_at'
  ) OR NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='procureflow_2y'
      AND table_name='delivery_orders' AND column_name='requested_at'
  ) THEN RAISE EXCEPTION 'MAS agreement and delivery dates must be separate'; END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid='procureflow_2y.mas_delivery_links'::regclass
      AND contype='f'
  ) THEN RAISE EXCEPTION 'MAS delivery links must enforce foreign keys'; END IF;
END $$;
-- A zero-row view is expected until verified original records are ingested.
SELECT count(*) AS mas_agreement_rows FROM procureflow_2y.mas_agreements;
SELECT count(*) AS mas_delivery_link_rows FROM procureflow_2y.mas_delivery_links;
