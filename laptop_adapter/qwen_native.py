"""Minimal pinned b12189 llama.cpp bridge for training a last-FFN rank-one adapter.

This is intentionally ABI-specific, for the provided Intel Mac experiment only. It does
not call out to a service. Only run with the sha-verified b12189 libraries and base.
"""
import ctypes as C
from pathlib import Path
import os
import numpy as np

P=C.c_void_p; S=C.c_char_p; I=C.c_int32; U=C.c_uint32; F=C.c_float; Z=C.c_size_t; B=C.c_bool

def fields(names,kind): return [(k,kind) for k in names.split()]
class ModelParams(C.Structure):
 _fields_=fields('devices buft',P)+fields('gpu split load lazy main',I)+fields('split_p progress progress_user kv',P)+fields('vocab check extra nohost noalloc mtp',B)
class ContextParams(C.Structure):
 _fields_=fields('ctx batch ubatch seq rs outputs ops',U)+fields('threads threadsb ctype rope pool attention flash',I)+fields('rfbase rfscale yarn1 yarn2 yarn3 yarn4',F)+fields('yarnorig',U)+fields('defrag',F)+fields('eval eval_data',P)+fields('k v',I)+fields('cache',Z)+fields('abort abort_data',P)+fields('emb offk noperf offop swa unified',B)+fields('samplers',P)+fields('nsamplers',Z)+fields('other',P)
class Batch(C.Structure):
 _fields_=[('n',I)]+fields('token embd pos n_seq seq outputs',P)
class GParams(C.Structure): _fields_=[('noalloc',B),('ctx',P)]
class Traits(C.Structure): _fields_=[('name',S),('n',C.c_int64),('interleave',C.c_int64),('size',Z),('quantized',B),('dequant',P),('quant',P)]

def bind(lib,name,ret,*args):
 fn=getattr(lib,name);fn.restype=ret;fn.argtypes=list(args);return fn

