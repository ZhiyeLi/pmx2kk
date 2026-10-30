"""Landmark normalization shared by the face, hair, ornaments and neck."""
import math
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree

def coords(o):return [o.matrix_world@v.co for v in o.data.vertices]

def skin_vertices(obj):
    """Outer skin component: exclude detached mouth/eyelid shadow strips."""
    adjacent=[set() for _ in obj.data.vertices]
    for e in obj.data.edges:
        a,b=e.vertices;adjacent[a].add(b);adjacent[b].add(a)
    seen=set();parts=[]
    for v in obj.data.vertices:
        if v.index in seen:continue
        stack=[v.index];seen.add(v.index);part=set()
        while stack:
            i=stack.pop();part.add(i)
            for j in adjacent[i]-seen:seen.add(j);stack.append(j)
        parts.append(part)
    largest=max(map(len,parts))
    return set().union(*(p for p in parts if len(p)>=largest*.35))

def iris_parts(parts,report):
    selected=[]
    for m in report['materials']:
        n=m['name'].lower()
        if n in ['eye','eyes','瞳','瞳孔'] or any(s in n for s in ['眼睛','瞳孔','iris']):
            if any(s in n for s in ['高光','highlight','白','white']):continue
            selected.append(parts[m['id']])
    return selected

def principal_irises(objects):
    def area(obj,side):
        points=coords(obj);total=0
        for p in obj.data.polygons:
            if sum(points[i].x for i in p.vertices)*side<=0:continue
            a=points[p.vertices[0]]
            for j in range(1,len(p.vertices)-1):total+=(points[p.vertices[j]]-a).cross(points[p.vertices[j+1]]-a).length
        return total
    chosen=[]
    for side in [1,-1]:
        obj=max(objects,key=lambda o:area(o,side))
        if obj not in chosen:chosen.append(obj)
    return chosen

def center(points):
    return Vector([(min(p[i] for p in points)+max(p[i] for p in points))*.5 for i in range(3)])

def chin(points,eye_span):
    central=[p for p in points if abs(p.x)<eye_span*.18]
    front=min(p.y for p in central);depth=max(p.y for p in central)-front
    front_points=[p for p in central if p.y<front+depth*.65]
    return min(front_points,key=lambda p:p.z)

def normalize(parts,r,report,nface,native_objects):
    faces=[o for k,o in parts.items() if r['materials'][k]=='FACE']
    if len(faces)!=1:raise ValueError('请指定一个脸部皮肤材质')
    eyes=[o for k,o in parts.items() if r['materials'][k]=='IRIS'] or iris_parts(parts,report)
    if not eyes:raise ValueError('没有识别到瞳孔材质；请将对应部件分类设为“瞳孔”')
    eyes=principal_irises(eyes)
    layers=iris_parts(parts,report)
    for m in report['materials']:
        if '眼高光' in m['name'] or 'eye_highlight' in m['name'].lower():layers.append(parts[m['id']])
    layers=list(dict.fromkeys(eyes+layers))
    points=[p for o in eyes for p in coords(o)]
    source=[center([p for p in points if p.x*s>0]) for s in [1,-1]]
    native=[next(o for o in native_objects if o.type=='MESH' and o.name.startswith('cf_Ohitomi_'+s+'_')) for s in ['L','R']]
    target=[center(coords(o)) for o in native]
    se=(source[0]+source[1])*.5;te=(target[0]+target[1])*.5
    sw=abs(source[0].x-source[1].x);tw=abs(target[0].x-target[1].x)
    sc=chin(coords(faces[0]),sw);tc=chin(coords(nface),tw)
    if sw<1e-4 or se.z-sc.z<1e-4:raise ValueError('瞳孔/下巴标记无效，不能归一化')
    scales=Vector((tw/sw,tw/sw,(te.z-tc.z)/(se.z-sc.z)))
    linear=Matrix.Diagonal(scales);offset=te-linear@se
    # One transform for every head-attached surface. There is no later face-only
    # depth translation, and ears/halo bounds never determine head size.
    return dict(linear=linear,offset=offset,source_face=faces[0],iris_sources=eyes,iris_layers=layers,native_eyes=native,
        report=dict(method='iris centers + eye-to-chin height; shared affine',source_eyes=[list(p) for p in source],
        target_eyes=[list(p) for p in target],source_chin=list(sc),target_chin=list(tc),scales=list(scales),offset=list(offset),iris_materials=[str(o['pmx2kk_id']) for o in eyes]))

