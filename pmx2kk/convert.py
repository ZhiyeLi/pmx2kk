"""Native KK fitting in an isolated Blender process; source assets are read only."""
import sys,os,math,shutil,hashlib,time
from pathlib import Path
import bpy,bmesh
from mathutils import Vector,Matrix,Quaternion
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from core import *

HERE=Path(__file__).resolve().parent

def prepare(r,job):
    files=[Path(r['game'])/('abdata/chara/'+n+'.unity3d') for n in ['oo_base','bo_head_00','bo_hair_f_08','co_top_10']]
    files.append(Path(r['game'])/'abdata/list/characustom/00.unity3d')
    stamp=str([(str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in files])+VERSION
    key=hashlib.sha256(stamp.encode()).hexdigest()[:16]
    cache=Path(r['output'])/'_templates'/key
    if not (cache/'complete.json').exists():
        status(job,'running','首次提取本机 KK 模板',.08)
        run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',HERE/'backend/templates.ps1','-Recipe',job/'recipe.json','-Cache',cache],job/'templates.log')
        for label in ['body','hair','head','outfit','outfit_low']:
            if not (cache/label/'template.fbx').is_file():raise ValueError('模板提取失败：'+label)
        write_json(cache/'complete.json',dict(stamp=stamp))
    return cache

def bounds(obj):
    coords=[obj.matrix_world@v.co for v in obj.data.vertices]
    return [Vector([f(v[i] for v in coords) for i in range(3)]) for f in (min,max)]

def append_source(job):
    with bpy.data.libraries.load(str(job/'source.blend'),link=False) as (src,dst):
        dst.objects=[n for n in src.objects if n.startswith('pmx2kk_part_')]
    for o in dst.objects:bpy.context.scene.collection.objects.link(o)
    return {str(o['pmx2kk_id']):o for o in dst.objects}

def flatten(o,coords):
    o.parent=None;o.matrix_world=Matrix.Identity(4);o.shape_key_clear();o.modifiers.clear();o.vertex_groups.clear()
    for v,co in zip(o.data.vertices,coords):v.co=co

def join(parts,name,arm):
    if not parts:raise ValueError('没有 '+name+' 部件，请检查材质分类')
    bpy.ops.object.select_all(action='DESELECT')
    for o in parts:o.select_set(True)
    bpy.context.view_layer.objects.active=parts[0];bpy.ops.object.join();o=parts[0];o.name=name
    o.parent=arm;o.matrix_world=Matrix.Identity(4)
    mod=o.modifiers.new('KK native rig','ARMATURE');mod.object=arm
    bpy.context.view_layer.update();return o

def export(o,arm,path):
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);arm.select_set(True);bpy.context.view_layer.objects.active=arm
    bpy.ops.export_scene.fbx(filepath=str(path),global_scale=.01,use_selection=True,object_types={'MESH','ARMATURE'},
        add_leaf_bones=False,bake_anim=False,use_mesh_modifiers=False,axis_forward='-Z',axis_up='Y')

def mesh_limit(o,r):
    before=len(o.data.vertices)
    if before<=60000:return dict(before=before,after=before,simplified=False)
    if not r['settings'].get('simplify_large_meshes'):
        raise ValueError(f'{o.name} 有 {before} 顶点，超过原版 KK 单网格限制；请启用“允许简化超大网格”并检查结果，或先在源副本中减面')
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
    for _ in range(3):
        if len(o.data.vertices)<=55000:break
        mod=o.modifiers.new('KK vertex budget','DECIMATE');mod.ratio=50000/len(o.data.vertices)
        bpy.ops.object.modifier_apply(modifier=mod.name)
    if len(o.data.vertices)>55000:raise ValueError('减面仍超出顶点预算，请手动处理网格')
    # Decimation interpolates weights; normalize to the four influences supported
    # by this legacy pipeline before exporting.
    for v in o.data.vertices:
        weights=sorted([(g.group,g.weight) for g in v.groups if g.weight>1e-8],key=lambda x:-x[1])[:4]
        total=sum(w for _,w in weights)
        if total<=0:raise ValueError('减面产生未蒙皮顶点')
        for g in list(v.groups):o.vertex_groups[g.group].remove([v.index])
        for group,w in weights:o.vertex_groups[group].add([v.index],w/total,'REPLACE')
    return dict(before=before,after=len(o.data.vertices),simplified=True)

