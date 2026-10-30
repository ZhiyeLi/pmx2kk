"""Isolated Blender worker. Never opens or overwrites the user's live scene."""
import sys,os,traceback,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from core import *
import bpy

def enable_mmd(path):
    # Installed extension or user-selected module directory; no downloading.
    if path:
        p=Path(path);sys.path.insert(0,str(p.parent if p.name=='mmd_tools' else p))
        module=p if p.name=='mmd_tools' else p/'mmd_tools'
        import zipfile
        deps=Path(os.environ['BLENDER_USER_CONFIG']).parent/'dependencies'
        deps.mkdir(parents=True,exist_ok=True)
        for wheel in (module/'wheels').glob('*.whl'):
            with zipfile.ZipFile(wheel) as z:
                if any(not (deps/n).resolve().is_relative_to(deps.resolve()) for n in z.namelist()):
                    raise ValueError('Unsafe dependency archive')
                z.extractall(deps)
        sys.path.insert(0,str(deps))
        import mmd_tools
        if not hasattr(bpy.types.Object,'mmd_type'):mmd_tools.register()
        return
    import addon_utils
    for entry in addon_utils.modules():
        if entry.__name__.endswith('mmd_tools'):
            addon_utils.enable(entry.__name__,default_set=False);return
    import mmd_tools
    if not hasattr(bpy.types.Object,'mmd_type'):mmd_tools.register()

def inspect(r,job):
    from mathutils import Matrix
    enable_mmd(r.get('mmd',''))
    bpy.ops.mmd_tools.import_model(filepath=r['source'],scale=r['settings']['import_scale'])
    meshes=[o for o in bpy.data.objects if o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers)]
    if not meshes:raise ValueError('未找到蒙皮网格；请选择人物 PMX')
    arms={m.object for o in meshes for m in o.modifiers if m.type=='ARMATURE'}
    if len(arms)!=1:raise ValueError('第一版需要一套人物骨架')
    arm=arms.pop()
    for p in arm.pose.bones:
        for c in p.constraints:c.mute=True
        p.matrix_basis.identity()
    matrix=arm.matrix_world.copy();arm.parent=None;arm.matrix_world=matrix
    bones=[dict(name=b.name,original=arm.pose.bones[b.name].mmd_bone.name_j,head=list(arm.matrix_world@b.head_local),
                tail=list(arm.matrix_world@b.tail_local),parent=b.parent.name if b.parent else None) for b in arm.data.bones]
    mapping,anchors,missing=map_bones(bones,r.get('bone_overrides'))
    parts=[];matrows=[];material_id=0;bone_table={b['name']:b for b in bones}
    for mesh in meshes:
        bpy.ops.object.select_all(action='DESELECT');mesh.select_set(True);bpy.context.view_layer.objects.active=mesh
        bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.mesh.separate(type='MATERIAL');bpy.ops.object.mode_set(mode='OBJECT')
        for obj in sorted([x for x in bpy.context.selected_objects if x.type=='MESH'],key=lambda x:x.name):
            if not obj.data.materials:raise ValueError('网格没有材质：'+obj.name)
            mat=obj.data.materials[0];original=mat.mmd_material.name_j or mat.name
            texture=next((n.image for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image and n.name=='mmd_base_tex'),None)
            if texture is None:texture=next((n.image for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image),None)
            texpath=bpy.path.abspath(texture.filepath) if texture else ''
            heads=set(n for n,t in mapping.items() if t=='cf_j_head');count=0
            for v in obj.data.vertices:
                if sum(g.weight for g in v.groups if obj.vertex_groups[g.group].name in heads)>.8:count+=1
            fraction=count/max(1,len(obj.data.vertices));role,confidence=classify_material(original,fraction)
            unresolved={}
            for v in obj.data.vertices:
                for g in v.groups:
                    n=obj.vertex_groups[g.group].name
                    if n not in bone_table or g.weight<=1e-8:continue
                    parent=n;seen=set()
                    while parent in bone_table and parent not in mapping and parent not in seen:
                        seen.add(parent);parent=bone_table[parent]['parent']
                    if parent not in mapping:unresolved[n]=unresolved.get(n,0)+1
            key=str(material_id);obj.name='pmx2kk_part_'+key;obj['pmx2kk_id']=key
            mat.name='pmx2kk_mat_'+key
            coords=[obj.matrix_world@v.co for v in obj.data.vertices]
            matrows.append(dict(id=key,name=original,object=obj.name,texture=texpath,texture_exists=bool(texpath and Path(texpath).is_file()),
                vertices=len(coords),role=role,confidence=confidence,head_fraction=fraction,unresolved_bones=unresolved,
                bounds=[[min(v[i] for v in coords) for i in range(3)],[max(v[i] for v in coords) for i in range(3)]]))
            # Simple export/preview material with original diffuse atlas.
            mat.use_nodes=True;mat.node_tree.nodes.clear();out=mat.node_tree.nodes.new('ShaderNodeOutputMaterial');bs=mat.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
            bs.inputs['Base Color'].default_value=mat.diffuse_color
            mat.node_tree.links.new(bs.outputs['BSDF'],out.inputs['Surface']);bs.inputs['Roughness'].default_value=.8
            if texture:
                node=mat.node_tree.nodes.new('ShaderNodeTexImage');node.image=texture
                mat.node_tree.links.new(node.outputs['Color'],bs.inputs['Base Color']);mat.node_tree.links.new(node.outputs['Alpha'],bs.inputs['Alpha'])
                if Path(texpath).is_file():texture.pack()
            parts.append(obj);material_id+=1
    keep=set(parts+[arm])
    for obj in list(bpy.data.objects):
        if obj not in keep:bpy.data.objects.remove(obj,do_unlink=True)
    arm.name='pmx2kk_source_rig'
    bpy.context.scene.name='pmx2KK source'
    for c in list(bpy.data.collections):
        if c.name=='PMX2KK_Source':continue
    collection=bpy.data.collections.new('PMX2KK_Source');bpy.context.scene.collection.children.link(collection)
    for obj in keep:
        for c in list(obj.users_collection):c.objects.unlink(obj)
        collection.objects.link(obj)
    report=dict(source=r['source'],identity=r['identity'],bones=bones,bone_mapping=mapping,anchors=anchors,missing_bones=missing,
        materials=matrows,vertices=sum(len(o.data.vertices) for o in parts),blender=bpy.app.version_string)
    write_json(job/'inspect.json',report)
    if not r.get('materials'):r['materials']={x['id']:x['role'] for x in matrows}
    write_json(job/'recipe.json',r)
    bpy.ops.wm.save_as_mainfile(filepath=str(job/'source.blend'))
    status(job,'inspected','检查完成；请确认部件与骨骼映射',1,missing_bones=missing)

def main():
    args=sys.argv[sys.argv.index('--')+1:];recipe=Path(args[0]);stage=args[1]
    r=read_json(recipe);job=job_path(r);job.mkdir(parents=True,exist_ok=True);start=time.monotonic()
    try:
        if bpy.app.version[:2]!=(4,5):raise ValueError('本版本仅验证 Blender 4.5 LTS')
        validate_recipe(r,building=stage!='inspect')
        status(job,'running','正在'+stage,0)
        if stage=='inspect':inspect(r,job)
        else:
            from convert import convert
            convert(r,job,stage)
        write_json(job/(stage+'-timing.json'),dict(seconds=time.monotonic()-start))
    except Exception as e:
        status(job,'error',str(e),0,traceback=traceback.format_exc());raise

if __name__=='__main__':main()