def sculpt(nface,head,strength):
    pmx=head['source_face'];linear=head['linear'];offset=head['offset'];src=[linear@p+offset for p in coords(pmx)]
    skin=skin_vertices(pmx)
    tree=BVHTree.FromPolygons(src,[list(p.vertices) for p in pmx.data.polygons if p.vertices[0] in skin])
    world=nface.matrix_world;inverse=world.inverted().to_3x3();deltas=[];pinned=[]
    for v in nface.data.vertices:
        p=world@v.co;hit=tree.find_nearest(p);delta=hit[0]-p if hit[0] is not None else Vector()
        # Bound the *final* displacement field. The old 8 cm nearest-surface
        # offsets, multiplied by rectangular masks AFTER smoothing, made cheek
        # shelves around the untouched eyelid/lip regions. Native topology needs
        # a conservative silhouette fit, not a shrinkwrap onto PMX eye sockets.
        eye=math.exp(-((abs(p.x)-.055)/.040)**4-((p.z-.077)/.040)**4)
        mouth=math.exp(-(p.x/.030)**4-((p.z-.009)/.027)**4)
        neck=max(0.,min(1.,(p.z+.025)/.035))
        frontal=max(0.,min(1.,(.035-p.y)/.07))
        protected=max(eye,mouth)
        amount=min(1.,max(0.,strength))*.8*neck*frontal*(1-protected)
        if delta.length>.016:delta*=.016/delta.length
        deltas.append(inverse@(delta*amount))
        eye_envelope=max(abs(abs(p.x)-.055)/.040,abs(p.z-.077)/.036)
        lip_envelope=max(abs(p.x)/.040,abs(p.z-.009)/.033)
        pinned.append(min(eye_envelope,lip_envelope)<1 or neck==0 or frontal==0)
    # FBX UV/material seams contain duplicated vertices. Diffusing each copy
    # independently opens cracks at the mouth and eyelids. Solve one field on
    # coincident positions, then scatter it back without changing KK topology.
    groups={};indices=[]
    for v in nface.data.vertices:
        key=tuple(round(x,6) for x in v.co)
        if key not in groups:groups[key]=len(groups)
        indices.append(groups[key])
    members=[[] for _ in groups]
    for i,g in enumerate(indices):members[g].append(i)
    field=[sum((deltas[i] for i in members[g]),Vector())/len(members[g]) for g in range(len(groups))]
    locks=[any(pinned[i] for i in ids) for ids in members]
    adjacent=[set() for _ in groups]
    for e in nface.data.edges:
        a,b=[indices[i] for i in e.vertices]
        if a!=b:adjacent[a].add(b);adjacent[b].add(a)
    for _ in range(24):
        field=[Vector() if locks[i] else d*.6+sum((field[j] for j in adjacent[i]),Vector())*(.4/len(adjacent[i])) if adjacent[i] else d for i,d in enumerate(field)]
    deltas=[field[g] for g in indices]
    for key in nface.data.shape_keys.key_blocks:
        for v,d in zip(key.data,deltas):v.co+=d
    for v,d in zip(nface.data.vertices,deltas):v.co+=d
    # Imported custom normals describe the unsculpted surface. Recalculate from
    # repaired geometry; do not carry stale normals into the native face bundle.
    if nface.data.has_custom_normals:nface.data.normals_split_custom_set([(0,0,0)]*len(nface.data.loops))
    return dict(method='bounded displacement diffusion with native expression constraints',vertices=len(deltas),morphs=len(nface.data.shape_keys.key_blocks)-1,
        welded_displacement_groups=len(groups),imported_key_order=[k.name for k in nface.data.shape_keys.key_blocks][1:],max_displacement=max(v.length for v in deltas),lossless=False)
