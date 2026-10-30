"""pmx2KK: Blender-side authoring for original Koikatsu native parts."""
bl_info={'name':'pmx2KK','author':'Local tools','version':(0,2,1),'blender':(4,5,0),'location':'3D View > Sidebar > pmx2KK','description':'Landmark fitting and source facial textures on native KK parts','category':'Import-Export'}
import bpy,sys,os,subprocess,time
from pathlib import Path
from bpy.props import StringProperty,EnumProperty,FloatProperty,FloatVectorProperty,BoolProperty,IntProperty,CollectionProperty,PointerProperty
from bpy_extras.io_utils import ImportHelper
from . import core

PACKAGE=__package__;HERE=Path(__file__).parent;JOBS={}
ROLE_ITEMS=[(k,label,'') for k,label in [('AUTO','待确认'),('BODY','身体 / 服装'),('HAIR','头发'),('HEAD_ACCESSORY','头饰'),('FACE','脸部皮肤'),('IRIS','瞳孔（转移原图）'),('FACE_DETAIL','其他五官（KK 原生）'),('IGNORE','忽略'),('SPLIT_HOOD','帽衣按高度分割')]]

class PMX2KKPreferences(bpy.types.AddonPreferences):
    bl_idname=PACKAGE
    game:StringProperty(name='原版 KK 目录',subtype='DIR_PATH')
    sb3:StringProperty(name='SB3Utility 目录',subtype='DIR_PATH')
    mmd:StringProperty(name='mmd_tools 模块目录',subtype='DIR_PATH')
    shader:StringProperty(name='本地 Studio 材质模板',subtype='FILE_PATH',description='含 Shader Forge/main_item_studio 材质的本地 Unity 5.6 bundle')
    base_card:StringProperty(name='基础人物卡（可选）',subtype='FILE_PATH',description='原版 KK 女性卡；生成时重置脸型/体型参数。原色瞳孔需 KK OverlayMods')
    def draw(self,context):
        for p in ['game','sb3','mmd','shader','base_card']:self.layout.prop(self,p)
        self.layout.label(text='本插件不包含游戏资源、模型或 SB3Utility。Windows / Blender 4.5。')

class PMX2KKMaterial(bpy.types.PropertyGroup):
    key:StringProperty();name:StringProperty();object_name:StringProperty();note:StringProperty()
    role:EnumProperty(items=ROLE_ITEMS,default='AUTO')

class PMX2KKBone(bpy.types.PropertyGroup):
    name:StringProperty();target:StringProperty(name='KK 骨骼',description='留空使用自动映射；目标必须是 KK 原生骨骼名称')

class PMX2KKSettings(bpy.types.PropertyGroup):
    source:StringProperty(name='PMX 文件',subtype='FILE_PATH')
    output:StringProperty(name='独立工作目录',subtype='DIR_PATH')
    recipe:StringProperty(name='当前配置',subtype='FILE_PATH')
    status:StringProperty(default='选择 PMX 后检查模型')
    display_name:StringProperty(name='角色名称')
    confirmed:BoolProperty(name='我已检查部件分类与骨骼映射',default=False)
    import_scale:FloatProperty(name='PMX 导入比例',default=.08,min=.001,max=10)
    body_width:FloatProperty(name='身体横向比例',default=1,min=.2,max=3)
    face_strength:FloatProperty(name='脸型拟合强度',default=1,min=0,max=1)
    hair_scale:FloatProperty(name='头发比例微调',default=1,min=.2,max=3,description='自动眼距/下巴归一化后，绕眼部中心微调头发与头饰')
    hair_offset:FloatVectorProperty(name='头发偏移',size=3,subtype='TRANSLATION')
    hood_cut:FloatProperty(name='帽衣分割高度',default=1,description='PMX 按导入比例缩放后的世界 Z 高度')
    hair_physics:EnumProperty(name='头发物理',items=[('STATIC','固定在头部','适合先验证贴合；长发物理需后续适配'),('FRINGE','短刘海模板','只对头部附近的前侧发梢应用模板摆动')],default='STATIC')
    damping:FloatProperty(name='阻尼',default=.55,min=0,max=1)
    stiffness:FloatProperty(name='刚度',default=.85,min=0,max=1)
    elasticity:FloatProperty(name='弹性',default=.35,min=0,max=1)
    inertia:FloatProperty(name='惯性',default=.8,min=0,max=1)
    outline:FloatProperty(name='描边宽度',default=0,min=0,max=.01,precision=4)
    simplify_large_meshes:BoolProperty(name='允许简化超大网格',default=False,description='超过原版 KK 单网格限制时，在工作副本中减面。需要重新检查细节和权重')
    materials:CollectionProperty(type=PMX2KKMaterial);material_index:IntProperty()
    bones:CollectionProperty(type=PMX2KKBone);bone_index:IntProperty()
    show_bones:BoolProperty(name='骨骼覆盖',default=False)