def trim(o,z,upper):
    bm=bmesh.new();bm.from_mesh(o.data)
    bmesh.ops.delete(bm,geom=[v for v in bm.verts if (v.co.z<z if upper else v.co.z>=z)],context='VERTS')
    bm.to_mesh(o.data);bm.free()

def fit_body(parts,r,job,report,arm,cache,head):
    source={b['name']:b for b in report['bones']};mapping,anchors,missing=map_bones(report['bones'],r['bone_overrides'])
    if missing:raise ValueError('缺少必需骨骼映射：'+', '.join(missing))
    target={b.name:arm.matrix_world@b.head_local for b in arm.data.bones}
    ends={'cf_j_spine01':'cf_j_spine03','cf_j_spine03':'cf_j_neck','cf_j_neck':'cf_j_head'}
    for side in ['L','R']:
        for a,b in [('shoulder','arm00'),('arm00','forearm01'),('forearm01','hand'),('hand','middle01'),('thigh00','leg01'),('leg01','foot')]:ends['cf_j_'+a+'_'+side]='cf_j_'+b+'_'+side
        for f in ['thumb','index','middle','ring','little']:
            for i in range(1,4):ends[f'cf_j_{f}0{i}_{side}']=f'cf_j_{f}0{i+1}_{side}'
    # Shoulder width is anatomical. Head pivot height is not a body-width scale.
    sa=Vector(source[anchors['cf_j_arm00_L']]['head']);sb=Vector(source[anchors['cf_j_arm00_R']]['head'])
    width=(target['cf_j_arm00_L']-target['cf_j_arm00_R']).length/max((sa-sb).length,.001)*r['settings']['body_width']
    transforms={};rots={}
    for name,dest in mapping.items():
        if dest not in target:raise ValueError('未知 KK 目标骨骼：'+dest)
        h=Vector(source[name]['head']);t=target[dest];wscale=width;q=Quaternion()
        if any(k in dest for k in ['hand_','thumb','index','middle','ring','little']):
            side=dest[-1];a='cf_j_index01_'+side;b='cf_j_little01_'+side
            if a in anchors and b in anchors:
                wscale=(target[a]-target[b]).length/max((Vector(source[anchors[a]]['head'])-Vector(source[anchors[b]]['head'])).length,.001)*r['settings']['body_width']
        linear=Matrix.Identity(3)*wscale
        end=ends.get(dest)
        if end and end in target:
            ep=source[anchors[end]]['head'] if end in anchors else source[name]['tail']
            v=Vector(ep)-h;w=target[end]-t
            if v.length>.001 and w.length>.001:
                q=v.rotation_difference(w);u=v.normalized();stretch=linear.copy()
                for i in range(3):
                    for j in range(3):stretch[i][j]+=(w.length/v.length-wscale)*u[i]*u[j]
                linear=q.to_matrix()@stretch
        transforms[name]=(h,t,linear);rots[name]=q
    for name,dest in mapping.items():
        if dest=='cf_j_head':
            h=Vector(source[name]['head']);transforms[name]=(h,head['linear']@h+head['offset']+target['cf_j_head'],head['linear'])
        if dest=='cf_j_neck':
            h=Vector(source[name]['head']);sh=Vector(source[anchors['cf_j_head']]['head'])
            t=target[dest];end=head['linear']@sh+head['offset']+target['cf_j_head'];v=sh-h;w=end-t
            if v.length>.001 and w.length>.001:
                q=v.rotation_difference(w);u=v.normalized();linear=Matrix.Identity(3)*width
                for i in range(3):
                    for j in range(3):linear[i][j]+=(w.length/v.length-width)*u[i]*u[j]
                transforms[name]=(h,t,q.to_matrix()@linear)
    for name,dest in mapping.items():
        if dest.startswith('cf_j_toes_'):transforms[name]=transforms[anchors['cf_j_foot_'+dest[-1]]]
    def mapped(n):
        original=n;seen=set()
        while n not in mapping and n in source and n not in seen:
            seen.add(n);n=source[n]['parent']
        if n not in mapping:raise ValueError('未映射的变形骨骼：'+str(original)+'，请在骨骼覆盖中指定附件跟随的 KK 骨骼，或忽略相应部件')
        return n
    fitted=[];ignored={};used=set();vertex_count=0
    for key,o in parts.items():
        role=r['materials'][key]
        if role not in ['BODY','SPLIT_HOOD']:continue
        if role=='SPLIT_HOOD':
            o=o.copy();o.data=o.data.copy();bpy.context.scene.collection.objects.link(o)
        world=o.matrix_world.copy();groups=[g.name for g in o.vertex_groups];coords=[];weights=[];original_z=[]
        for v in o.data.vertices:
            p=world@v.co;original_z.append(p.z);co=Vector();row={};total=0
            for g in v.groups:
                n=groups[g.group]
                if n not in source:ignored[n]=ignored.get(n,0)+1;continue
                if g.weight<1e-8:continue
                ancestor=mapped(n);h,t,l=transforms[ancestor];point=t+l@(p-h)
                if n not in mapping and mapping[ancestor] in ['cf_j_spine01','cf_j_spine03','cf_j_waist01','cf_j_hips']:
                    a=n
                    while source[a]['parent'] not in mapping:a=source[a]['parent']
                    ah=Vector(source[a]['head']);point=t+l@(ah-h)+width*(p-ah)
                co+=point*g.weight;total+=g.weight;dest=mapping[ancestor];row[dest]=row.get(dest,0)+g.weight
            if total<1e-6:raise ValueError(f'{o.name} 顶点 {v.index} 没有有效骨骼权重')
            coords.append(co/total);row={n:w/total for n,w in row.items()};weights.append(row)
        flatten(o,coords)
        for n in sorted({n for row in weights for n in row}):o.vertex_groups.new(name=n)
        for i,row in enumerate(weights):
            for n,w in row.items():o.vertex_groups[n].add([i],w,'REPLACE');used.add(n)
        if role=='SPLIT_HOOD':
            bm=bmesh.new();bm.from_mesh(o.data);bm.verts.ensure_lookup_table()
            bmesh.ops.delete(bm,geom=[bm.verts[i] for i,z in enumerate(original_z) if z>=r['settings']['hood_cut']],context='VERTS');bm.to_mesh(o.data);bm.free()
        vertex_count+=len(o.data.vertices);fitted.append(o)
    for label in ['outfit','outfit_low']:
        allowed={b['name'] for b in read_json(cache/label/'frames.json')}
        if used-allowed:raise ValueError('服装模板缺少骨骼：'+str(used-allowed))
    outfit=join(fitted,'pmx2kk_outfit',arm)
    budget=mesh_limit(outfit,r)
    export(outfit,arm,job/'outfit.fbx');shutil.copy2(job/'outfit.fbx',job/'outfit_low.fbx')
    return outfit,dict(vertices=len(outfit.data.vertices),vertex_budget=budget,width_scale=width,ignored_non_bone_groups=ignored,used_bones=sorted(used),bone_mapping=mapping)

