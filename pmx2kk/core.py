"""Blender-independent recipes, identity, classification and job utilities."""
import hashlib,json,re,os,subprocess,time,unicodedata
from pathlib import Path

VERSION='0.2.1'
ROLES=('AUTO','BODY','HAIR','HEAD_ACCESSORY','FACE','IRIS','FACE_DETAIL','IGNORE','SPLIT_HOOD')

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)

def fingerprint(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def identity(source):
    digest=fingerprint(source);key='p'+digest[:12]+'n21'
    # Unique bundle/CAB/GUID namespace. Local list IDs are in the Sideloader
    # namespace and remain stable when the same source is rebuilt.
    return dict(key=key,guid='local.pmx2kk.'+key,source_sha256=digest,
                ids={n:100000+int(digest[i:i+6],16) for n,i in [('hair',0),('outfit',6),('face',12),('iris_l',18),('iris_r',24)]})

def new_recipe(source,output,game,sb3,mmd='',shader='',base_card=''):
    source=Path(source).resolve();output=Path(output).resolve()
    if not source.is_file() or source.suffix.lower()!='.pmx':raise ValueError('请选择存在的 PMX 文件')
    if output==source.parent or output in source.parents:raise ValueError('输出目录不能是源模型目录或其上级；请选择单独的工作目录')
    return dict(schema=1,version=VERSION,source=str(source),output=str(output),game=str(Path(game).resolve()),
                sb3=str(Path(sb3).resolve()),mmd=str(mmd),shader_template=str(shader),base_card=str(base_card),
                name=source.stem,identity=identity(source),materials={},bone_overrides={},
                settings=dict(import_scale=.08,body_width=1.0,face_strength=1.0,hair_scale=1.0,
                hair_offset=[0,0,0],hood_cut=1.0,hair_physics='STATIC',damping=.55,stiffness=.85,
                elasticity=.35,inertia=.8,outline=0.0,simplify_large_meshes=False),confirmed=False)

def validate_recipe(r,building=False):
    if r.get('schema')!=1:raise ValueError('配置版本不支持')
    if fingerprint(r['source'])!=r['identity']['source_sha256']:raise ValueError('源 PMX 已改变，请重新检查并创建配置')
    if building:
        if r.get('version')!=VERSION or 'iris_l' not in r['identity']['ids']:
            raise ValueError('旧版配方需要重新“检查 PMX”，建立 '+VERSION+' 独立任务后再转换')
        if not r.get('confirmed'):raise ValueError('请先确认部件和骨骼映射')
        required=['abdata/chara/oo_base.unity3d','abdata/chara/bo_head_00.unity3d',
                  'abdata/chara/bo_hair_f_08.unity3d','abdata/chara/co_top_10.unity3d','abdata/list/characustom/00.unity3d']
        for p in required:
            if not (Path(r['game'])/p).is_file():raise ValueError('缺少原版 KK 资源：'+p)
        for p in ['SB3Utility.dll','plugins/UnityPlugin.dll','plugins/SB3UtilityFBX.dll']:
            if not (Path(r['sb3'])/p).is_file():raise ValueError('SB3Utility 路径无效：'+p)
        if not Path(r['shader_template']).is_file():raise ValueError('请指定本地 Studio 材质模板 bundle')
        if r.get('base_card') and not list((Path(r['game'])/'BepInEx/plugins').rglob('KK_OverlayMods.dll')):
            raise ValueError('原色瞳孔人物卡需要 KK_OverlayMods（KSOX）；请在 KK 安装该插件后生成')

def job_path(r):return Path(r['output'])/r['identity']['key']

def status(job,phase,message,progress=0,**extra):
    write_json(Path(job)/'status.json',dict(phase=phase,message=message,progress=progress,time=time.time(),**extra))

def run(cmd,log,env=None):
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    with open(log,'a',encoding='utf8') as f:
        process=subprocess.run([str(x) for x in cmd],stdout=f,stderr=subprocess.STDOUT,env=env,creationflags=flags)
    if process.returncode:raise RuntimeError('处理失败，详见日志：'+str(log))

def canonical(name):
    return unicodedata.normalize('NFKC',name).replace(' ', '').replace('_','').lower()

def bone_targets():
    aliases={}
    def put(target,*names):
        for n in names:aliases[canonical(n)]=target
    for src,dst,eng in [('腰','hips','hips'),('下半身','waist01','lowerbody'),('上半身','spine01','upperbody'),
        ('上半身2','spine03','upperbody2'),('首','neck','neck'),('頭','head','head')]:put('cf_j_'+dst,src,eng,'cf_j_'+dst)
    for s,jp,en in [('L','左','left'),('R','右','right')]:
        for src,dst,eng in [('肩','shoulder','shoulder'),('腕','arm00','arm'),('ひじ','forearm01','elbow'),
            ('肘','forearm01','elbow'),('手首','hand','wrist'),('足','thigh00','leg'),('足D','thigh00','legd'),
            ('ひざ','leg01','knee'),('膝','leg01','knee'),('ひざD','leg01','kneed'),('足首','foot','ankle'),
            ('足首D','foot','ankled'),('足先EX','toes','toeex'),('つま先','toes','toe')]:
            put('cf_j_'+dst+'_'+s,src+'.'+s,jp+src,eng+'.'+s,en+eng,'cf_j_'+dst+'_'+s)
        for src,dst in [('親指','thumb'),('人指','index'),('人差指','index'),('中指','middle'),('薬指','ring'),('小指','little')]:
            for i in range(1,4):
                p=i-1 if dst=='thumb' else i
                put('cf_j_'+dst+'0'+str(i)+'_'+s,src+'０１２３'[p]+'.'+s,src+str(p)+'.'+s,
                    jp+src+'０１２３'[p],jp+src+str(p),en+dst+str(i),'cf_j_'+dst+'0'+str(i)+'_'+s)
    return aliases

ALIASES=bone_targets()
REQUIRED=['cf_j_'+n for n in ['waist01','spine01','spine03','neck','head']]+[
    'cf_j_'+n+'_'+s for s in ['L','R'] for n in ['arm00','forearm01','hand','thigh00','leg01','foot']]

def map_bones(bones,overrides=None):
    result={};overrides=overrides or {}
    for b in bones:
        if b['name'] in overrides:
            if overrides[b['name']]:result[b['name']]=overrides[b['name']]
            continue
        for name in [b['name'],b.get('original','')]:
            if canonical(name) in ALIASES:result[b['name']]=ALIASES[canonical(name)];break
    # Prefer PMX deform D bones over control bones for fitting landmarks.
    anchors={}
    for name,target in result.items():
        if target not in anchors or 'D.' in name or name.endswith('D'):anchors[target]=name
    return result,anchors,[n for n in REQUIRED if n not in anchors]

def classify_material(name,head_fraction):
    n=name.lower()
    if n in ['eye','eyes','瞳','瞳孔'] or any(x in n for x in ['眼睛','瞳孔','iris']):
        if not any(x in n for x in ['高光','highlight','白','white']):return 'IRIS',.9
    if any(x in n for x in ['发带','头带','头饰','耳环','耳飾','兜帽','halo','光环','角']):return 'HEAD_ACCESSORY',.75
    if any(x in n for x in ['髪','发','hair','まつ毛','前髮','後髮']) and '发光' not in n:
        return ('FACE_DETAIL' if any(x in n for x in ['まつ毛','睫','eyelash']) else 'HAIR',.95)
    if any(x in n for x in ['睫','眉','眼','目','瞳','歯','牙','舌','口内','口腔','eye','brow','teeth','mouth','表情','expression']):return 'FACE_DETAIL',.95
    if any(x in n for x in ['顔','脸','face']) or n=='head':return 'FACE',.95
    if any(x in n for x in ['帽','头饰','頭飾','halo','光环','角','耳饰']):return 'HEAD_ACCESSORY',.75
    if any(x in n for x in ['body','体','皮肤','肌','skin']):return 'BODY',.8
    if head_fraction>.85:return 'HEAD_ACCESSORY',.35
    return 'BODY',.55
