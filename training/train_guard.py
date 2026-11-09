"""Fit and evaluate a reproducible logistic warning model using only the standard library."""
from __future__ import annotations
import argparse, hashlib, json, math, random, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
from resumeforge.learned_guard import features,assess
from corpus import scenarios,CHALLENGE


def label_rows(split):
    if split=='challenge':
        return [(f'challenge-{j}-{name}',[s],c,label) for j,(name,s,ok,bad) in enumerate(CHALLENGE) for c,label in [(ok,0),(bad,1)]]
    return [(x['id'],[x['source']],x[k],y) for x in scenarios(split) for k,y in [('concise',0),('detailed',0),('bad',1)]]


def evaluate(rows,model):
    counts={k:0 for k in ('safe_passed','safe_flagged','unsafe_flagged','unsafe_missed')}
    misses=[]
    for ident,s,c,label in rows:
        result=assess(s,c,weights=model)
        guessed=int(result['flagged'])
        counts[['safe_passed','safe_flagged','unsafe_missed','unsafe_flagged'][2*label+guessed]]+=1
        if label!=guessed:misses.append(dict(id=ident,evidence=s,candidate=c,unsafe=bool(label),**result))
    return dict(counts=counts,errors=misses)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--weights',type=Path,default=HERE.parent/'resumeforge/data/risk-guard.json')
    parser.add_argument('--report',type=Path,default=HERE/'guard-report.json')
    args=parser.parse_args()
    train,val,test=(label_rows(k) for k in ('train','validation','challenge'))
    assert not ({s[0] for _,s,_,_ in train} & {s[0] for _,s,_,_ in val+test})
    frows=[(features(s,c),y) for _,s,c,y in train]
    keys=sorted(frows[0][0]); ws=dict.fromkeys(keys,0.0); b=0.0
    # Class-balanced full-batch logistic loss + L2 regularization.
    totals=[sum(y==label for _,y in frows) for label in (0,1)]
    for epoch in range(1200):
        g=dict.fromkeys(keys,0.0); gb=0.0
        for fs,y in frows:
            z=b+sum(ws[k]*fs[k] for k in keys); diff=(1/(1+math.exp(-z))-y)/(2*totals[y])
            gb+=diff
            for k in keys:g[k]+=diff*fs[k]
        for k in keys:ws[k]-=.8*(g[k]+.002*ws[k])
        b-=.8*gb
    model=dict(model_id='paired-evidence-linear-v1',weights=ws,bias=b,threshold=.5,format=1)
    # Threshold chosen on calibration only. Do not tune to the independent challenge.
    options=[]
    for t in [i/100 for i in range(10,91,2)]:
        model['threshold']=t
        counts=evaluate(val,model)['counts']
        fpr=counts['safe_flagged']/max(1,counts['safe_passed']+counts['safe_flagged'])
        options.append((fpr<=.15,counts['unsafe_flagged'],-counts['safe_flagged'],t))
    model['threshold']=max(options)[-1]
    args.weights.write_text(json.dumps(model,indent=2,sort_keys=True)+'\n')
    report={'model_id':model['model_id'],'seed':'deterministic full-batch','train_rows':len(train),'calibration_rows':len(val),'challenge_rows':len(test),'threshold':model['threshold'],'train':evaluate(train,model)['counts'],'calibration':evaluate(val,model)['counts'],'challenge':evaluate(test,model),'weights_sha256':hashlib.sha256(args.weights.read_bytes()).hexdigest(),'caveat':'Synthetic examples, small handwritten challenge; a low score never constitutes approval.'}
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['train_rows','calibration_rows','challenge_rows','threshold']},indent=2),report['challenge']['counts'])
if __name__=='__main__':main()
