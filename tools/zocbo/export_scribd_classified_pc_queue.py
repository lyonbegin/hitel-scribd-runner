#!/usr/bin/env python3
"""Export a pinned, independently verified classification checkpoint to a PC queue.
No network access to Scribd; no download is initiated by this script.
"""
import argparse,csv,hashlib,io,json,re,zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--checkpoint",required=True)
    p.add_argument("--expected-verified",type=int,required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(a.checkpoint) as z:
        stats=json.loads(z.read("status.json"))
        rows=list(csv.DictReader(io.StringIO(z.read("Scribd_AI_분류결과.csv").decode("utf-8-sig"),newline="")))
        done={}
        for name in z.namelist():
            if re.fullmatch(r"completed/[^/]+\.json",name):
                for r in json.loads(z.read(name))["rows"]:
                    n=int(r["no"])
                    if n in done or not 1<=n<=18109:raise ValueError("DUPLICATE_OR_INVALID_COMPLETED_ID")
                    done[n]=r
    if len(rows)!=18109 or len(done)!=a.expected_verified or stats["verified_ai_completed"]!=len(done):
        raise ValueError("CHECKPOINT_COUNT_MISMATCH")
    if len({r["문서 ID"] for r in rows})!=18109 or stats["unverified_skipped"]!=0:
        raise ValueError("SOURCE_ID_OR_SKIP_MISMATCH")
    candidates=[];review=[];counts=Counter()
    for i,r in enumerate(rows,1):
        if int(r["번호"])!=i:raise ValueError("SOURCE_ORDER_MISMATCH")
        proof=done.get(i)
        if proof is None:
            if r["학교급"]!="미처리" or r["다운로드"]:raise ValueError("UNVERIFIED_ROW_HAS_CLASSIFICATION")
            continue
        for k,v in (("문서 ID","id"),("학교급","school"),("학년","grade"),("학기","semester"),
                    ("2022 세부과목","subject"),("다운로드","download")):
            expected="" if proof.get(v) is None else str(proof[v])
            if r[k]!=expected:
                raise ValueError(f"VERIFIED_CSV_MISMATCH row={i} field={k} csv={r[k]!r} proof={expected!r}")
        decision=proof["download"];counts[decision]+=1
        item={"document_id":r["문서 ID"],"original_title":r["원문 제목"],"original_url":r["Scribd 상세URL"],
              "source_no":i,"school":r["학교급"],"grade":r["학년"],"semester":r["학기"],
              "subject":r["2022 세부과목"],"edition":r["고등 판본"],"download_decision":decision}
        if decision in ("대상","판본검토"):
            u=urlparse(item["original_url"])
            if (u.scheme!="https" or u.netloc.lower() not in ("scribd.com","www.scribd.com")
                or not re.match(r"^/document/"+re.escape(item["document_id"])+r"(?:/|$)",u.path)):
                raise ValueError("INVALID_TARGET_URL_"+item["document_id"])
            (candidates if decision=="대상" else review).append(item)
        elif decision!="제외":raise ValueError("UNKNOWN_DOWNLOAD_DECISION")
    fields=["document_id","original_title","original_url","source_no","school","grade","semester","subject","edition","download_decision"]
    for name,data in (("download_queue.csv",candidates+review),("edition_review.csv",review)):
        with (out/name).open("w",encoding="utf-8-sig",newline="") as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(data)
    summary={"total":18109,"verified":len(done),"unverified":18109-len(done),
             "download_targets":len(candidates),"edition_review":len(review),"total_download_queue":len(candidates)+len(review),"excluded":counts["제외"],
             "decision_counts":dict(counts),"checkpoint_sha256":hashlib.sha256(Path(a.checkpoint).read_bytes()).hexdigest(),
             "download_queue_sha256":hashlib.sha256((out/"download_queue.csv").read_bytes()).hexdigest(),
             "downloads_started":0,"note":"AI target is educational relevance, not a license or download entitlement."}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SCRIBD_PC_QUEUE_VERIFIED",json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=="__main__":main()
