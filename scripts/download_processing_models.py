"""Pinned official model weights for offline restoration; input recordings never leave this PC."""
from concurrent.futures import ThreadPoolExecutor
from download_reference_models import install
from download_model import configured_path
import json
from voice_platform.config import ROOT

SPECS=[
 ('alibabasglab/MossFormer2_SS_16K','mossformer-separation','models/MossFormer2_SS_16K',{'README.md','last_best_checkpoint.pt'},'apache-2.0','407cb030cd66340918ebb6c8cc63b18f8592cdbe'),
 ('alibabasglab/MossFormer2_SE_48K','mossformer-enhancement','models/MossFormer2_SE_48K',{'README.md','last_best_checkpoint.pt'},'apache-2.0','eff8c97925c8bec812af707814b3e5d777fd4503'),
 ('KimberleyJSN/melbandroformer','mel-band-vocals','models/MelBandRoformer',{'README.md','MelBandRoformer.ckpt'},'mit','ac9b0614ab3cd7f77219e18ba494dfd93956c348')]

def main():
 specs=[(*spec[:2],configured_path(key,'audio_processing'),*spec[3:]) for spec,key in zip(SPECS,('separation_dir','enhancement_dir','music_dir'))]
 with ThreadPoolExecutor(max_workers=3) as pool:
  list(pool.map(lambda s:install(*s[:5],evidence_dir='audio-restoration',revision=s[5]),specs))
 sources=json.loads((ROOT/'runtime/source-provenance.json').read_text(encoding='utf-8'))
 for spec in specs:
  path=ROOT/spec[2]/'provenance.json';value=json.loads(path.read_text(encoding='utf-8'))
  source=sources[1] if spec[0].startswith('Kimberley') else sources[0]
  value['inference_source']={key:source[key] for key in ('source','revision','license')}
  path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Restoration models verified.',flush=True)

if __name__=='__main__':main()
