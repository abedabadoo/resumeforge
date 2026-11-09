"""Sequential, model-only CPU comparison with identical prompts and memory guard.

Use after stopping the production model server; only the child started here is
terminated. The comparison never changes app defaults or downloads weights.
"""
import argparse,json,re,subprocess,sys,threading,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from resumeforge.laptop import ask,REVIEWER,Verdict,Versions,WRITER
from resumeforge.models import ModelSettings
from resumeforge.planning import CALLS

def osread(cmd):return subprocess.check_output(cmd,text=True).strip()
def swap():
    return float(re.search(r'used\s*=\s*([\d.]+)M',osread(['sysctl','-n','vm.swapusage'])).group(1))
def run(args,tag,path):
    if not path.is_file():raise ValueError('Missing model: '+str(path))
    start_swap=swap();stats={'peak_process_rss_mib':0,'start_swap_mib':start_swap,'max_swap_growth_mib':0,'worst_pressure_level':1}
    stop=threading.Event();scores=[];timings=[];error=None;write=None
    with (args.out/(tag+'.log')).open('w') as log:
        child=subprocess.Popen([str(args.binary),'--offline','-m',str(path),'-a','rf-compare','--host','127.0.0.1','--port','18768','-ngl','0','-c','8192','-np','1','-t','4','-tb','4','-b','192','-ub','96','--no-slots','--reasoning','off','--no-webui','--cors-origins','localhost','--no-cors-credentials'],stdout=log,stderr=subprocess.STDOUT)
        def watch():
            high=0
            while not stop.wait(2) and child.poll() is None:
                try:
                    rss=int(osread(['ps','-o','rss=','-p',str(child.pid)]))/1024
                    level=int(osread(['sysctl','-n','kern.memorystatus_vm_pressure_level']))
                    growth=swap()-start_swap
                except (ValueError,subprocess.CalledProcessError): continue
                stats['peak_process_rss_mib']=max(stats['peak_process_rss_mib'],round(rss,1))
                stats['max_swap_growth_mib']=max(stats['max_swap_growth_mib'],round(growth,1))
                stats['worst_pressure_level']=max(stats['worst_pressure_level'],level)
                high=high+1 if level>=2 else 0
                if high>=5 or growth>768:
                    stats['resource_stop']='Sustained OS memory pressure or swap growth above 768 MiB'; child.terminate(); return
        monitor=threading.Thread(target=watch,daemon=True);monitor.start();tok=CALLS.set(timings);t=time.monotonic()
        try:
            for _ in range(90):
                if child.poll() is not None:raise RuntimeError('Server exited before readiness')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:18768/health',timeout=1) as f:
                        if json.load(f).get('status')=='ok':break
                except OSError:pass
                time.sleep(1)
            else:raise RuntimeError('Model load timed out')
            cfg=ModelSettings(provider='openai-compatible',strategy='laptop',base_url='http://127.0.0.1:18768/v1',api_key_env='',model='rf-compare',timeout_seconds=240)
            rows=[json.loads(s) for s in (ROOT/'evaluation/development/reviews.jsonl').read_text().splitlines() if s.strip()]
            for r in rows:
                v=ask(cfg,Verdict,REVIEWER,{'evidence':[r['source']],'candidate':r['candidate']},120)
                scores.append({'id':r['id'],'expect':r['expect'],'decision':v.decision,'reason':v.reason,'correct':(v.decision=='accept')==(r['expect']=='accept')})
                print(tag,r['id'],scores[-1]['correct'],flush=True)
            source='Tested a backup restoration checklist in staging and documented two missing configuration steps for the service owner.'
            write=ask(cfg,Versions,WRITER,{'evidence':source,'target_terms':['production readiness','testing'],'applicant_editing_brief':'Keep the testing environment and my contribution clear.','layout_feedback':{}},260).model_dump()
        except Exception as e:error=str(e)
        finally:
            stop.set();monitor.join();CALLS.reset(tok)
            if child.poll() is None:child.terminate()
            try:child.wait(15)
            except subprocess.TimeoutExpired:child.kill();child.wait()
    r={'model':tag,'measured_seconds':round(time.monotonic()-t,1),'model_only_reviews':scores,'draft':write,'metrics':stats,'timings':timings,'error':error}
    (args.out/(tag+'.json')).write_text(json.dumps(r,indent=2));return r

def main():
    p=argparse.ArgumentParser();p.add_argument('--binary',required=True,type=Path);p.add_argument('--small',required=True,type=Path);p.add_argument('--large',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    for tag,path in [('4B',a.small),('9B',a.large)]:run(a,tag,path)
if __name__=='__main__':main()
