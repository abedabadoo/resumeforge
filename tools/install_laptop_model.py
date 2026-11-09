"""Pinned Intel Mac inference runtime + weights. No global package changes."""
import hashlib
import json
import platform
import tarfile
import urllib.request
from pathlib import Path

DEST=Path.home()/"Library/Application Support/ResumeForge"
BUILD="b12189"
RUNTIME="https://github.com/ggml-org/llama.cpp/releases/download/b12189/llama-b12189-bin-macos-x64.tar.gz"
WEIGHTS="https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf"
RHASH="c690cb11be36a910df7e3d5baf22ed2fb53c02243c72cd33aae8f5fd6c6afe55"
WHASH="00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"


def sha(path):
    d=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(2**20),b""):d.update(chunk)
    return d.hexdigest()


def fetch(url,path,expected):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and sha(path)==expected:return
    tmp=path.with_name(path.name+".download")
    print("Downloading",path.name,flush=True)
    urllib.request.urlretrieve(url,tmp)
    if sha(tmp)!=expected:raise SystemExit("Checksum mismatch: "+str(tmp))
    tmp.replace(path)


def main():
    if platform.system()!="Darwin" or platform.machine()!="x86_64":raise SystemExit("For Intel macOS only. On the PC configure its own local model endpoint.")
    rt=DEST/"inference"/BUILD
    archive=rt/"runtime.tar.gz"
    fetch(RUNTIME,archive,RHASH)
    with tarfile.open(archive) as tar:tar.extractall(rt,filter="data")
    fetch(WEIGHTS,DEST/"models/Qwen3.5-4B-Q4_K_M.gguf",WHASH)
    (DEST/"laptop-model.json").write_text(json.dumps({"runtime":BUILD,"runtime_sha256":RHASH,"quant":"Q4_K_M","model":"Qwen/Qwen3.5-4B","weight_source":WEIGHTS,"weights_sha256":WHASH},indent=2))
    print("Verified and installed. Restart ResumeForge. Weights load when you first use the model.")


if __name__=="__main__":main()
