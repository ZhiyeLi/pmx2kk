"""Offline original-KK card assembly from an explicitly supplied local base card.

Uses canonical face/body parameters and retained Sideloader references. New
source iris overlays are embedded; other base-card extension data is not cloned.
"""
import io,struct,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
import msgpack
from core import write_json,fingerprint

UAR='com.bepis.sideloader.universalautoresolver'
def unpack(data):return msgpack.unpackb(data,raw=False,strict_map_key=False)
def pack(value):return msgpack.packb(value,use_bin_type=True,use_single_float=True)

class Reader:
    def __init__(self,data):self.s=io.BytesIO(data)
    def read(self,n):
        if n<0 or n>100_000_000:raise ValueError('Invalid card length')
        data=self.s.read(n)
        if len(data)!=n:raise ValueError('Truncated card')
        return data
    def number(self,fmt='<i'):return struct.unpack(fmt,self.read(struct.calcsize(fmt)))[0]
    def blob(self):return self.read(self.number())
    def string(self):
        n=0
        for i in range(5):
            c=self.read(1)[0];n|=(c&127)<<(7*i)
            if c<128:return self.read(n).decode('utf8')
        raise ValueError('Invalid string')

def string(s):
    b=s.encode('utf8');n=len(b);head=bytearray()
    while n>=128:head.append((n&127)|128);n>>=7
    return bytes(head)+bytes([n])+b
def blob(b):return struct.pack('<i',len(b))+b

def png_size(data):
    if data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('基础卡必须是 PNG 人物卡')
    pos=8
    while pos+12<=len(data):
        n=struct.unpack('>I',data[pos:pos+4])[0];kind=data[pos+4:pos+8];pos+=12+n
        if pos>len(data):break
        if kind==b'IEND':return pos
    raise ValueError('Invalid PNG')

def read_card(path):
    data=Path(path).read_bytes();end=png_size(data);reader=Reader(data[end:])
    if reader.number()!=100 or reader.string()!='【KoiKatuChara】':raise ValueError('仅支持原版 KK 人物卡')
    version=reader.string();face=reader.blob();header=unpack(reader.blob());size=reader.number('<q');payload=reader.read(size)
    if reader.s.read():raise ValueError('不支持带未知尾部数据的基础卡')
    blocks={}
    for b in header['lstInfo']:
        if b['pos']<0 or b['size']<0 or b['pos']+b['size']>len(payload):raise ValueError('Invalid card block')
        blocks[b['name']]=payload[b['pos']:b['pos']+b['size']]
    return dict(png=data[:end],version=version,face_png=face,header=header,blocks=blocks)

def write_card(card,path):
    payload=bytearray()
    for row in card['header']['lstInfo']:
        b=card['blocks'][row['name']];row['pos']=len(payload);row['size']=len(b);payload.extend(b)
    result=card['png']+struct.pack('<i',100)+string('【KoiKatuChara】')+string(card['version'])+blob(card['face_png'])+blob(pack(card['header']))+struct.pack('<q',len(payload))+payload
    Path(path).write_bytes(result)

