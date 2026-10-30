"""Bake source PMX appearance into native KK UV maps, retaining native topology."""
import bpy,numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

def surface(obj,positions=None,skin_only=False,front_only=False):
    obj.data.calc_loop_triangles()
    triangles=list(obj.data.loop_triangles)
    if skin_only:
        from head import skin_vertices
        skin=skin_vertices(obj);triangles=[t for t in triangles if t.vertices[0] in skin]
    positions=positions or [obj.matrix_world@v.co for v in obj.data.vertices]
    if front_only:
        triangles=[t for t in triangles if (positions[t.vertices[1]]-positions[t.vertices[0]]).cross(positions[t.vertices[2]]-positions[t.vertices[0]]).normalized().y<-.12]
    tree=BVHTree.FromPolygons(positions,[t.vertices[:] for t in triangles],all_triangles=True)
    return tree,triangles,positions

def image_for(obj):
    return next(n.image for n in obj.data.materials[0].node_tree.nodes if n.type=='TEX_IMAGE' and n.image)

def uv_pixels(uv,size):
    uv=np.array(uv,dtype=float)*size
    lo=np.maximum(np.floor(uv.min(axis=0)).astype(int),0);hi=np.minimum(np.ceil(uv.max(axis=0)).astype(int),size-1)
    if np.any(hi<lo):return None
    x,y=np.meshgrid(np.arange(lo[0],hi[0]+1),np.arange(lo[1],hi[1]+1));p=np.stack([x.ravel()+.5,y.ravel()+.5],axis=1)
    a,b,c=uv;v=b-a;w=c-a;det=v[0]*w[1]-v[1]*w[0]
    if abs(det)<1e-9:return None
    p-=a;beta=(p[:,0]*w[1]-p[:,1]*w[0])/det;gamma=(v[0]*p[:,1]-v[1]*p[:,0])/det
    weights=np.stack([1-beta-gamma,beta,gamma],axis=1);inside=weights.min(axis=1)>=-1e-6
    return x.ravel()[inside],y.ravel()[inside],weights[inside]

def sample_image(pixels,uv):
    h,w=pixels.shape[:2]
    xy=np.clip(uv*np.array([w,h])-.5,0,np.array([w-1,h-1]))
    ix=xy.astype(int);jx=np.minimum(ix+1,np.array([w-1,h-1]));d=xy-ix
    dx=d[:,0,None];dy=d[:,1,None]
    return (pixels[ix[:,1],ix[:,0]]*(1-dx)+pixels[ix[:,1],jx[:,0]]*dx)*(1-dy)+(pixels[jx[:,1],ix[:,0]]*(1-dx)+pixels[jx[:,1],jx[:,0]]*dx)*dy


