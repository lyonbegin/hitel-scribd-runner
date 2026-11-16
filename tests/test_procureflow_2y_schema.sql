-- Run ONLY against GitHub Actions ephemeral PostgreSQL, NEVER production.
BEGIN;
INSERT INTO procureflow_2y.source_evidence
 (source_id,source_system,original_url,fetched_at,raw_locator,raw_sha256,raw_bytes,extraction_version,completeness_status)
VALUES
 (1,'g2b','https://www.g2b.go.kr/test',now(),'fixture://g2b',repeat('a',64),4,'fixture','verified'),
 (2,'g2b','https://www.g2b.go.kr/test2',now(),'fixture://g2b2',repeat('b',64),6,'fixture','verified'),
 (3,'g2b','https://www.g2b.go.kr/test3',now(),'fixture://g2b3',repeat('c',64),7,'fixture','verified');

INSERT INTO procureflow_2y.suppliers(supplier_id,business_no,observed_name,first_source_id)
VALUES (1,'1111111111','업체A',1),(2,'2222222222','업체B',1);
INSERT INTO procureflow_2y.notice_rounds
 (bid_no,bid_ord,bid_clsfc_no,bid_prgrs_ord,notice_title,primary_source_id)
VALUES ('R26BK01787028','000','0','000','TEST',1);

INSERT INTO procureflow_2y.opening_results
 (bid_no,bid_ord,bid_clsfc_no,bid_prgrs_ord,opening_status,declared_bidder_count,evidence_source_id)
VALUES ('R26BK01787028','000','0','000','개찰완료',2,1);
INSERT INTO procureflow_2y.bid_participations
 (bid_no,bid_ord,bid_clsfc_no,bid_prgrs_ord,raw_row_sha256,supplier_id,bidder_name,rank_no,bid_amount,bid_rate,evidence_page,evidence_source_id)
VALUES ('R26BK01787028','000','0','000',repeat('1',64),1,'업체A',1,100,90,1,1),
       ('R26BK01787028','000','0','000',repeat('2',64),2,'업체B',2,101,91,1,1);
-- A repeated source row must not change two bidder records into three.
INSERT INTO procureflow_2y.bid_participations
 (bid_no,bid_ord,bid_clsfc_no,bid_prgrs_ord,raw_row_sha256,supplier_id,bidder_name,evidence_page,evidence_source_id)
VALUES ('R26BK01787028','000','0','000',repeat('1',64),1,'업체A',1,1)
ON CONFLICT DO NOTHING;

-- Deliberately choose a non-first-ranked award winner to prove ranks and awards are independent.
INSERT INTO procureflow_2y.award_results
 (bid_no,bid_ord,bid_clsfc_no,bid_prgrs_ord,award_version,award_state,selected_supplier_id,selected_supplier_name,selected_amount,observed_at,evidence_source_id)
VALUES ('R26BK01787028','000','0','000','v1','최종낙찰확정',2,'업체B',101,now(),2);
INSERT INTO procureflow_2y.contracts
 (contract_no,contract_revision,contract_method,contract_state,contract_name,agreed_amount,evidence_source_id)
VALUES ('CONTRACT01','01','제한경쟁','체결','TEST CONTRACT',105,2);
INSERT INTO procureflow_2y.notice_contract_links
 (bid_no,bid_ord,bid_clsfc_no,bid_prgrs_ord,contract_no,contract_revision,exact_reference,link_evidence_source_id)
VALUES ('R26BK01787028','000','0','000','CONTRACT01','01','R26BK01787028',3);
INSERT INTO procureflow_2y.contract_partners
 (contract_no,contract_revision,partner_row_sha256,supplier_id,observed_name,partner_role,share_pct,evidence_source_id)
VALUES ('CONTRACT01','01',repeat('3',64),1,'업체A','구성원',35,3),
       ('CONTRACT01','01',repeat('4',64),2,'업체B','대표',65,3);
INSERT INTO procureflow_2y.delivery_orders
 (delivery_no,delivery_revision,requested_at,supplier_id,total_requested_amount,evidence_source_id)
VALUES ('DELIVERY01','01',now(),2,15,3);
INSERT INTO procureflow_2y.contract_delivery_links
 (contract_no,contract_revision,delivery_no,delivery_revision,exact_reference,link_evidence_source_id)
VALUES ('CONTRACT01','01','DELIVERY01','01','CONTRACT01',3);
INSERT INTO procureflow_2y.delivery_order_items
 (delivery_no,delivery_revision,item_row_sha256,item_title,quantity,unit_price,line_amount,evidence_source_id)
VALUES ('DELIVERY01','01',repeat('5',64),'품목1',1,5,5,3),
       ('DELIVERY01','01',repeat('6',64),'품목2',2,5,10,3);

DO $checks$
DECLARE
  bid_count BIGINT;
  supplier_count BIGINT;
  contract_count BIGINT;
  amount_total NUMERIC;
  delivery_total NUMERIC;
  winner_id BIGINT;
BEGIN
  SELECT stored_bid_rows,resolved_distinct_suppliers INTO bid_count,supplier_count
    FROM procureflow_2y.v_opening_bid_counts WHERE bid_no='R26BK01787028';
  IF bid_count<>2 OR supplier_count<>2 THEN
    RAISE EXCEPTION 'bad bidder dedup/count: % %',bid_count,supplier_count;
  END IF;
  SELECT selected_supplier_id INTO winner_id FROM procureflow_2y.award_results
   WHERE bid_no='R26BK01787028';
  IF winner_id<>2 THEN RAISE EXCEPTION 'winner mismatch'; END IF;
  SELECT COUNT(*),SUM(agreed_amount) INTO contract_count,amount_total
    FROM procureflow_2y.v_contract_amounts;
  IF contract_count<>1 OR amount_total<>105 THEN
    RAISE EXCEPTION 'contract inflated by partners or delivery items';
  END IF;
  SELECT SUM(line_amount) INTO delivery_total FROM procureflow_2y.delivery_order_items;
  IF delivery_total<>15 THEN RAISE EXCEPTION 'delivery line sum mismatch'; END IF;
  IF (SELECT count(*) FROM procureflow_2y.notice_contract_links)<>1 THEN
     RAISE EXCEPTION 'notice-contract link missing';
  END IF;
  BEGIN
    INSERT INTO procureflow_2y.notice_contract_links(
      bid_no,bid_ord,bid_clsfc_no,bid_prgrs_ord,
      contract_no,contract_revision,exact_reference,link_evidence_source_id)
    VALUES ('NOTEXIST','000','0','000','CONTRACT01','01','INVALID',3);
    RAISE EXCEPTION 'foreign-key allowed orphan notice';
  EXCEPTION WHEN foreign_key_violation THEN NULL;
  END;
END
$checks$;
ROLLBACK;