def create_card(r,job,out):
    card=read_card(r['base_card']);blocks=card['blocks'];parameter=unpack(blocks['Parameter'])
    if parameter.get('sex')!=1:raise ValueError('第一版需要原版 KK 女性基础卡')
    custom=Reader(blocks['Custom']);face=unpack(custom.blob());body=unpack(custom.blob());hair=unpack(custom.blob());ids=r['identity']['ids']
    face['headId']=ids['face'];hair['parts'][1]['id']=ids['hair']
    # The mesh was fitted to a canonical head; borrowing another character's
    # sliders invalidates that fit. Source proportions are represented by geometry.
    face['shapeValueFace']=[.5]*len(face['shapeValueFace'])
    body['shapeValueBody']=[.5]*len(body['shapeValueBody'])
    face.update(pupilWidth=.9,pupilHeight=.9,pupilX=.25,pupilY=.5,eyelineColor=[.12,.10,.12,1.],eyebrowColor=[.32,.29,.32,1.])
    for i,side in enumerate(['l','r']):
        face['pupil'][i].update(id=ids['iris_'+side],baseColor=[1.,1.,1.,1.],subColor=[1.,1.,1.,1.],gradBlend=0.)
    for k in ['hlUpColor','hlDownColor','lipLineColor','moleColor']:face[k][-1]=0.
    for k in ['cheekColor','eyeshadowColor','lipColor']:face['baseMakeup'][k][-1]=0.
    hair['parts'][1].update(pos=[0.,0.,0.],rot=[0.,0.,0.],scl=[1.,1.,1.],length=0.)
    for k in ['baseColor','startColor','endColor']:hair['parts'][1][k]=[1.,1.,1.,1.]
    hair['parts'][1]['noShake']=r['settings']['hair_physics']=='STATIC'
    blocks['Custom']=b''.join(blob(pack(x)) for x in [face,body,hair])
    old_ext=unpack(blocks.get('KKEx',pack({})));old_info=old_ext.get(UAR,[0,{}])[1].get('info',[])
    retained=[]
    for b in old_info:
        info=unpack(b);prop=info['Property']
        if prop in ['ChaFileFace.headId','ChaFileFace.Pupil1','ChaFileFace.Pupil2','ChaFileHair.HairFront'] or prop.startswith('outfit'):continue
        retained.append(b)
    def ref(kind,prop,category):
        return pack(dict(ModID=r['identity']['guid'],Slot=ids[kind],LocalSlot=ids[kind],Property=prop,CategoryNo=category,Author='Local PMX adaptation',Website=None,Name=r['name']+' pmx2KK'))
    refs=retained+[ref('face','ChaFileFace.headId',100),ref('hair','ChaFileHair.HairFront',102)]
    refs.extend([ref('iris_l','ChaFileFace.Pupil1',408),ref('iris_r','ChaFileFace.Pupil2',408)])
    coords=unpack(blocks['Coordinate']);converted=[]
    for index,data in enumerate(coords):
        c=Reader(data);clothes=unpack(c.blob());accessories=unpack(c.blob());enabled=c.read(1);makeup=c.blob()
        for i,part in enumerate(clothes['parts']):part['id']=ids['outfit'] if i==0 else 0
        for part in accessories['parts']:part['type']=120;part['id']=0
        converted.append(blob(pack(clothes))+blob(pack(accessories))+b'\x00'+blob(makeup))
        refs.append(ref('outfit',f'outfit{index}.ChaFileClothes.ClothesTop',105))
    blocks['Coordinate']=pack(converted);parameter.update(lastname='',firstname=r['name'],nickname=r['name']);blocks['Parameter']=pack(parameter)
    state=unpack(blocks['Status']);state.update(coordinateType=0,backCoordinateType=0,clothesState=bytes(9),mouthOpenMax=0.,eyesOpenMax=1.);blocks['Status']=pack(state)
    # Existing OverlayMods applies RGB after KK's grayscale iris recoloring.
    # EyeOver follows the native iris UV motion and needs no custom runtime DLL.
    blocks['KKEx']=pack({UAR:[0,{'info':refs}], 'KSOX':[1,{
        'EyeOverL':(job/'iris-L.png').read_bytes(),'EyeOverR':(job/'iris-R.png').read_bytes()}]})
    if not any(x['name']=='KKEx' for x in card['header']['lstInfo']):card['header']['lstInfo'].append(dict(name='KKEx',version='3',pos=0,size=0))
    card['png']=(job/'preview-front.png').read_bytes();card['face_png']=b''
    path=out/(r['identity']['key']+'-native.png');write_card(card,path)
    # Reparse before reporting success; reference resolution is tested separately in KK.
    check=read_card(path);assert len(unpack(check['blocks']['Coordinate']))==len(coords)
    dependencies=sorted({unpack(b)['ModID'] for b in retained}|{'KSOX'})
    write_json(out/'card.json',dict(path=str(path),sha256=fingerprint(path),base_card_sha256=fingerprint(r['base_card']),retained_mod_dependencies=dependencies,game_verified=False,thumbnail='Blender geometry preview; KK eye shaders are evaluated in-game'))
    return path
