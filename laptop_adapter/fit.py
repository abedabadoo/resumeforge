"""Fit a real Qwen last-FFN rank-one LoRA; only training rows affect parameters."""
import argparse, hashlib, json, struct
from pathlib import Path
import numpy as np
from cases import cases, prompt

MODEL_DIGEST="00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"

def write_gguf(path,a,b):
    def string(s):
        v=s.encode();return struct.pack('<Q',len(v))+v
    def kv(k,v):
        return string(k)+(struct.pack('<I',8)+string(v) if isinstance(v,str) else struct.pack('<If',6,v))
    arrays=[('blk.31.ffn_down.weight.lora_a',(a.size,1),a),('blk.31.ffn_down.weight.lora_b',(1,b.size),b)]
    meta=b''.join(kv(k,v) for k,v in [('general.type','adapter'),('general.architecture','qwen35'),('adapter.type','lora'),('adapter.lora.alpha',1.0)])
    header=b'GGUF'+struct.pack('<IQQ',3,2,4)+meta;data=b''
    for name,shape,arr in arrays:
        header+=string(name)+struct.pack('<IQQIQ',2,*shape,0,len(data))
        data+=np.asarray(arr,dtype='<f4').tobytes();data+=b'\x00'*(-len(data)%32)
    path.write_bytes(header+b'\x00'*(-len(header)%32)+data)


def fit(x,h,m,y,d):
    # Fix B along the tied Yes-vs-No unembedding direction; fit A on logits.
    # Add the adapter after the frozen down projection, before final RMSNorm.
    u=d/np.linalg.norm(d);dx=np.sqrt(np.mean(np.sum(x*x,axis=1)))
    z=x/dx;dim=h.shape[1]
    rms=lambda a:np.sqrt(np.mean(a*a,axis=1)+1e-6)
    h0=rms(h);m0=(h@d)/h0
    slope=(u@d)/h0-((h@d)*(h@u))/(dim*h0**3)
    b=u/np.median(slope)
    w=np.zeros(x.shape[1],dtype='float64')
    # Fixed objective and budget chosen before held-out evaluation.
    for i in range(650):
        changed=h+(z@w)[:,None]*b
        inv=1/rms(changed)
        raw=(changed@d)*inv
        margin=m+raw-m0
        p=1/(1+np.exp(-np.clip(margin,-40,40)))
        deriv=(b@d)*inv-(changed@d)*(changed@b)*inv**3/dim
        grad=(z.T@((p-y)*deriv))/len(y)+.002*w
        w-=1.2*grad
    return w/dx,b


def metrics(rows,key):
    y=np.array([i['label'] for i in rows]);v=np.array([i[key] for i in rows])
    return {'correct':int(np.sum((v>0)==y)),'total':len(rows),'false_accepts':int(np.sum((v>0)&(y==0))),
            'false_holds':int(np.sum((v<=0)&(y==1))),'log_loss':round(float(np.mean(np.logaddexp(0,(1-2*y)*v))),5)}


def main():
    p=argparse.ArgumentParser()
    for name in ('features','runtime','model','out'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    s=np.load(args.features,allow_pickle=False);cs=list(cases());assert np.array_equal(s['ids'],[c['id'] for c in cs])
    tr=np.array([r['split']=='train' for r in cs]);y=s['y']
    a,b=fit(s['x'][tr].astype('d'),s['h'][tr].astype('d'),s['m'][tr],y[tr],s['d'].astype('d'))
    adapter=args.out/'qwen35-4b-resume-review-r1.gguf';write_gguf(adapter,a,b)
    from qwen_native import Native
    q=Native(args.runtime,args.model,watch=False);rows=[]
    try:
        q.load_adapter(adapter)
        for i,c in enumerate(cs):
            if tr[i]:continue
            v,_,_=q.forward(prompt(c));rows.append({'id':c['id'],'label':c['label'],'base_margin':float(s['m'][i]),'adapter_margin':v})
            print(c['id'],round(rows[-1]['base_margin'],3),round(v,3),flush=True)
    finally:q.close()
    diff=max(abs(r['base_margin']-r['adapter_margin']) for r in rows)
    if diff<.01: raise RuntimeError('Loaded adapter did not measurably affect model logits')
    report={'base_model_sha256':MODEL_DIGEST,'runtime':'llama.cpp b12189','target_tensor':'blk.31.ffn_down.weight',
            'rank':1,'trained_parameters':int(a.size),'frozen_direction_values':int(b.size),'train_pairs':int(tr.sum()),
            'heldout_source_pairs':len(rows)//2,'max_observed_margin_change':round(diff,5),
            'base':metrics(rows,'base_margin'),'trained':metrics(rows,'adapter_margin'),'rows':rows,
            'artifact_sha256':hashlib.sha256(adapter.read_bytes()).hexdigest(),'deployed_by_training_script':False}
    (args.out/'adapter-report.json').write_text(json.dumps(report,indent=2))
    print({k:v for k,v in report.items() if k!='rows'})
if __name__=='__main__':main()
