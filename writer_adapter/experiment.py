"""Reproducible, source-grouped next-token preference tuning on Qwen3.5-4B."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
import tarfile
import time

import numpy as np

HERE = Path(__file__).resolve().parent
# The bridge is intentionally pinned to this repository's b12189 ABI.
sys.path.insert(0, str(HERE.parent / "laptop_adapter"))
from qwen_native import Native, Batch, I, P, B, bind

BASE_SHA = '00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4'
ARCHIVE_SHA = 'c690cb11be36a910df7e3d5baf22ed2fb53c02243c72cd33aae8f5fd6c6afe55'
RANK, STEPS, REG, RATE = 4, 350, .008, .8
SUPPORT = Path.home() / 'Library/Application Support/ResumeForge'
SYSTEM = ('Rewrite the supplied work evidence as one concise resume bullet. Keep the stated '
          'tools, scope, attribution and results accurate. Do not add unstated achievements. '
          'Return only the bullet, in one sentence.')
CTX_LIMIT, MAX_NEW = 250, 64


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(runtime, model, archive):
    if digest(archive) != ARCHIVE_SHA or digest(model) != BASE_SHA:
        raise ValueError('Unexpected model or runtime archive SHA-256')
    with tarfile.open(archive, 'r:gz') as tar:
        libs = [p for p in runtime.glob('*.dylib') if p.name.startswith(('libggml', 'libllama.'))]
        if not {'libggml.dylib', 'libggml-base.dylib', 'libllama.dylib', 'libggml-cpu.dylib'} <= {p.name for p in libs}:
            raise ValueError('Missing expected b12189 libraries')
        for p in libs:
            item = tar.extractfile('llama-b12189/' + p.name)
            if item is None or digest(p) != hashlib.sha256(item.read()).hexdigest():
                raise ValueError(f'Installed library differs from pinned b12189 archive: {p.name}')


def chat(source):
    return (f'<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n'
            f'Evidence: {source}<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n')


def divergence(a, b):
    for i, (u, v) in enumerate(zip(a, b)):
        if u != v and i:
            return a[:i], u, v
    raise ValueError('Alternatives must differ at a noninitial token before either sequence ends')


class Writer(Native):
    capture = False

    def _eval(self, tensor, ask, ignored):
        return super()._eval(tensor, ask, ignored) if self.capture else False

    def step(self, ids, reset):
        size = len(ids)
        if not 0 < size <= CTX_LIMIT:
            raise ValueError(f'Invalid batch length {size}')
        toks = (I * size)(*ids)
        flags = (C.c_int8 * size)()
        flags[-1] = 1
        if reset:
            self.captured.clear()
            self.clear(self.memory, True)
        batch = Batch(size, C.cast(toks, P), None, None, None, None, C.cast(flags, P))
        if self.decode(self.ctx, batch):
            raise RuntimeError('Native llama_decode failed')
        p = self.logits(self.ctx, -1)
        if not p:
            raise RuntimeError('Missing native logits')
        return p

    def pair(self, row, features=False):
        pre = chat(row['source'])
        tokens, good, bad = divergence(self.tokenize(pre + row['good']), self.tokenize(pre + row['bad']))
        # No training signal may live in the instructions or chat template.
        if len(tokens) < len(self.tokenize(pre)) - 1:
            raise ValueError('Token contrast starts before response')
        self.capture = features
        logits = self.step(tokens, True)
        result = {'good_token': good, 'bad_token': bad, 'prefix_tokens': len(tokens),
                  'margin': float(logits[good] - logits[bad])}
        if features:
            if not {'x', 'h'} <= self.captured.keys() or 'error' in self.captured:
                raise RuntimeError(f'Missing native features: {self.captured.keys()}')
            self.ids = [good, bad]
            result.update(x=self.captured['x'], h=self.captured['h'], d=self.rows())
        return result

    def generate(self, source):
        self.capture = False
        pre = self.tokenize(chat(source))
        if len(pre) + MAX_NEW > CTX_LIMIT:
            raise ValueError('Free-generation probe exceeds native context budget')
        eog = bind(self.ll, 'llama_vocab_is_eog', B, P, I)
        piece = bind(self.ll, 'llama_token_to_piece', I, P, I, P, I, I, B)
        logits = self.step(pre, True)
        content = bytearray()
        for i in range(MAX_NEW):
            token = int(np.ctypeslib.as_array(logits, shape=(self.v,)).argmax())
            if eog(self.vocab, token):
                return {'text': content.decode().strip(), 'completion_tokens': i, 'stop': 'eog'}
            buf = C.create_string_buffer(1024)
            n = piece(self.vocab, token, buf, len(buf), 0, False)
            if not 0 <= n <= len(buf):
                raise ValueError('Unexpected token byte length')
            content.extend(buf.raw[:n])
            logits = self.step([token], False)
        return {'text': content.decode(errors='replace').strip(), 'completion_tokens': MAX_NEW,
                'stop': 'limit'}


def normtext(s):
    return ' '.join(re.findall(r'[a-z0-9]+', s.lower()))


def load_cases(path):
    obj = json.loads(path.read_text())
    rows, probes = obj['pairs'], obj['probes']
    all_rows = rows + probes
    if len({r['id'] for r in all_rows}) != len(all_rows) or len({normtext(r['source']) for r in all_rows}) != len(all_rows):
        raise ValueError('Source or identifier reused across cases')
    if {r['split'] for r in rows} != {'train','holdout'}:
        raise ValueError('Invalid split')
    assert sum(r['split']=='train' for r in rows) >= 16
    assert sum(r['split']=='holdout' for r in rows) >= 8 and len(probes) >= 6
    for r in rows:
        if not r['good'] or not r['bad'] or r['good']==r['bad']:
            raise ValueError(f'Invalid pair: {r["id"]}')
    for r in probes:
        for exp in r['required'] + r['forbidden']:
            re.compile(exp,re.I)
    # All training evidence is synthetic. Detect material verbatim spans reused
    # from the app's frozen qualification fixtures or these independent probes.
    external = {}
    for p in sorted((HERE.parent / 'evaluation' / 'holdout').glob('*.json*')):
        external[p.name] = normtext(p.read_text())
    def grams(s):
        words = normtext(s).split()
        return {' '.join(words[i:i+7]) for i in range(len(words)-6)}
    train = [r for r in rows if r['split']=='train']
    other = [r for r in rows if r['split']=='holdout'] + probes
    for r in train:
        for key in ('source','good','bad'):
            for g in grams(r[key]):
                if any(g in e for e in external.values()) or any(g in normtext(x['source']) for x in other):
                    raise ValueError(f'Qualification overlap in {r["id"]}: {g}')
    if not external:
        raise ValueError('Frozen application holdout not found for overlap audit')
    return rows, probes


def fit(X, H, M, D):
    """Fit A by pairwise logistic loss, given train-only unembedding subspace B."""
    x, h, m, d = (np.asarray(a, dtype='float64') for a in (X,H,M,D))
    scale = np.sqrt(np.mean(np.sum(x*x, axis=1)))
    z = x/scale
    inv_rms = lambda h: 1 / np.sqrt(np.mean(h*h,axis=1) + 1e-6)
    # Train-only SVD of per-example logit directions; no validation peeking.
    _, _, vt = np.linalg.svd(d/np.linalg.norm(d,axis=1)[:,None],full_matrices=False)
    b = vt[:RANK].T.copy()
    def rdot(a,b): return (a*b).sum(axis=1)
    inv0 = inv_rms(h)
    raw0 = rdot(h,d)*inv0
    def slope(u,inv,raw):
        return (d@b)*inv[:,None] - (u@b)*(raw*inv**2/h.shape[1])[:,None]
    b /= np.median(np.linalg.norm(slope(h,inv0,raw0),axis=1))
    w = np.zeros((x.shape[1],RANK))
    for _ in range(STEPS):
        u = h + (z@w)@b.T
        inv = inv_rms(u)
        raw = rdot(u,d)*inv
        margin = m + raw - raw0
        error = -1/(1+np.exp(np.clip(margin,-40,40)))
        grad = z.T@(error[:,None]*slope(u,inv,raw))/len(m) + REG*w
        w -= RATE*grad
    if not np.isfinite(w).all() or not np.any(w):
        raise RuntimeError('Training produced invalid weights')
    return (w.T/scale).astype('<f4'), b.astype('<f4')


def write_gguf(path,a,b):
    assert a.shape[0] == b.shape[1] == RANK
    def st(s):
        v = s.encode()
        return struct.pack('<Q',len(v))+v
    def kv(k,v):
        return st(k)+(struct.pack('<I',8)+st(v) if isinstance(v,str) else struct.pack('<If',6,v))
    fields = [('general.type','adapter'),('general.architecture','qwen35'),
              ('adapter.type','lora'),('adapter.lora.alpha',float(RANK))]
    header = b'GGUF'+struct.pack('<IQQ',3,2,len(fields))+b''.join(kv(*p) for p in fields)
    data = b''
    for name, arr in [('a',a),('b',b)]:
        header += st('blk.31.ffn_down.weight.lora_'+name)+struct.pack('<IQQIQ',2,*arr.shape[::-1],0,len(data))
        data += np.asarray(arr,dtype='<f4').tobytes(order='C')
        data += b'\0'*(-len(data)%32)
    path.write_bytes(header+b'\0'*(-len(header)%32)+data)


REFUSE = r"\b(?:cannot|can't|can’t|insufficient evidence|unable to|not enough (?:information|evidence)|as an ai|please provide)\b"

def score(probe, output):
    t = output['text']
    missing = [exp for exp in probe['required'] if not re.search(exp,t,re.I)]
    invented = [exp for exp in probe['forbidden'] if re.search(exp,t,re.I)]
    invalid = [k for k,flag in {'truncated':output['stop']!='eog', 'refusal': bool(re.search(REFUSE,t,re.I)),
               'malformed': not t.strip() or '\n' in t.strip() or bool(re.search(r'<\||</?think>|^[{\[]',t)),
               'length': not 4<=len(t.split())<=50}.items() if flag]
    return {**output,'missing_anchors':missing,'forbidden_hits':invented,'invalid':invalid,
            'pass':not (missing or invented or invalid)}


def pair_summary(values):
    a = np.array(values)
    return {'total':len(a),'preferred':int(sum(a>0)),
            'log_loss':float(np.mean(np.logaddexp(0,-a)))}


def dump(path,data):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2,ensure_ascii=False)+'\n')
    tmp.replace(path)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--runtime',type=Path,default=SUPPORT/'inference/b12189/llama-b12189')
    ap.add_argument('--model',type=Path,default=SUPPORT/'models/Qwen3.5-4B-Q4_K_M.gguf')
    ap.add_argument('--archive',type=Path,default=SUPPORT/'inference/b12189/runtime.tar.gz')
    ap.add_argument('--out',type=Path,default=HERE/'result')
    ap.add_argument('--check-only',action='store_true')
    ap.add_argument('--threads',type=int,default=4)
    args=ap.parse_args()
    rows,probes=load_cases(HERE/'cases.json')
    if args.check_only:
        print(f'Corpus and overlap checks passed ({len(rows)} pairs; {len(probes)} probes).')
        return
    args.out.mkdir(parents=True,exist_ok=True)
    verify(args.runtime,args.model,args.archive)
    q=Writer(args.runtime,args.model,threads=args.threads)
    started=time.monotonic()
    pairlog=[]
    probelog=[]
    try:
        tr=[r for r in rows if r['split']=='train']
        ho=[r for r in rows if r['split']=='holdout']
        states=[]
        for r in tr:
            s=q.pair(r,True)
            states.append(s)
            print('train feature',r['id'],round(s['margin'],3),flush=True)
        a,b=fit(*[np.array([s[k] for s in states]) for k in ('x','h','margin','d')])
        adapter=args.out/'qwen35-4b-resume-writing-r4.gguf'
        write_gguf(adapter,a,b)
        for r in ho:
            x=q.pair(r)
            pairlog.append({'id':r['id'],'family':r['family'],'source':r['source'],'good':r['good'],
                            'bad':r['bad'],'base':x})
            print('base contrast',r['id'],round(x['margin'],3),flush=True)
        for r in probes:
            probelog.append({'id':r['id'],'source':r['source'],'base':score(r,q.generate(r['source']))})
            print('base prose',r['id'],probelog[-1]['base']['text'],flush=True)
        q.load_adapter(adapter)
        for r,entry in zip(ho,pairlog):
            entry['adapter']=q.pair(r)
            print('adapter contrast',r['id'],round(entry['adapter']['margin'],3),flush=True)
        for r,entry in zip(probes,probelog):
            entry['adapter']=score(r,q.generate(r['source']))
            print('adapter prose',r['id'],entry['adapter']['text'],flush=True)
    finally:
        q.close()
    delta=max(abs(r['base']['margin']-r['adapter']['margin']) for r in pairlog)
    if delta < .01:
        raise RuntimeError('Native logits do not verify an effective loaded adapter')
    metrics={k:{'pairs':pair_summary([r[k]['margin'] for r in pairlog]),
                'free_writing_passed':sum(r[k]['pass'] for r in probelog),
                'free_writing_total':len(probelog)} for k in ['base','adapter']}
    report={'method':'first-divergent-token conditional pairwise preference LoRA; not full QLoRA/SFT',
            'model_sha256':BASE_SHA,'runtime_archive_sha256':ARCHIVE_SHA,
            'cases_sha256':digest(HERE/'cases.json'),'adapter_sha256':digest(adapter),
            'target':'blk.31.ffn_down.weight','rank':RANK,'alpha':RANK,
            'fitted_A_values':a.size,'train_derived_B_values':b.size,
            'train_sources':len(tr),'holdout_sources':len(ho),'free_probes':len(probes),
            'elapsed_inference_and_fit_seconds':round(time.monotonic()-started,2),
            'max_abs_native_margin_delta':delta,'metrics':metrics,'pairs':pairlog,'free_writing':probelog,
            'deployed':False,'limitations':'Small synthetic corpus; one teacher-forced token contrast per pair. Prose checks detect named errors only. No guarantee against omitted or invented claims.'}
    dump(args.out/'report.json',report)
    print(json.dumps(metrics,indent=2),flush=True)

if __name__=='__main__':
    main()
