"""Apply an asset-free preset to an inspected, idle pmx2KK job (Python 3.10+)."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROLES = {'AUTO','BODY','HAIR','HEAD_ACCESSORY','FACE','IRIS','FACE_DETAIL','IGNORE','SPLIT_HOOD'}
SETTINGS = {'import_scale','body_width','face_strength','hair_scale','hair_offset','hood_cut',
            'hair_physics','damping','stiffness','elasticity','inertia','outline','simplify_large_meshes'}

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def apply(preset_path, recipe_path):
    preset = read(preset_path); recipe_path = Path(recipe_path).resolve(); r = read(recipe_path)
    if preset.get('schema') != 'pmx2kk-example-1' or r.get('schema') != 1:
        raise ValueError('Unsupported preset or recipe schema')
    if preset.get('addon_version') != '0.2.1' or r.get('version') != '0.2.1':
        raise ValueError('Inspect the PMX with pmx2KK 0.2.1 first')
    if not r['identity']['key'].endswith('n21'):
        raise ValueError('Old job namespace; inspect with 0.2.1 first')
    source = Path(r['source'])
    h = hashlib.sha256()
    with source.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    digest = h.hexdigest()
    if digest != preset['source']['sha256'] or digest != r['identity']['source_sha256']:
        raise ValueError('Source SHA256 mismatch: use the exact model version, or classify manually')
    inspect = read(recipe_path.parent/'inspect.json')
    if inspect['identity']['source_sha256'] != digest:
        raise ValueError('Inspection belongs to a different PMX')
    expected = [(m['id'],m['name']) for m in preset['materials']]
    actual = [(m['id'],m['name']) for m in inspect['materials']]
    if actual != expected or len({m[0] for m in expected}) != len(expected):
        raise ValueError('Material IDs/names differ; inspect and classify manually')
    if any(m['role'] not in ROLES for m in preset['materials']):
        raise ValueError('Unknown material role')
    if sum(m['role']=='FACE' for m in preset['materials']) != 1:
        raise ValueError('Exactly one FACE material is required')
    if set(preset['settings']) != SETTINGS:
        raise ValueError('Unexpected or missing setting')
    if abs(r['settings']['import_scale']-preset['settings']['import_scale']) > 1e-7:
        raise ValueError('Import scale differs; inspect with the preset scale first')
    r['name']=preset['name']; r['materials']={m['id']:m['role'] for m in preset['materials']}
    r['settings']=preset['settings']; r['bone_overrides']=preset['bone_overrides']; r['confirmed']=False
    backup=recipe_path.with_name('recipe-before-example-'+str(time.time_ns())+'.json')
    backup.write_bytes(recipe_path.read_bytes())
    temp=recipe_path.with_name('recipe-example-'+str(time.time_ns())+'.tmp')
    try:
        temp.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        temp.replace(recipe_path)
    finally:
        if temp.exists(): temp.unlink()
    return backup

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preset',required=True); p.add_argument('--recipe',required=True)
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    a=p.parse_args(argv)
    try: backup=apply(a.preset,a.recipe)
    except (ValueError,KeyError,OSError) as e: p.exit(1,str(e)+'\n')
    print('Applied. Backup:',backup)
    print('Reload recipe.json in Blender, review materials/bones, then confirm. Do not re-inspect unless needed.')

if __name__=='__main__': main()