def write_skin_dds(pixels,path):
    """Uncompressed BGRA mip chain. SB3's default PNG path uses DXT5, whose
    RGB565 endpoints visibly posterize subtle skin gradients into colored rings.
    An explicit DDS payload avoids both that compression and format-name hacks.
    Input uses Blender bottom-up RGBA floats; DDS stores top-down rows.
    """
    import struct
    h,w=pixels.shape[:2];level=np.clip(pixels[::-1],0,1);levels=[]
    while True:
        levels.append(np.rint(level[:,:,[2,1,0,3]]*255).astype(np.uint8).tobytes())
        if min(level.shape[:2])==1:break
        lh,lw=level.shape[:2];level=level.reshape(lh//2,2,lw//2,2,4).mean(axis=(1,3))
    header=struct.pack('<7I',124,0x2100f,h,w,w*4,0,len(levels))+bytes(44)
    header+=struct.pack('<8I',32,0x41,0,32,0x00ff0000,0x0000ff00,0x000000ff,0xff000000)
    header+=struct.pack('<5I',0x401008,0,0,0,0)
    path.write_bytes(b'DDS '+header+b''.join(levels))


def harmonic_extend(values,known):
    """Multiscale Dirichlet fill: keep measured skin; extend its boundary colors.

    Missing PMX eye/mouth surface must not be filled by three constant-color
    ellipses. A harmonic field has no new extrema and no painted ring boundary.
    """
    h,w=known.shape
    if min(h,w)<=4:
        out=np.empty_like(values);out[:]=np.mean(values[known],axis=0) if known.any() else 1
    else:
        counts=known.reshape(h//2,2,w//2,2).sum(axis=(1,3))
        sums=(values*known[:,:,None]).reshape(h//2,2,w//2,2,values.shape[2]).sum(axis=(1,3))
        coarse=sums/np.maximum(counts[:,:,None],1)
        out=harmonic_extend(coarse,counts>0).repeat(2,0).repeat(2,1)
    out[known]=values[known]
    for _ in range(48):
        padded=np.pad(out,((1,1),(1,1),(0,0)),mode='edge')
        average=(padded[:-2,1:-1]+padded[2:,1:-1]+padded[1:-1,:-2]+padded[1:-1,2:])*.25
        out[~known]=average[~known]
    return out


def face_color_field(head,job):
    src=head['source_face'];positions=[head['linear']@(src.matrix_world@v.co)+head['offset'] for v in src.data.vertices]
    _,triangles,positions=surface(src,positions,skin_only=True,front_only=True)
    image=image_for(src);sw,sh=image.size
    pixels=np.array(image.pixels[:],dtype=np.float32).reshape(sh,sw,4)
    size=512;lower=np.array([-.16,-.06]);extent=np.array([.32,.32])
    color=np.zeros((size,size,4),np.float32);depth=np.full((size,size),np.inf);known=np.zeros((size,size),bool)
    uv=src.data.uv_layers.active
    for tri in triangles:
        pos=np.array([positions[i] for i in tri.vertices]);raster=uv_pixels((pos[:,[0,2]]-lower)/extent,size)
        if raster is None:continue
        x,y,weights=raster;z=weights@pos[:,1];mapped=weights@np.array([uv.data[i].uv[:] for i in tri.loops]);col=sample_image(pixels,mapped)
        front=(z<depth[y,x])&(col[:,3]>.9);x=x[front];y=y[front]
        color[y,x]=col[front];depth[y,x]=z[front];known[y,x]=True
    # Detached ink/sclera and atlas-edge bleed are not skin. Keep the continuous
    # source skin/blush field; KK provides its own movable eyelid and lip lines.
    base=np.median(color[known,:3],axis=0)
    valid=known&(np.max(np.abs(color[:,:,:3]-base),axis=2)<.22)
    # Reject the antialiased fringe as well as the dark ink pixel; otherwise
    # isolated brown/white dots remain where the PMX mouth used to be.
    rejected=known&~valid
    for _ in range(2):
        padded=np.pad(rejected,1)
        rejected=padded[1:-1,1:-1]|padded[:-2,1:-1]|padded[2:,1:-1]|padded[1:-1,:-2]|padded[1:-1,2:]
    valid&=~rejected
    field=harmonic_extend(color[:,:,:3],valid)
    from core import write_json
    write_json(job/'face-bake.json',dict(method='front-surface source UV sampling + harmonic hole extension',unity_skin_format='ARGB32 uncompressed mip chain',source_pixels=int(known.sum()),retained_skin_pixels=int(valid.sum()),skin_reference=base.tolist(),fixed_ellipse_patches=False))
    return field,lower,extent,base


def transfer_face(nface,head,job):
    field,lower,extent,base=face_color_field(head,job)
    size=1024;output=np.zeros((size,size,4),np.float32);filled=np.zeros((size,size),bool)
    nface.data.calc_loop_triangles();native_uv=nface.data.uv_layers.active
    for tri in nface.data.loop_triangles:
        raster=uv_pixels([native_uv.data[i].uv[:] for i in tri.loops],size)
        if raster is None:continue
        x,y,weights=raster
        points=weights@np.array([nface.matrix_world@nface.data.vertices[i].co for i in tri.vertices])
        col=sample_image(field,(points[:,[0,2]]-lower)/extent)
        front=np.clip((.015-points[:,1])/.065,0,1);front=front*front*(3-2*front)
        output[y,x,:3]=col*front[:,None]+base*(1-front[:,None]);output[y,x,3]=1;filled[y,x]=True
    # Extend UV islands, retaining their border colors for bilinear/mipmap sampling.
    for _ in range(12):
        previous=filled.copy()
        for axis,step in [(0,1),(0,-1),(1,1),(1,-1)]:
            shifted=np.roll(previous,step,axis=axis);take=shifted&~filled
            output[take]=np.roll(output,step,axis=axis)[take];filled|=take
    image=bpy.data.images.new('face-albedo',width=size,height=size,alpha=True)
    image.pixels.foreach_set(output.ravel());image.update();image.filepath_raw=str(job/'face-albedo.png');image.file_format='PNG';image.save();image.pack()
    write_skin_dds(output,job/'face-albedo.dds')
    # Visible Blender preview uses the same baked albedo delivered to KK.
    native_mat=bpy.data.materials.new('pmx2kk_face_preview');native_mat.use_nodes=True
    bs=next(n for n in native_mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');bs.inputs['Roughness'].default_value=.85
    tex=native_mat.node_tree.nodes.new('ShaderNodeTexImage');tex.image=image;native_mat.node_tree.links.new(tex.outputs['Color'],bs.inputs['Base Color'])
    # Do not replace the native material in the FBX exported to KK; preview only.
    nface.data.materials.clear();nface.data.materials.append(native_mat)
    return image

def transfer_iris(head,job):
    result=[]
    for side,target in zip([1,-1],head['native_eyes']):
        tree,tris,pos=surface(target);tuv=target.data.uv_layers.active
        size=512;output=np.zeros((size,size,4),np.float32);zbuffer=np.full((size,size),np.inf);draw=[];images={}
        for source in head['iris_layers']:
            original=image_for(source);sw,sh=original.size
            images[source.name]=(np.array(original.pixels[:],dtype=np.float32).reshape(sh,sw,4),sw,sh)
            coords=[head['linear']@(source.matrix_world@v.co)+head['offset'] for v in source.data.vertices]
            native=[]
            for p in coords:
                hit,_,index,_=tree.ray_cast(Vector((p.x,-1,p.z)),Vector((0,1,0)))
                if hit is None:hit,_,index,_=tree.find_nearest(Vector((p.x,-.08,p.z)))
                tri=tris[index]
                native.append(barycentric_transform(hit,*[pos[i] for i in tri.vertices],*[Vector((*tuv.data[i].uv,0)) for i in tri.loops])[:2])
            source.data.calc_loop_triangles();uv=source.data.uv_layers.active
            for tri in source.data.loop_triangles:
                if any(coords[i].x*side<=0 for i in tri.vertices):continue
                a,b,c=[coords[i] for i in tri.vertices]
                if (b-a).cross(c-a).y>=0:continue
                draw.append((sum(coords[i].y for i in tri.vertices)/3,source.name,[native[i] for i in tri.vertices],[uv.data[i].uv[:] for i in tri.loops],[coords[i].y for i in tri.vertices]))
        # Back-to-front alpha composition preserves separate PMX iris highlights.
        # Using source UVs per triangle avoids painting across unrelated atlas regions.
        for depth,name,nuv,suv,depths in sorted(draw,key=lambda row:-row[0]):
            raster=uv_pixels(nuv,size)
            if raster is None:continue
            x,y,weights=raster;mapped=weights@np.array(suv);pixels,sw,sh=images[name]
            sx=np.clip(mapped[:,0]*sw-.5,0,sw-1);sy=np.clip(mapped[:,1]*sh-.5,0,sh-1)
            ix=sx.astype(int);iy=sy.astype(int);jx=np.minimum(ix+1,sw-1);jy=np.minimum(iy+1,sh-1);dx=(sx-ix)[:,None];dy=(sy-iy)[:,None]
            col=(pixels[iy,ix]*(1-dx)+pixels[iy,jx]*dx)*(1-dy)+(pixels[jy,ix]*(1-dx)+pixels[jy,jx]*dx)*dy
            if name not in {o.name for o in head['iris_sources']}:
                # Extra eye materials can be flesh-colored eyelid occluders.
                # Only neutral highlight/shadow pixels belong in the iris atlas;
                # KK already supplies its own moving eyelid geometry.
                col[:,3]*=(col[:,:3].max(axis=1)-col[:,:3].min(axis=1)<.075)
            z=weights@np.array(depths);visible=(z<=zbuffer[y,x]+1e-7)&(col[:,3]>.001)
            x=x[visible];y=y[visible];col=col[visible];z=z[visible];zbuffer[y,x]=z
            old=output[y,x];alpha=col[:,3:4]+old[:,3:4]*(1-col[:,3:4]);rgb=(col[:,:3]*col[:,3:4]+old[:,:3]*old[:,3:4]*(1-col[:,3:4]))/np.maximum(alpha,1e-8)
            output[y,x]=np.concatenate([rgb,alpha],axis=1)
        label='L' if side==1 else 'R';image=bpy.data.images.new('iris-'+label,width=size,height=size,alpha=True)
        image.pixels.foreach_set(output.ravel());image.update();image.filepath_raw=str(job/('iris-'+label+'.png'));image.file_format='PNG';image.save();image.pack();result.append(image)
    return result
