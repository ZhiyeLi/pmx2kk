"""Create reproducible source-only release ZIPs using explicit allowed files."""
import argparse, hashlib, sys, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ADDON=['__init__.py','core.py','worker.py','convert.py','head.py','appearance.py','packaging.py','card.py',
       'backend/templates.ps1','backend/build.ps1','backend/runtime.ps1','README.txt',
       'vendor/msgpack/__init__.py','vendor/msgpack/exceptions.py','vendor/msgpack/ext.py',
       'vendor/msgpack/fallback.py','vendor/msgpack/LICENSE']
LEGAL=['LICENSE','THIRD_PARTY_NOTICES.md','licenses/Apache-2.0.txt']

def archive(path, entries):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for src,name in sorted(entries,key=lambda x:x[1]):
            info=zipfile.ZipInfo(name,date_time=(2026,10,30,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o100644 << 16
            # Every allowlisted input is UTF-8 text; canonical LF also makes
            # Windows and Git checkouts produce identical archives.
            z.writestr(info,src.read_text(encoding='utf8').encode('utf8'))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',default=str(ROOT/'dist'))
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    out=Path(p.parse_args(argv).output);out.mkdir(parents=True,exist_ok=True)
    archive(out/'pmx2KK-0.2.1.zip',[(ROOT/'pmx2kk'/s,'pmx2kk/'+s) for s in ADDON]+[(ROOT/s,'pmx2kk/'+s) for s in LEGAL])
    examples=['examples/README.md']+[f'examples/{s}/preset.json' for s in ('theresa','demon-lord','leviathan')]
    docs=['README.md','docs/SETUP.md','docs/USER_GUIDE.md','docs/TROUBLESHOOTING.md','docs/RELEASE-v0.2.1.md',
          'docs/ARCHITECTURE.md','docs/VALIDATION.md','docs/validation-summary.json']
    extras=examples+docs+LEGAL+['tools/apply_example.py','tools/extract_studio_template.py']
    archive(out/'pmx2KK-0.2.1-examples-and-docs.zip',[(ROOT/s,s) for s in extras])
    lines=[]
    for name in ('pmx2KK-0.2.1.zip','pmx2KK-0.2.1-examples-and-docs.zip'):
        path=out/name;lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+name)
        print(name,path.stat().st_size)
    (out/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf8')

if __name__=='__main__':main()