class PMX2KK_UL_materials(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row();row.label(text=item.key+' · '+item.name);row.prop(item,'role',text='')

class PMX2KK_UL_bones(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        layout.label(text=item.name);layout.prop(item,'target',text='')

SETTING_KEYS=['import_scale','body_width','face_strength','hair_scale','hair_offset','hood_cut','hair_physics','damping','stiffness','elasticity','inertia','outline','simplify_large_meshes']

def load_recipe(scene,path):
    r=core.read_json(path);s=scene.pmx2kk;s.recipe=str(path);s.source=r['source'];s.output=r['output'];s.display_name=r['name'];s.confirmed=r['confirmed']
    for k in SETTING_KEYS:
        if k in r['settings']:setattr(s,k,r['settings'][k])
    s.materials.clear();s.bones.clear()
    report=core.read_json(core.job_path(r)/'inspect.json')
    mapping,anchors,missing=core.map_bones(report['bones'],r['bone_overrides'])
    for m in report['materials']:
        row=s.materials.add();row.key=m['id'];row.name=m['name'];row.object_name=m['object'];row.role=r['materials'].get(m['id'],m['role'])
        row.note=f"{m['vertices']} 顶点 · 建议置信度 {m['confidence']:.0%}"
        if m.get('unresolved_bones'):row.note+=' · 未绑定: '+', '.join(m['unresolved_bones'])
    for b in report['bones']:
        row=s.bones.add();row.name=b['name'];row.target=r['bone_overrides'].get(b['name'],mapping.get(b['name'],''))
    s.status='检查完成；缺少必需骨骼 '+str(len(missing))

def saved_recipe(context):
    s=context.scene.pmx2kk;r=core.read_json(s.recipe);p=context.preferences.addons[PACKAGE].preferences
    r.update(name=s.display_name,confirmed=s.confirmed,game=bpy.path.abspath(p.game),sb3=bpy.path.abspath(p.sb3),mmd=bpy.path.abspath(p.mmd),shader_template=bpy.path.abspath(p.shader),base_card=bpy.path.abspath(p.base_card) if p.base_card else '')
    r['materials']={x.key:x.role for x in s.materials};r['bone_overrides']={x.name:x.target for x in s.bones if x.target}
    r['settings']={k:list(getattr(s,k)) if k=='hair_offset' else getattr(s,k) for k in SETTING_KEYS}
    report=core.read_json(core.job_path(r)/'inspect.json')
    if r['source']!=bpy.path.abspath(s.source):raise ValueError('PMX 已改变，请重新检查')
    # Import scale affects source.blend, and must never be changed only at fitting time.
    old=core.read_json(s.recipe)
    if abs(r['settings']['import_scale']-old['settings']['import_scale'])>1e-7:raise ValueError('导入比例已改变，请重新检查模型')
    core.validate_recipe(r,building=True);core.write_json(s.recipe,r);return r

def poll_jobs():
    for scene_name,entry in list(JOBS.items()):
        scene=bpy.data.scenes.get(scene_name);process=entry['process'];job=entry['job']
        state={}
        try:state=core.read_json(job/'status.json')
        except (OSError,ValueError):pass
        if scene:scene.pmx2kk.status=state.get('message','启动中')+' · '+str(int(time.monotonic()-entry['start']))+' 秒'
        code=process.poll()
        if code is not None:
            entry['log'].close();del JOBS[scene_name]
            if scene and code==0 and entry['stage']=='inspect':
                try:load_recipe(scene,job/'recipe.json')
                except Exception as e:scene.pmx2kk.status=str(e)
            elif scene and code!=0:scene.pmx2kk.status='失败：'+state.get('message','查看 worker 日志')
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type=='VIEW_3D':area.tag_redraw()
    return .5 if JOBS else None

class PMX2KK_OT_run(bpy.types.Operator):
    bl_idname='pmx2kk.run';bl_label='pmx2KK 后台任务'
    stage:EnumProperty(items=[('inspect','检查',''),('convert','预览',''),('build','打包','')])
    def execute(self,context):
        if JOBS:self.report({'ERROR'},'请等待当前任务完成');return {'CANCELLED'}
        try:
            s=context.scene.pmx2kk;p=context.preferences.addons[PACKAGE].preferences
            if self.stage=='inspect':
                if not s.output:raise ValueError('请选择独立工作目录')
                r=core.new_recipe(bpy.path.abspath(s.source),bpy.path.abspath(s.output),bpy.path.abspath(p.game),bpy.path.abspath(p.sb3),bpy.path.abspath(p.mmd),bpy.path.abspath(p.shader),bpy.path.abspath(p.base_card) if p.base_card else '')
                r['settings']['import_scale']=s.import_scale
                job=core.job_path(r);job.mkdir(parents=True,exist_ok=True)
                # A fresh inspection resets classification; preserve the preceding recipe.
                if (job/'recipe.json').exists():
                    core.write_json(job/('recipe-before-inspect-'+str(time.time_ns())+'.json'),core.read_json(job/'recipe.json'))
                core.write_json(job/'recipe.json',r);s.recipe=str(job/'recipe.json')
            else:r=saved_recipe(context);job=core.job_path(r)
            env=os.environ.copy();env['PYTHONNOUSERSITE']='1'
            for key,part in [('BLENDER_USER_CONFIG','config'),('BLENDER_USER_EXTENSIONS','extensions')]:
                env[key]=str(job/'profile'/part);Path(env[key]).mkdir(parents=True,exist_ok=True)
            log=open(job/(self.stage+'-worker.log'),'a',encoding='utf8')
            cmd=[bpy.app.binary_path,'--background','--factory-startup','--python-exit-code','1','--python',str(HERE/'worker.py'),'--',str(job/'recipe.json'),self.stage]
            try:process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:log.close();raise
            JOBS[context.scene.name]=dict(process=process,job=job,log=log,stage=self.stage,start=time.monotonic())
            s.status='后台任务启动中'
            if not bpy.app.timers.is_registered(poll_jobs):bpy.app.timers.register(poll_jobs,first_interval=.5)
            return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class PMX2KK_OT_cancel(bpy.types.Operator):
    bl_idname='pmx2kk.cancel';bl_label='取消后台任务'
    def execute(self,context):
        for e in JOBS.values():
            if e['process'].poll() is None:subprocess.run(['taskkill','/PID',str(e['process'].pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        return {'FINISHED'}

class PMX2KK_OT_load(bpy.types.Operator,ImportHelper):
    bl_idname='pmx2kk.load';bl_label='恢复转换配置'
    filename_ext='.json';filter_glob:StringProperty(default='*.json',options={'HIDDEN'})
    def execute(self,context):
        try:load_recipe(context.scene,self.filepath);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class PMX2KK_OT_preview(bpy.types.Operator):
    bl_idname='pmx2kk.preview';bl_label='载入预览副本';bl_options={'REGISTER','UNDO'}
    result:BoolProperty(default=False)
    def execute(self,context):
        try:
            r=core.read_json(context.scene.pmx2kk.recipe);job=core.job_path(r);name='PMX2KK_Result' if self.result else 'PMX2KK_Source'
            file=job/('converted.blend' if self.result else 'source.blend')
            if not file.exists():raise ValueError('请先运行相应的检查或转换任务')
            with bpy.data.libraries.load(str(file),link=False) as (src,dst):dst.collections=[name]
            c=dst.collections[0]
            if c is None:raise ValueError('预览集合不存在')
            for old in context.scene.collection.children:
                if old.get('pmx2kk_preview'):old.hide_viewport=True;old.hide_render=True
            context.scene.collection.children.link(c);c['pmx2kk_preview']=True
            context.view_layer.update()
            bpy.ops.object.select_all(action='DESELECT')
            for o in c.all_objects:
                if o is None:continue
                o.hide_set(False);o.hide_viewport=False
                if o.type=='MESH':o.select_set(True);context.view_layer.objects.active=o
            for area in context.screen.areas:
                if area.type=='VIEW_3D':
                    area.spaces.active.shading.type='MATERIAL'
                    region=next(x for x in area.regions if x.type=='WINDOW')
                    with context.temp_override(area=area,region=region):bpy.ops.view3d.view_selected()
            return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class PMX2KK_OT_select(bpy.types.Operator):
    bl_idname='pmx2kk.select_part';bl_label='选中此部件';bl_options={'UNDO'}
    def execute(self,context):
        s=context.scene.pmx2kk
        if not s.materials:return {'CANCELLED'}
        key=s.materials[s.material_index].key;bpy.ops.object.select_all(action='DESELECT')
        for o in context.scene.objects:
            if str(o.get('pmx2kk_id',''))==key and o.visible_get():o.select_set(True);context.view_layer.objects.active=o
        return {'FINISHED'}

class PMX2KK_OT_folder(bpy.types.Operator):
    bl_idname='pmx2kk.folder';bl_label='打开工作目录'
    def execute(self,context):
        p=Path(context.scene.pmx2kk.recipe).parent
        if p.is_dir():bpy.ops.wm.path_open(filepath=str(p))
        return {'FINISHED'}

class PMX2KK_PT_panel(bpy.types.Panel):
    bl_label='pmx2KK · 原生部件转换';bl_idname='PMX2KK_PT_panel';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='pmx2KK'
    def draw(self,context):
        l=self.layout;s=context.scene.pmx2kk
        l.label(text='Blender 4.5 / 原版 KK / Windows')
        for p in ['source','output','import_scale']:l.prop(s,p)
        row=l.row();row.enabled=not JOBS;row.operator('pmx2kk.run',text='1 · 检查 PMX',icon='VIEWZOOM').stage='inspect';row.operator('pmx2kk.load',text='',icon='FILE_FOLDER')
        l.label(text=s.status)
        if JOBS:l.operator('pmx2kk.cancel',icon='CANCEL')
        if not s.materials:return
        row=l.row();row.operator('pmx2kk.preview',text='载入源模型').result=False;row.operator('pmx2kk.select_part')
        l.template_list('PMX2KK_UL_materials','',s,'materials',s,'material_index',rows=7)
        if s.materials:l.label(text=s.materials[s.material_index].note)
        l.prop(s,'show_bones')
        if s.show_bones:l.template_list('PMX2KK_UL_bones','',s,'bones',s,'bone_index',rows=5)
        l.prop(s,'display_name')
        for p in ['body_width','face_strength','hair_scale','hair_offset','hood_cut','hair_physics']:l.prop(s,p)
        if s.hair_physics=='FRINGE':
            for p in ['damping','stiffness','elasticity','inertia']:l.prop(s,p)
        l.prop(s,'outline');l.prop(s,'simplify_large_meshes');l.prop(s,'confirmed')
        row=l.row();row.enabled=not JOBS and s.confirmed;row.operator('pmx2kk.run',text='2 · 转换并渲染').stage='convert';row.operator('pmx2kk.run',text='3 · 生成 zipmod').stage='build'
        row=l.row();row.operator('pmx2kk.preview',text='载入转换预览').result=True;row.operator('pmx2kk.folder',text='',icon='FILE_FOLDER')
        l.label(text='原生近似脸型 · 整套服装占上衣槽')
        l.label(text='预览为几何检查；眼睛材质以 KK 内为准')
        l.label(text='打包完成不等于已通过游戏内验收')

CLASSES=[PMX2KKPreferences,PMX2KKMaterial,PMX2KKBone,PMX2KKSettings,PMX2KK_UL_materials,PMX2KK_UL_bones,PMX2KK_OT_run,PMX2KK_OT_cancel,PMX2KK_OT_load,PMX2KK_OT_preview,PMX2KK_OT_select,PMX2KK_OT_folder,PMX2KK_PT_panel]
def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.Scene.pmx2kk=PointerProperty(type=PMX2KKSettings)

def unregister():
    for e in JOBS.values():
        if e['process'].poll() is None:subprocess.run(['taskkill','/PID',str(e['process'].pid),'/T','/F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        e['log'].close()
    JOBS.clear()
    if bpy.app.timers.is_registered(poll_jobs):bpy.app.timers.unregister(poll_jobs)
    del bpy.types.Scene.pmx2kk
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
