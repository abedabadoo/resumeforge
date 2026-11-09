"""Repeatable local model/system acceptance. Run from any working directory.

No training, downloads, token billing, external judges, or input from your resume.
The parent imposes a wall-clock budget on each real worker and checkpoints results.
"""
from __future__ import annotations
import argparse
import hashlib
import inspect
import ipaddress
import json
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from resumeforge.models import Bullet, Candidate, ModelSettings, Profile, Role, RunRequest
from resumeforge.planning import build_plan, selected_skills, review_content
from resumeforge.engine import run

SMOKE = ["h-rev-01","h-rev-02","h-rev-05","h-rev-06","h-plan-01","h-plan-07","h-plan-10","h-pdf-04"]
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = path.with_suffix(path.suffix+".tmp")
    stage.write_text(json.dumps(data, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    stage.replace(path)
def stable(data): return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
def wordnorm(text): return " ".join(re.findall(r"[\w+#]+", text.casefold()))
def keyeq(a,b): return a.strip().casefold()==b.strip().casefold()

def cases(split):
    items=[]
    for file,task in [("reviews","review"),("plans","plan"),("requests","request")]:
        for line in (HERE/split/(file+".jsonl")).read_text().splitlines():
            if line.strip(): items.append({"task":task,**json.loads(line)})
    prefix=split[0]
    items += [{"id":prefix+"-pdf-01","task":"layout","category":"sparse-underfill","layout":"sparse","expect":"needs_content"},
              {"id":prefix+"-pdf-02","task":"layout","category":"fixed-section-overflow","layout":"overflow","expect":"needs_content"}]
    if split=="holdout":
        items += [{"id":"h-pdf-03","task":"layout","category":"dense-fixed-layout","layout":"dense","expect":"ready"},
                  {"id":"h-pdf-04","task":"end-to-end","category":"final-keyword-fit","layout":"dense","expect":"ready",
                   "job":"Logistics analyst: prioritize PostgreSQL reconciliation of parcel scans and dispatch manifests.",
                   "terms":["PostgreSQL"],"edit_request":"Shorten the database reconciliation bullet while preserving PostgreSQL and the discrepancy context. Preserve my job titles and dates.",
                   "shortened_slot":"h1","slot_patterns":[r"\bPostgreSQL\b",r"discrepanc|mismatch|inconsisten|anomal|reconcil"],
                   "final_contains":["PostgreSQL","manifest"],"final_forbidden":["Airflow","93%","certified logistics master"]}]
    return items

def make_profile(split, case):
    p=Profile.model_validate(load(HERE/split/"profile.json"))
    if case["task"]=="review":
        return Profile(name="Synthetic Reviewer Fixture",contact="fixture@example.invalid",roles=[
            Role(id="r",company="Example Operations",title="Associate",dates="2020 - 2023",
                 bullets=[Bullet(id="b",text=case["source"])])])
    if case.get("layout") in ("sparse","overflow"):
        p.roles=p.roles[:1]; p.roles[0].bullets=p.roles[0].bullets[:1]; p.facts=[]; p.skills=[]
        if case["layout"]=="overflow":
            p.certifications="; ".join("Equipment safety course module "+str(i) for i in range(190))
    if case.get("layout")=="dense":
        additions=load(HERE/split/"layout-extras.json")
        for role in p.roles:
            role.bullets.extend(Bullet(id=f"{role.id}-extra-{i}",text=s) for i,s in enumerate(additions[role.id]))
    return p

def verify_pdf(case, prof, folder, result, checks):
    import pdfplumber
    def check(name,ok): checks.append({"assertion":name,"passed":bool(ok)})
    exported=folder/"resume.pdf"
    check("status matches fixed scenario expectation", result["status"]==case["expect"])
    check("export exists if and only if status is ready",exported.exists()==(result["status"]=="ready"))
    if not exported.exists(): return
    with pdfplumber.open(exported) as pdf:
        check("one physical page", len(pdf.pages)==1)
        page=pdf.pages[0]; chars=[c for c in page.chars if c["text"].strip()]
        check("US Letter", abs(page.width-612)<.01 and abs(page.height-792)<.01)
        check("searchable text",len(chars)>40)
        if not chars: return
        check("all glyphs inside fixed 40-pt margins", all(c["x0"]>=39.5 and c["x1"]<=572.5 and c["top"]>=39.5 and c["bottom"]<=752.5 for c in chars))
        check("last visible ink within one body line of target",-.5<=752-max(c["bottom"] for c in chars)<=13.3)
        check("fixed font family/sizes", all("LiberationSans" in c["fontname"] and any(abs(c["size"]-s)<.01 for s in (12,14,32)) for c in chars))
        text=wordnorm(page.extract_text() or "")
        for phrase in [prof.name, *(r.company for r in prof.roles), *(r.title for r in prof.roles), *(r.dates for r in prof.roles), *case.get("final_contains",[])]:
            check(f"PDF includes: {phrase}",wordnorm(phrase) in text)
        for marker in case.get("final_forbidden",[]): check(f"PDF excludes: {marker}",wordnorm(marker) not in text)
        selected=load(folder/"selected.json")
        for c in selected: check("selected bullet round-trips: "+c["id"],wordnorm(c["text"]) in text)
        if case.get("shortened_slot"):
            slot=case["shortened_slot"]; before=prof.evidence()[slot].text
            check("target slot actually shortened; keeping originals is not a successful edit",
                  any(c["slot_id"]==slot and len(wordnorm(c["text"]).split())<len(wordnorm(before).split())
                      and all(re.search(term,c["text"],re.I) for term in case.get("slot_patterns", []))
                      and wordnorm(c["text"])!=wordnorm(before) for c in selected))

def evaluate(split, case, settings, folder):
    p=make_profile(split,case); checks=[]; output={}; calls=[]
    def check(name,ok): checks.append({"assertion":name,"passed":bool(ok)})
    def audit(event,args):
        if event=="urllib.Request":
            path=urlsplit(str(args[0])).path
            if path.endswith(("/chat","/completions")): calls.append(path)
    sys.addaudithook(audit) # counts real requests; never substitutes fake output.
    task=case["task"]
    if task=="review":
        c=Candidate(id="v",role_id="r",slot_id="b",text=case["candidate"],evidence_ids=["b"],rationale="Reworded for clarity.")
        r=review_content(p,[c],settings); output=r.model_dump()
        check("review decision equals independent label", r.passed==(case["expect"]=="accept"))
        if case["expect"]=="reject": check("rejection gives a reason",bool(r.issues))
    elif task=="request":
        # Test the production editorial-request judge against known final material;
        # the answer is neither sent to the model nor generated by another judge.
        from resumeforge.laptop import check_request
        req=RunRequest(profile=p, edit_request=case["edit_request"], settings=settings)
        selected=[Candidate(id="v:"+b.id,role_id=r.id,slot_id=b.id,text=b.text,evidence_ids=[b.id])
                  for r in p.roles for b in r.bullets]
        verdict=check_request(req,selected,p.skills); output=verdict.model_dump()
        check("evaluated final text satisfies or fails the explicit brief as labeled",verdict.passed==(case["expect"]=="accept"))
    elif task=="plan":
        extra={}
        if case.get("edit_request"):
            if "edit_request" not in inspect.signature(build_plan).parameters:
                raise RuntimeError("Installed planner does not expose a trusted edit_request input")
            extra["edit_request"]=case["edit_request"]
        plan=build_plan(p,case["job"],case["terms"],settings,**extra)
        ev=p.evidence()
        exact={(r.id,b.id,b.text) for r in p.roles for b in r.bullets}
        exact.update((f.role_id,"fact:"+f.id,f.text) for f in p.facts if f.confirmed)
        admitted=[c for c in plan.candidates if not c.needs_confirmation]
        variants=[c for c in admitted if (c.role_id,c.slot_id,c.text) not in exact]
        skills=selected_skills(p,plan,settings,case.get('edit_request',''))
        for c in admitted:
            check(c.id+": confirmed same-job evidence", bool(c.evidence_ids) and all(i in ev and ev[i].confirmed and ev[i].role_id==c.role_id for i in c.evidence_ids))
        for rule in case.get("forbidden",[]):
            bad=[c.id for c in admitted if ("role" not in rule or c.role_id==rule["role"]) and re.search(rule["pattern"],c.text,re.I)]
            check("no admitted text matching "+rule["pattern"]+((": "+", ".join(bad)) if bad else ""),not bad)
        for s in case.get("skill_present",[]): check("keeps supported skill "+s,any(keyeq(x,s) for x in skills))
        for s in case.get("skill_absent",[]): check("excludes skill "+s,not any(keyeq(x,s) for x in skills))
        for s in case.get("propose",[]):
            check("missing keyword routed to confirmation: "+s,any(any(keyeq(s,k) for k in q.keywords) for q in plan.proposed_claims))
        rule=case.get("require_variant")
        if rule:
            valid=[c for c in variants if c.role_id==rule["role"] and set(rule["sources"])<=set(c.evidence_ids)
                   and all(re.search(t,c.text,re.I) for t in rule["terms"]) and len(c.text.split())<=rule.get("max_words",10000)]
            check("delivers substantive requested rewrite with role, evidence, meaning and length anchors",bool(valid))
        if case.get("other_slots_unchanged"): check("no other slots rewritten",all(c.slot_id in rule["sources"] for c in variants))
        output={"plan":plan.model_dump(),"skills":skills,"novel_alternatives":len(variants)}
    else:
        current=ModelSettings() if task=="layout" else settings
        args={"profile":p,"settings":current,"job_description":case.get("job",""),"keywords":case.get("terms",[])}
        if case.get("edit_request"):
            if "edit_request" not in RunRequest.model_fields: raise RuntimeError("Engine lacks trusted edit_request input")
            args["edit_request"]=case["edit_request"]
        pdfdir=folder/"pdf"
        r=run(RunRequest(**args),pdfdir)
        verify_pdf(case,p,pdfdir,r,checks)
        output={"status":r["status"],"report":r["report"]}
    return {"passed":all(x["passed"] for x in checks) and bool(checks),"checks":checks,"output":output,
            "chat_http_attempts":len(calls),"error":None}

def worker(input_path):
    job=load(Path(input_path)); case=job["case"]; folder=Path(job["folder"]); start=time.monotonic()
    try:
        value=evaluate(job["split"],case,ModelSettings.model_validate(job["settings"]),folder)
    except Exception as exc:
        value={"passed":False,"error":f"{type(exc).__name__}: {exc}","checks":[],"chat_http_attempts":None}
    value.update(id=case["id"],task=case["task"],category=case["category"],expect=case.get("expect"),elapsed_seconds=round(time.monotonic()-start,3))
    write(folder/"result.json",value)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--split",choices=["development","holdout"],default="development")
    ap.add_argument("--suite",choices=["all","review","plan","request","layout","end-to-end"],default="all")
    ap.add_argument("--preset",choices=["laptop-smoke"]);ap.add_argument("--case",action="append")
    ap.add_argument("--provider",choices=["none","ollama","openai-compatible"],default="none")
    ap.add_argument("--strategy",help="Production ModelSettings.strategy (e.g. laptop)")
    ap.add_argument("--model",default="");ap.add_argument("--base-url",default="http://127.0.0.1:18766/v1")
    ap.add_argument("--revision",default="unspecified",help="Immutable model / GGUF digest, not just a mutable tag")
    ap.add_argument("--rounds",type=int,choices=range(1,6),default=2)
    ap.add_argument("--timeout",type=int,default=180,help="Per model request, seconds")
    ap.add_argument("--case-budget",type=int,default=600,help="Hard wall-clock budget per case (subprocess)")
    ap.add_argument("--total-budget",type=int,default=7200,help="Hard wall-clock budget per invocation")
    ap.add_argument("--repeat",type=int,default=1);ap.add_argument("--resume",action="store_true")
    ap.add_argument("--list",action="store_true");ap.add_argument("--out",type=Path);args=ap.parse_args()
    if args.preset: args.split="holdout"
    rows=cases(args.split)
    if args.preset: rows=[next(r for r in rows if r["id"]==i) for i in SMOKE]
    if args.suite!="all":rows=[r for r in rows if r["task"]==args.suite]
    if args.case:
        unknown=set(args.case)-{c["id"] for c in rows}
        if unknown:ap.error("Unknown case(s) for selected split/suite/preset: "+", ".join(sorted(unknown)))
        rows=[r for r in rows if r["id"] in args.case]
    if not rows:ap.error("Empty selection")
    if args.list:
        for r in rows:print(r["id"],r["task"],r["category"])
        return 0
    if not args.out:ap.error("--out is required")
    if not 1<=args.repeat<=20 or args.case_budget<1 or args.total_budget<1:ap.error("Invalid repeat/budget")
    if any(c["task"]!="layout" for c in rows) and (args.provider=="none" or not args.model):
        ap.error("Model cases require a real provider and model; --provider none is restricted to --suite layout")
    address=urlsplit(args.base_url)
    try: local=address.hostname=="localhost" or ipaddress.ip_address(address.hostname or "").is_loopback
    except ValueError:local=False
    if not local or address.scheme!="http" or address.username or address.password:ap.error("Only HTTP loopback model endpoints accepted")
    config={"provider":args.provider,"model":args.model,"base_url":args.base_url,"timeout_seconds":args.timeout,"max_rounds":args.rounds,"api_key_env":""}
    if args.strategy:
        if "strategy" not in ModelSettings.model_fields:ap.error("Current ResumeForge package does not yet provide strategy")
        config["strategy"]=args.strategy
    settings=ModelSettings(**config)
    if any(c["task"]!="layout" for c in rows):
        try:
            with socket.create_connection((address.hostname,address.port or 80),timeout=3): pass
        except OSError as exc:ap.error(f"Model endpoint unreachable: {exc}")
    args.out=args.out.resolve()
    files=[*sorted((HERE/args.split).glob("*")),Path(__file__),*sorted((ROOT/"resumeforge").rglob("*.py")),
           *sorted((ROOT/"resumeforge"/"data").glob("*.json")), *sorted((ROOT/"resumeforge"/"fonts").glob("*.ttf"))]
    def fingerprint():
        return stable({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()})
    manifest={"split":args.split,"ids":[c["id"] for c in rows],"repeat":args.repeat,"settings":settings.model_dump(),
              "revision":args.revision,"code_and_fixture_hash":fingerprint(),"python":platform.python_version(),
              "system":platform.platform(),"case_budget":args.case_budget}
    manifest_path=args.out/"manifest.json"
    if manifest_path.exists():
        if not args.resume or load(manifest_path)!=manifest:ap.error("Output exists; use --resume with unchanged code/model/cases or a new output directory")
    elif args.out.exists() and any(args.out.iterdir()):ap.error("Choose a new output folder")
    write(manifest_path,manifest)
    end=time.monotonic()+args.total_budget; results=[]; interrupted=False
    for rep in range(1,args.repeat+1):
        for c in rows:
            folder=args.out/f"rep-{rep:02d}"/c["id"]; path=folder/"result.json"
            if args.resume and path.exists():results.append(load(path));continue
            budget=min(args.case_budget,end-time.monotonic())
            if budget<1:interrupted=True;break
            print(f"[{rep}/{args.repeat}] {c['id']} ({c['category']})",flush=True)
            write(folder/"input.json",{"case":c,"split":args.split,"folder":str(folder),"settings":settings.model_dump()})
            try:
                proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),"__worker",str(folder/"input.json")],
                                    timeout=budget,capture_output=True,text=True)
                if proc.returncode or not path.exists():raise RuntimeError(f"Worker exited {proc.returncode}: "+proc.stderr[-500:])
            except (subprocess.TimeoutExpired,RuntimeError) as exc:
                write(path,{"id":c["id"],"task":c["task"],"category":c["category"],"expect":c.get("expect"),
                            "passed":False,"error":str(exc),"checks":[],"chat_http_attempts":None})
            if fingerprint()!=manifest["code_and_fixture_hash"]:
                ap.error("Evaluated code or fixtures changed mid-run; discard this run and use an immutable snapshot.")
            result=load(path); results.append(result);print("  "+("PASS" if result["passed"] else "FAIL"),flush=True)
        if interrupted:break
    reviews=[r for r in results if r["task"]=="review" and not r.get("error")]
    summary={"planned":len(rows)*args.repeat,"attempted":len(results),"passed":sum(r["passed"] for r in results),
             "incomplete":interrupted or len(results)!=len(rows)*args.repeat,
             "execution_errors":sum(bool(r.get("error")) for r in results),
             "graded_valid_reviews":sum(r["expect"]=="accept" for r in reviews),
             "graded_invalid_reviews":sum(r["expect"]=="reject" for r in reviews),
             "wrongly_accepted_invalid_reviews":sum(r["expect"]=="reject" and r["output"]["passed"] for r in reviews),
             "wrongly_rejected_valid_reviews":sum(r["expect"]=="accept" and not r["output"]["passed"] for r in reviews),
             "observed_chat_attempt_cases":sum((r.get("chat_http_attempts") or 0)>0 for r in results),
             "failures":[{"id":r["id"],"error":r.get("error"),"assertions":[v["assertion"] for v in r.get("checks",[]) if not v["passed"]]} for r in results if not r["passed"]],
             "human_review_replacement_validated":False}
    write(args.out/"summary.json",summary);print(json.dumps(summary,indent=2))
    return 2 if summary["incomplete"] else int(summary["passed"]!=summary["planned"])
if __name__=="__main__":
    if len(sys.argv)==3 and sys.argv[1]=="__worker":worker(sys.argv[2])
    else:sys.exit(main())
