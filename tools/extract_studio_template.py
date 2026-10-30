"""Copy the validated Studio example bundle from a locally owned mod archive."""
import argparse, hashlib, sys, zipfile
from pathlib import Path

MEMBER='abdata/studio/illusionmods/example_studio_item.unity3d'
SHA256='877740bae73b56f746fc761de20d0ae652ff16e7a028840a52ad06c06087cbed'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mod',required=True,help='Local [JustWaitAMinute] Porygon 1 v1.0.zipmod')
    p.add_argument('--output',required=True,help='New .unity3d file outside the game/model directory')
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    a=p.parse_args(argv)
    with zipfile.ZipFile(a.mod) as z:
        info=z.getinfo(MEMBER)
        if info.file_size!=92717: p.exit(1,'Unexpected template size; original archive not modified.\n')
        data=z.read(info)
    if hashlib.sha256(data).hexdigest()!=SHA256:
        p.exit(1,'Unknown template version; original archive not modified.\n')
    output=Path(a.output); output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f: f.write(data)
    print('Validated local template:',output)

if __name__=='__main__': main()