class Native:
 def __init__(self,runtime,model,threads=4,watch=True):
  self.runtime=Path(runtime); self.path=Path(model)
  if self.runtime.name!='llama-b12189' or not (self.runtime/'libllama.0.9.0.dylib').is_file(): raise ValueError('Requires the signed-off llama.cpp b12189 Intel macOS release ABI')
  self.gg=C.CDLL(str(self.runtime/'libggml-base.dylib'),mode=C.RTLD_GLOBAL);self.backend=C.CDLL(str(self.runtime/'libggml.dylib'),mode=C.RTLD_GLOBAL);self.ll=C.CDLL(str(self.runtime/'libllama.dylib'),mode=C.RTLD_GLOBAL)
  bind(self.backend,'ggml_backend_load_all_from_path',None,S)(os.fsencode(runtime));bind(self.ll,'llama_backend_init',None)()
  modelparams=bind(self.ll,'llama_model_default_params',ModelParams)();modelparams.gpu=0
  self.model=bind(self.ll,'llama_model_load_from_file',P,S,ModelParams)(os.fsencode(model),modelparams)
  if not self.model: raise RuntimeError('Could not load base model')
  self.vocab=bind(self.ll,'llama_model_get_vocab',P,P)(self.model)
  self.d=bind(self.ll,'llama_model_n_embd',I,P)(self.model);self.v=bind(self.ll,'llama_vocab_n_tokens',I,P)(self.vocab)
  if self.d!=2560: raise ValueError('Only Qwen3.5-4B is supported')
  self.tokfn=bind(self.ll,'llama_tokenize',I,P,S,I,C.POINTER(I),I,B,B)
  self.names=bind(self.gg,'ggml_get_name',S,P);self.nbytes=bind(self.gg,'ggml_nbytes',Z,P)
  self.fetch=bind(self.gg,'ggml_backend_tensor_get',None,P,P,Z,Z);self.captured={};self.last_layer_names=set();self.watch=watch
  self.callback=C.CFUNCTYPE(B,P,B,P)(self._eval)
  cp=bind(self.ll,'llama_context_default_params',ContextParams)();cp.ctx=256;cp.batch=256;cp.ubatch=128;cp.seq=1;cp.threads=threads;cp.threadsb=threads;cp.outputs=1;cp.ops=1;cp.pool=0;cp.attention=0;cp.offk=False;cp.offop=False
  if watch:cp.eval=C.cast(self.callback,P).value
  self.ctx=bind(self.ll,'llama_init_from_model',P,P,ContextParams)(self.model,cp)
  if not self.ctx:raise RuntimeError('Could not initialize context')
  self.memory=bind(self.ll,'llama_get_memory',P,P)(self.ctx);self.clear=bind(self.ll,'llama_memory_clear',None,P,B)
  self.decode=bind(self.ll,'llama_decode',I,P,Batch);self.logits=bind(self.ll,'llama_get_logits_ith',C.POINTER(F),P,I)
  self.ids=[self.tokenize(k,False)[0] for k in ('Yes','No')]
  if any(len(self.tokenize(k,False))!=1 for k in ('Yes','No')):raise ValueError('Labels must be single tokens')
 def _eval(self,t,ask,ignored):
  name=self.names(t)
  if name.endswith(b'-31'):self.last_layer_names.add(name.decode())
  target={b'ffn_swiglu-31':('x',9216),b'l_out-31':('h',2560)}.get(name)
  if not target:return False
  if ask:return True
  label,width=target;size=self.nbytes(t);n=width*4
  if size<n or size%n: self.captured['error']=f'Unexpected shape {label}: {size}';return False
  a=np.empty(width,dtype=np.float32);self.fetch(t,a.ctypes.data,size-n,n);self.captured[label]=a;return True
 def tokenize(self,prompt,special=True):
  s=prompt.encode();a=(I*(len(s)+16))();n=self.tokfn(self.vocab,s,len(s),a,len(a),False,special)
  if n<=0:raise ValueError('Tokenization failed')
  return list(a[:n])
 def forward(self,prompt):
  ids=self.tokenize(prompt);size=len(ids)
  if size>250:raise ValueError('This training harness expects a short evidence pair')
  toks=(I*size)(*ids);out=(C.c_int8*size)();out[-1]=1;b=Batch(size,C.cast(toks,P),None,None,None,None,C.cast(out,P));self.captured.clear();self.clear(self.memory,True)
  if self.decode(self.ctx,b):raise RuntimeError('Decode failed')
  p=self.logits(self.ctx,-1)
  if not p:raise RuntimeError('Logits unavailable')
  margin=float(p[self.ids[0]]-p[self.ids[1]])
  if self.watch and not {'h','x'}<=self.captured.keys():raise RuntimeError(f'Missing last-layer features {list(self.captured)}; graph: {sorted(self.last_layer_names)}')
  return margin,self.captured.copy(),size
 def rows(self):
  # Dequantize only the two tied token-embedding rows touched by the binary decision.
  g=bind(self.gg,'gguf_init_from_file',P,S,GParams)(os.fsencode(self.path),GParams(True,None));base=bind(self.gg,'gguf_get_data_offset',Z,P)(g)
  find=bind(self.gg,'gguf_find_tensor',C.c_int64,P,S);offset=bind(self.gg,'gguf_get_tensor_offset',Z,P,C.c_int64);ty=bind(self.gg,'gguf_get_tensor_type',I,P,C.c_int64)
  with self.path.open('rb') as f:
   ti=find(g,b'token_embd.weight');assert ti>=0
   typ=ty(g,ti);traits=bind(self.gg,'ggml_get_type_traits',C.POINTER(Traits),I)(typ).contents
   rowbytes=self.d//traits.n*traits.size;fn=C.CFUNCTYPE(None,P,C.POINTER(F),C.c_int64)(traits.dequant);rows=[]
   for idx in self.ids:
    f.seek(base+offset(g,ti)+idx*rowbytes);raw=C.create_string_buffer(f.read(rowbytes));a=np.empty(self.d,np.float32);fn(raw,a.ctypes.data_as(C.POINTER(F)),self.d);rows.append(a)
   ti=find(g,b'output_norm.weight');assert ti>=0 and ty(g,ti)==0;f.seek(base+offset(g,ti));gamma=np.frombuffer(f.read(self.d*4),np.float32).copy()
  bind(self.gg,'gguf_free',None,P)(g);return (rows[0]-rows[1])*gamma
 def load_adapter(self,path):
  a=bind(self.ll,'llama_adapter_lora_init',P,P,S)(self.model,os.fsencode(path))
  if not a:raise RuntimeError('Native adapter load failed')
  ret=bind(self.ll,'llama_set_adapters_lora',I,P,C.POINTER(P),Z,C.POINTER(F))(self.ctx,(P*1)(a),1,(F*1)(1.))
  if ret:raise RuntimeError('Could not apply adapter to context')
 def close(self):
  bind(self.ll,'llama_free',None,P)(self.ctx);bind(self.ll,'llama_model_free',None,P)(self.model);bind(self.ll,'llama_backend_free',None)()
