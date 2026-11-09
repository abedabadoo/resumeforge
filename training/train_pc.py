"""Optional NVIDIA PC QLoRA experiment. Never installs or deploys anything.

Uses the pinned official checkpoint; freezes the base and vision tower. Only
LoRA projections inside language-model blocks receive gradients. Exact token
prefix is checked rather than silently training on system/user context.
"""
from __future__ import annotations
import argparse,hashlib,importlib.metadata,json,math,random,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE='Qwen/Qwen3.5-4B'
REVISION='851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a'
def load_rows(folder,split):
    path=folder/(split+'.jsonl');manifest=json.loads((folder/'manifest.json').read_text())[split]
    if hashlib.sha256(path.read_bytes()).hexdigest()!=manifest['sha256']:
        raise ValueError('Dataset digest mismatch; rebuild the corpus and inspect it before training.')
    rows=[json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
    if len(rows)!=manifest['rows'] or not rows:raise ValueError('Invalid split size')
    return rows
def encode(row,tokenizer,limit):
    messages=row['messages']
    # Build a genuine non-thinking inference prefix, then supervise the JSON
    # completion through the chat EOS only. No gradient labels for user text.
    p=tokenizer.apply_chat_template(messages[:-1],tokenize=False,add_generation_prompt=True,enable_thinking=False)
    a=messages[-1]['content']; eos=tokenizer.eos_token
    if not eos:raise ValueError('Missing tokenizer EOS.')
    pre=tokenizer.encode(p,add_special_tokens=False)
    full=tokenizer.encode(p+a+eos,add_special_tokens=False)
    if full[:len(pre)]!=pre or full[-1]!=tokenizer.eos_token_id:raise ValueError('Chat prefix/EOS token mismatch; inspect tokenizer rather than masking approximate lengths.')
    if len(full)>limit or len(full)<=len(pre):raise ValueError(f'Example {row["id"]} exceeds context or has no supervised tokens.')
    return full,[-100]*len(pre)+full[len(pre):]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=HERE/'sft');p.add_argument('--out',type=Path,required=True)
    p.add_argument('--epochs',type=int,choices=(1,2,3),default=1);p.add_argument('--accum',type=int,default=8)
    p.add_argument('--max-tokens',type=int,default=1536);p.add_argument('--learning-rate',type=float,default=6e-5)
    p.add_argument('--smoke',action='store_true',help='One small training/validation subset; smoke checkpoints are never production candidates.')
    args=p.parse_args()
    if args.accum<1 or args.max_tokens<128 or not 0<args.learning_rate<=.001:p.error('Invalid batch/context/learning rate.')
    train=load_rows(args.data,'train');valid=load_rows(args.data,'validation')
    if args.out.exists():p.error('Choose a new output directory (refusing to overwrite).')
    import torch
    if not torch.cuda.is_available():p.error('This optional recipe needs a working CUDA GPU; no CPU fallback or automatic downloads.')
    from transformers import AutoTokenizer,Qwen3_5ForConditionalGeneration,BitsAndBytesConfig
    from peft import LoraConfig,prepare_model_for_kbit_training,get_peft_model
    torch.manual_seed(47);random.seed(47)
    dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    kw={'revision':REVISION,'trust_remote_code':False}
    tok=AutoTokenizer.from_pretrained(BASE,**kw)
    if args.smoke:train=train[:8];valid=valid[:6]
    tr=[encode(r,tok,args.max_tokens) for r in train];va=[encode(r,tok,args.max_tokens) for r in valid]
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype)
    model=Qwen3_5ForConditionalGeneration.from_pretrained(BASE,quantization_config=quant,device_map={'':0},dtype=dtype,**kw)
    model.config.use_cache=False
    if hasattr(model.config,'text_config'):model.config.text_config.use_cache=False
    model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True)
    targets=[name for name,_ in model.named_modules() if '.language_model.layers.' in name
             and name.rsplit('.',1)[-1] in ('q_proj','v_proj','o_proj','gate_proj','up_proj','down_proj')]
    if not targets:raise RuntimeError('No supported language-only projection paths on this checkpoint.')
    model=get_peft_model(model,LoraConfig(task_type='CAUSAL_LM',r=8,lora_alpha=16,lora_dropout=.05,target_modules=targets,bias='none'))
    params=[(n,v) for n,v in model.named_parameters() if v.requires_grad]
    if not params or any('lora_' not in n or '.visual.' in n for n,_ in params):raise RuntimeError('Unexpected trainable base or vision weights.')
    optimizer=torch.optim.AdamW([v for _,v in params],lr=args.learning_rate,weight_decay=.01)
    scaler=torch.amp.GradScaler('cuda',enabled=dtype==torch.float16)
    def loss(row):
        ids,labels=row
        with torch.autocast('cuda',dtype=dtype):
            return model(input_ids=torch.tensor([ids],device='cuda'),labels=torch.tensor([labels],device='cuda'),use_cache=False).loss
    @torch.no_grad()
    def val_loss():
        model.eval();total=0.;nt=0
        for row in va:
            n=sum(x!=-100 for x in row[1]);total+=loss(row).item()*n;nt+=n
        return total/max(nt,1)
    args.out.mkdir(parents=True);best=val_loss();baseline=best;history=[];start=time.time()
    for e in range(args.epochs):
        random.shuffle(tr);model.train()
        for batch_start in range(0,len(tr),args.accum):
            batch=tr[batch_start:batch_start+args.accum];optimizer.zero_grad(set_to_none=True)
            for row in batch:
                l=loss(row)/len(batch)
                if not torch.isfinite(l):raise RuntimeError('Nonfinite loss; no candidate accepted.')
                scaler.scale(l).backward()
            scaler.unscale_(optimizer);torch.nn.utils.clip_grad_norm_([v for _,v in params],1.0)
            scaler.step(optimizer);scaler.update()
        measured=val_loss();history.append(measured);print(f'epoch {e+1}: calibration assistant-token loss {measured:.4f}',flush=True)
        if math.isfinite(measured) and measured<best:
            best=measured;model.save_pretrained(args.out/'candidate');tok.save_pretrained(args.out/'candidate')
    result={'base':BASE,'revision':REVISION,'smoke_only':args.smoke,'train_examples':len(tr),'validation_examples':len(va),
            'trainable_parameters':sum(v.numel() for _,v in params),'base_validation_loss':baseline,'epoch_validation_loss':history,
            'candidate_saved':(args.out/'candidate').exists(),'qualifies_for_auto_export':False,'seconds':round(time.time()-start,1),
            'gpu':torch.cuda.get_device_name(),'cuda':torch.version.cuda,'libraries':{k:importlib.metadata.version(k) for k in ['torch','transformers','peft','accelerate','bitsandbytes']},
            'data':json.loads((args.data/'manifest.json').read_text()),'train_seed':47,'target_module_count':len(targets)}
    (args.out/'run.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