def fit_head(parts,r,job,nface,nhair,head):
    linear=head['linear'];offset=head['offset']
    hairarm=next(m.object for m in nhair.modifiers if m.type=='ARMATURE')
    tree=KDTree(len(nhair.data.vertices))
    for v in nhair.data.vertices:tree.insert(nhair.matrix_world@v.co,v.index)
    tree.balance();fitted=[]
    for key,o in parts.items():
        role=r['materials'][key]
        if role not in ['HAIR','HEAD_ACCESSORY','SPLIT_HOOD']:continue
        scale=r['settings']['hair_scale'];pivot=(Vector(head['report']['target_eyes'][0])+Vector(head['report']['target_eyes'][1]))*.5
        hlinear=linear*scale;hoff=pivot+(offset-pivot)*scale+Vector(r['settings']['hair_offset'])
        coords=[hlinear@(o.matrix_world@v.co)+hoff for v in o.data.vertices];flatten(o,coords)
        if role=='SPLIT_HOOD':trim(o,r['settings']['hood_cut']*hlinear[2][2]+hoff.z,True)
        for g in nhair.vertex_groups:o.vertex_groups.new(name=g.name)
        anchor=o.vertex_groups.get('cf_J_hairF_top') or o.vertex_groups.new(name='cf_J_hairF_top')
        for v in o.data.vertices:
            dynamic=0
            if role=='HAIR' and r['settings']['hair_physics']=='FRINGE':
                dynamic=max(0,min(1,(.15-v.co.z)/.13))*max(0,min(1,(.025-v.co.y)/.06))
                # Template fringe physics is deliberately limited to the head area.
                if v.co.z<-.025 or abs(v.co.x)>.15:dynamic=0
            weights={}
            if dynamic:
                for _,idx,dist in tree.find_n(v.co,4):
                    factor=1/max(dist,.0001)**2
                    for g in nhair.data.vertices[idx].groups:weights[g.group]=weights.get(g.group,0)+g.weight*factor
                best=sorted(weights.items(),key=lambda x:-x[1])[:3];total=sum(w for _,w in best)
                for gid,w in best:o.vertex_groups[gid].add([v.index],dynamic*w/total,'REPLACE')
            anchor.add([v.index],1-dynamic,'ADD')
        fitted.append(o)
    hair=join(fitted,'pmx2kk_hair',hairarm);hairbudget=mesh_limit(hair,r);export(hair,hairarm,job/'hair.fbx')
    from head import sculpt
    face_report=sculpt(nface,head,r['settings']['face_strength'])
    nface.name='cf_O_face';arm=next(m.object for m in nface.modifiers if m.type=='ARMATURE')
    export(nface,arm,job/'face.fbx')
    return hair,dict(normalization=head['report'],physics=r['settings']['hair_physics'],vertex_budget=hairbudget),face_report

