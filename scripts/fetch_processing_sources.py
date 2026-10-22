"""Export pinned inference code only; Windows cannot check out upstream training paths named AUX."""
import hashlib
import json
import subprocess
from pathlib import Path
from voice_platform.config import ROOT

SOURCES=[
 ('https://github.com/modelscope/ClearerVoice-Studio.git','ClearerVoice-Studio','6b3774dc79c46ae8bed2a4fa5f706f0ac8c75c61',[
  'clearvoice/clearvoice/models/__init__.py',
  'clearvoice/clearvoice/models/mossformer2_ss',
  'clearvoice/clearvoice/models/mossformer2_se',
  'clearvoice/clearvoice/utils/__init__.py',
  'clearvoice/clearvoice/utils/decode.py',
  'clearvoice/clearvoice/utils/misc.py',
  'clearvoice/clearvoice/utils/bandwidth_sub.py',
  'clearvoice/clearvoice/dataloader/__init__.py',
  'clearvoice/clearvoice/dataloader/meldataset.py',
  'LICENSE','README.md'],'Apache-2.0'),
 ('https://github.com/ZFTurbo/Music-Source-Separation-Training.git','Music-Source-Separation-Training','6fdad13686bb7e84d029ec66f9dbe76e65c93ebf',['models/bs_roformer','LICENSE'],'MIT')]

def main():
 records=[]
 for url,name,commit,paths,license_name in SOURCES:
  folder=ROOT/'vendor'/name
  if not (folder/'.git').exists():subprocess.run(['git','clone','--no-checkout','--filter=blob:none',url,str(folder)],check=True)
  check=subprocess.run(['git','-C',str(folder),'cat-file','-e',commit],capture_output=True)
  if check.returncode:subprocess.run(['git','-C',str(folder),'fetch','--depth=1','origin',commit],check=True)
  names=subprocess.check_output(['git','-C',str(folder),'ls-tree','-r','--name-only',commit,*paths],text=True).splitlines()
  files=[]
  for name_in_repo in names:
   target=(folder/name_in_repo).resolve()
   if not target.is_relative_to(folder.resolve()):raise ValueError('Unsafe upstream path')
   content=subprocess.check_output(['git','-C',str(folder),'show',commit+':'+name_in_repo])
   if target.exists() and target.read_bytes()!=content:raise ValueError('Local vendor changes preserved; refusing overwrite: '+str(target))
   target.parent.mkdir(parents=True,exist_ok=True)
   if not target.exists():target.write_bytes(content)
   files.append(dict(file=name_in_repo,sha256=hashlib.sha256(content).hexdigest()))
  records.append(dict(source=url,revision=commit,license=license_name,files=files))
 target=ROOT/'runtime/source-provenance.json';target.parent.mkdir(parents=True,exist_ok=True)
 target.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Pinned inference sources ready:',len(records),flush=True)

if __name__=='__main__':main()
