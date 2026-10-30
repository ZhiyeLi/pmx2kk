"""Tests for safe preset application; no Blender or third-party assets needed."""
import copy, hashlib, importlib.util, json, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('apply_example',ROOT/'tools/apply_example.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)

class PresetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.source=self.root/'fixture.pmx'
        self.source.write_bytes(b'synthetic source; not a model')
        self.digest=hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.preset=copy.deepcopy(helper.read(ROOT/'examples/theresa/preset.json'))
        self.preset['source']['sha256']=self.digest
        self.recipe={'schema':1,'version':'0.2.1','source':str(self.source),
            'identity':{'key':'p'+self.digest[:12]+'n21','source_sha256':self.digest},
            'game':'local game path','output':'local output path','settings':{'import_scale':.08},
            'confirmed':True,'materials':{}}
        self.inspect={'identity':{'source_sha256':self.digest},'materials':self.preset['materials']}
        self.pp=self.root/'preset.json';self.rp=self.root/'recipe.json';self.ip=self.root/'inspect.json'
        self.save()

    def save(self):
        for p,v in [(self.pp,self.preset),(self.rp,self.recipe),(self.ip,self.inspect)]:
            p.write_text(json.dumps(v,ensure_ascii=False),encoding='utf8')

    def reject(self,match):
        original=self.rp.read_bytes()
        with self.assertRaisesRegex(ValueError,match):helper.apply(self.pp,self.rp)
        self.assertEqual(original,self.rp.read_bytes())
        self.assertEqual([],list(self.root.glob('recipe-before-example-*')))

    def test_applies_settings_preserves_local_identity_and_requires_review(self):
        original=self.rp.read_bytes();backup=helper.apply(self.pp,self.rp);r=helper.read(self.rp)
        self.assertEqual(original,backup.read_bytes())
        for key in ('source','identity','game','output'):self.assertEqual(self.recipe[key],r[key])
        self.assertEqual(self.preset['settings'],r['settings']);self.assertFalse(r['confirmed'])
        self.assertEqual(len(self.preset['materials']),len(r['materials']))

    def test_changed_source_is_not_written(self):
        self.source.write_bytes(b'changed');self.reject('SHA256')

    def test_wrong_materials_are_not_written(self):
        self.inspect=copy.deepcopy(self.inspect);self.inspect['materials'][0]['name']='different';self.save()
        self.reject('Material IDs')

    def test_old_recipe_is_not_written(self):
        self.recipe['version']='0.2.0';self.save();self.reject('0.2.1')

    def test_changed_import_scale_requires_inspect(self):
        self.recipe['settings']['import_scale']=.1;self.save();self.reject('Import scale')

    def test_wrong_inspection_is_not_written(self):
        self.inspect['identity']['source_sha256']='0'*64;self.save();self.reject('different PMX')

    def test_shipped_presets_have_one_face_and_unique_material_ids(self):
        paths=list((ROOT/'examples').glob('*/preset.json'));self.assertEqual(3,len(paths))
        for path in paths:
            p=helper.read(path)
            self.assertEqual(64,len(p['source']['sha256']))
            self.assertEqual(1,sum(m['role']=='FACE' for m in p['materials']))
            self.assertEqual(len(p['materials']),len({m['id'] for m in p['materials']}))
            self.assertEqual(helper.SETTINGS,set(p['settings']))

if __name__=='__main__':unittest.main()