def render_preview(job,objects):
    scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE_NEXT';scene.render.resolution_x=640;scene.render.resolution_y=800;scene.render.resolution_percentage=100
    if scene.world is None:scene.world=bpy.data.worlds.new('pmx2KK World')
    scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False;scene.world.color=(.18,.18,.18)
    scene.view_settings.view_transform='Standard'
    for o in bpy.data.objects:o.hide_render=o not in objects
    coords=[o.matrix_world@v.co for o in objects if o.type=='MESH' for v in o.data.vertices]
    lo=Vector([min(v[i] for v in coords) for i in range(3)]);hi=Vector([max(v[i] for v in coords) for i in range(3)]);center=(lo+hi)/2
    data=bpy.data.cameras.new('pmx2KK preview');camera=bpy.data.objects.new('pmx2KK preview',data);scene.collection.objects.link(camera);scene.camera=camera
    data.type='ORTHO';data.ortho_scale=max((hi.z-lo.z)*1.15,(hi.x-lo.x)*1.4)
    for name,loc,power,size in [('key',(-3,-4,5),700,5),('fill',(3,1,4),500,4)]:
        light=bpy.data.lights.new(name,'AREA');light.energy=power;light.shape='DISK';light.size=size
        o=bpy.data.objects.new(name,light);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(center-o.location).to_track_quat('-Z','Y').to_euler()
    for name,direction in [('front',(0,-4,0)),('side',(4,0,0)),('back',(0,4,0))]:
        camera.location=center+Vector(direction);camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath=str(job/('preview-'+name+'.png'));bpy.ops.render.render(write_still=True)

