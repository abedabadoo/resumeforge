"""Capture frozen Qwen activations and yes/no logits on a labeled calibration corpus."""
import argparse,json,time
from pathlib import Path
import numpy as np
from cases import cases,prompt
from qwen_native import Native

def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--features',type=Path,required=True);a=p.parse_args()
 q=Native(a.runtime,a.model);rows=list(cases());hs=[];xs=[];ms=[];t=time.monotonic()
 try:
  for i,c in enumerate(rows):
   m,f,n=q.forward(prompt(c));hs.append(f['h']);xs.append(f['x']);ms.append(m);print(i+1,len(rows),c['id'],n,round(m,3),round(time.monotonic()-t,1),flush=True)
  np.savez_compressed(a.features,x=np.stack(xs),h=np.stack(hs),m=ms,d=q.rows(),ids=[c['id'] for c in rows],y=[c['label'] for c in rows]);print('saved',a.features,flush=True)
 finally:q.close()
if __name__=='__main__':main()
