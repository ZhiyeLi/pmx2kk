"""Create Sideloader zipmods without shipping game data in the add-on itself."""
import sys,csv,io,zipfile
from pathlib import Path
from xml.sax.saxutils import escape
from core import *
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
import msgpack

def package(r,job,cache):
    key=r['identity']['key'];guid=r['identity']['guid'];ids=r['identity']['ids']
    schemas=[msgpack.unpackb(p.read_bytes(),raw=False,strict_map_key=False) for p in (cache/'lists').glob('*.TextAsset')]
    def source(category,index):
        s=next(x for x in schemas if x['categoryNo']==category)
        row=s['dictList'].get(index,s['dictList'].get(str(index)))
        if row is None:raise ValueError('Missing KK list template')
        return s,dict(zip(s['lstKey'],row))
    out=job/'output';out.mkdir(exist_ok=True);path=out/(key+'-native.zipmod')
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        manifest=f'<manifest schema-ver="1"><guid>{guid}</guid><name>{escape(r["name"])} pmx2KK</name><version>{VERSION}</version><author>Local PMX adaptation</author><description>Local conversion. Original source permissions apply.</description></manifest>'
        z.writestr('manifest.xml',manifest)
        for kind,category in [('hair',102),('outfit',105),('face',100)]:
            bundle=f'chara/pmx2kk/{key}/{kind}.unity3d'
            if kind=='hair':
                s=dict(lstKey=['ID','Kind','Possess','Name','MainManifest','MainAB','MainData','ThumbAB','ThumbTex'],filePath='Assets/Illusion/assetbundle/chara/list/characustom/00/bo_hair_f_00.bytes')
                row=dict(Kind='0',MainManifest='abdata')
            else:s,row=source(category,4 if kind=='outfit' else 0)
            row.update(ID=str(ids[kind]),Possess='99',Name=r['name']+' '+kind,MainAB=bundle,MainData=f'p_{key}_{kind}',ThumbAB=bundle,ThumbTex='thumbnail')
            if kind=='face':row.update(MainTexAB=bundle,MainTex='face_albedo',ColorMaskAB=bundle,ColorMaskTex='face_color_mask')
            if kind=='outfit':row.update(Coordinate='2',NotBra='1',OverBodyMaskAB=bundle,OverBodyMask='body_mask',OverBraMaskAB='0',OverBraMask='0',MainTex='0',ColorMaskTex='0')
            text=io.StringIO();text.write(str(category)+'\n0\n'+s['filePath']+'\n');writer=csv.writer(text,lineterminator='\n');writer.writerow(s['lstKey']);writer.writerow([row[k] for k in s['lstKey']])
            z.writestr(f'abdata/list/characustom/pmx2kk/{key}/{kind}.csv',text.getvalue())
            z.write(job/'package/abdata'/bundle,'abdata/'+bundle)
        s,base=source(408,0)
        text=io.StringIO();text.write('408\n0\n'+s['filePath']+'\n');writer=csv.writer(text,lineterminator='\n');writer.writerow(s['lstKey'])
        for side in ['L','R']:
            row=base.copy();row.update(ID=str(ids['iris_'+side.lower()]),Possess='99',Name=r['name']+' iris '+side,MainAB=f'chara/pmx2kk/{key}/face.unity3d',EyeTex='iris_'+side,ThumbAB=f'chara/pmx2kk/{key}/face.unity3d',ThumbTex='iris_'+side)
            writer.writerow([row[k] for k in s['lstKey']])
        z.writestr(f'abdata/list/characustom/pmx2kk/{key}/iris.csv',text.getvalue())
        z.writestr('CONVERSION.txt','Native KK approximation. Face preserves KK topology and expressions. Outfit is one top slot. See local recipe for settings.\nSource: '+Path(r['source']).name)
    write_json(out/'delivery.json',dict(zipmod=str(path),sha256=fingerprint(path),identity=r['identity'],game_verified=False))
    if r.get('base_card'):
        from card import create_card
        create_card(r,job,out)
    return path