def convert(r,job,stage):
    report=read_json(job/'inspect.json')
    if set(r['materials'])!={m['id'] for m in report['materials']}:raise ValueError('部件列表已变化，请重新检查')
    if any(v not in ROLES or v=='AUTO' for v in r['materials'].values()):raise ValueError('请确认所有部件分类')
    cache=prepare(r,job);status(job,'running','拟合骨骼与原生表情',.25)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    refs={}
    for label in ['hair','body','head']:
        before=set(bpy.data.objects);bpy.ops.import_scene.fbx(filepath=str(cache/label/'template.fbx'),use_anim=False,global_scale=100)
        refs[label]=list(set(bpy.data.objects)-before)
    bodyarm=next(o for o in refs['body'] if o.type=='ARMATURE')
    nface=next(o for o in refs['head'] if o.type=='MESH' and o.name.startswith('cf_O_face_'))
    nhair=next(o for o in refs['hair'] if o.type=='MESH')
    parts=append_source(job);textures={}
    # Load the original facial atlases as well; these were discarded in v0.1.
    for m in report['materials']:
        if r['materials'][m['id']] not in ['FACE','IRIS','FACE_DETAIL']:continue
        if m['texture'] and Path(m['texture']).is_file():
            image=bpy.data.images.load(m['texture'],check_existing=False)
            for node in parts[m['id']].data.materials[0].node_tree.nodes:
                if node.type=='TEX_IMAGE':node.image=image
    from head import normalize
    head=normalize(parts,r,report,nface,refs['head'])
    (job/'textures').mkdir(exist_ok=True)
    for key,o in parts.items():
        if r['materials'][key] in ['FACE','IRIS','FACE_DETAIL','IGNORE']:continue
        mat=o.data.materials[0];mat.name='pmx2kk_mat_'+key
        image=next((n.image for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image),None)
        texture=next(m['texture'] for m in report['materials'] if m['id']==key)
        if texture and Path(texture).is_file():
            image=bpy.data.images.load(texture,check_existing=False)
            for node in mat.node_tree.nodes:
                if node.type=='TEX_IMAGE':node.image=image
        elif image is not None and not image.has_data:
            raise ValueError('贴图丢失：'+str(texture))
        if image is None:
            image=bpy.data.images.new('solid_'+key,4,4);image.generated_color=tuple(mat.diffuse_color)
        # Force lazy image data to load before changing the destination path.
        _=image.pixels[0]
        path=job/'textures'/(mat.name+'.png');image.filepath_raw=str(path);image.file_format='PNG';image.save();image.pack();textures[mat.name]=str(path)
    outfit,bodyreport=fit_body(parts,r,job,report,bodyarm,cache,head)
    hair,hairreport,facereport=fit_head(parts,r,job,nface,nhair,head)
    status(job,'running','转移原始面部与左右瞳孔纹理',.48)
    from appearance import transfer_face,transfer_iris
    transfer_face(nface,head,job);iris_images=transfer_iris(head,job)
    for obj,image in zip(head['native_eyes'],iris_images):
        mat=bpy.data.materials.new('Native iris preview');mat.use_nodes=True
        bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');tex=mat.node_tree.nodes.new('ShaderNodeTexImage');tex.image=image
        mat.node_tree.links.new(tex.outputs['Color'],bs.inputs['Base Color']);mat.node_tree.links.new(tex.outputs['Alpha'],bs.inputs['Alpha'])
        obj.data.materials.clear();obj.data.materials.append(mat)
    mask=bpy.data.images.new('body mask',4,4);mask.generated_color=(0,0,0,1);mask.filepath_raw=str(job/'body-mask.png');mask.file_format='PNG';mask.save()
    mask=bpy.data.images.new('face color mask',4,4);mask.generated_color=(0,0,0,0);mask.filepath_raw=str(job/'face-color-mask.png');mask.file_format='PNG';mask.save()
    result=dict(cache=str(cache),body=bodyreport,hair=hairreport,face=facereport,textures=textures,appearance=dict(face_albedo=True,left_right_iris=True,canonical_card=True),
        cabs={k:'CAB-'+hashlib.md5((r['identity']['guid']+'.'+k).encode()).hexdigest() for k in ['hair','outfit','face']},game_verified=False)
    write_json(job/'fit.json',result)
    # Save an assembled, inspectable scene. Export files above remain head-local.
    headpos=bodyarm.matrix_world@bodyarm.data.bones['cf_j_head'].head_local
    headarm=next(m.object for m in nface.modifiers if m.type=='ARMATURE');hairarm=next(m.object for m in hair.modifiers if m.type=='ARMATURE')
    headarm.location+=headpos;hairarm.location+=headpos
    head_objects=[o for o in refs['head'] if not any(n in o.name for n in ['gag_eye','namida','eyeline_low','hitomi_L02','hitomi_R02'])]
    visible=[outfit,bodyarm,hair,hairarm]+head_objects
    keep=set(visible)
    for o in list(bpy.data.objects):
        if o not in keep:bpy.data.objects.remove(o,do_unlink=True)
    collection=bpy.data.collections.new('PMX2KK_Result');bpy.context.scene.collection.children.link(collection)
    for o in keep:
        if not o:continue
        for c in list(o.users_collection):c.objects.unlink(o)
        collection.objects.link(o)
    bpy.context.view_layer.update()
    status(job,'running','渲染正面、侧面和背面预览',.6);render_preview(job,visible)
    bpy.ops.wm.save_as_mainfile(filepath=str(job/'converted.blend'))
    if stage=='build':
        status(job,'running','生成 Unity 5.6 原生资源包',.8)
        shutil.copy2(r['shader_template'],job/'shader-template.unity3d')
        run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',HERE/'backend/build.ps1','-Recipe',job/'recipe.json'],job/'build.log')
        from packaging import package
        output=package(r,job,cache)
        status(job,'built','资源包已生成；游戏内效果需另行验收',1,output=str(output),game_verified=False)
    else:status(job,'converted','预览完成，请检查姿态、分件及贴合',1,game_verified=False)
