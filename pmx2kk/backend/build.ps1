param([Parameter(Mandatory=$true)][string]$Recipe)
$ErrorActionPreference='Stop'
trap { $_.Exception.ToString();exit 1 }
$r=Get-Content -LiteralPath $Recipe -Encoding UTF8 -Raw | ConvertFrom-Json
$job=Join-Path $r.output $r.identity.key
$fit=Get-Content -LiteralPath (Join-Path $job 'fit.json') -Encoding UTF8 -Raw | ConvertFrom-Json
. (Join-Path $PSScriptRoot 'runtime.ps1') -Sb3 $r.sb3
$source=New-Object UnityPlugin.UnityParser (Join-Path $job 'shader-template.unity3d')
$sourceEditor=New-Object UnityPlugin.Unity3dEditor ($source,$false);$null=$sourceEditor.GetAssetNames($false)
$baseInfo=@($source.Cabinet.Components | Where-Object {$_.classID2 -eq [UnityPlugin.UnityClassID]::Material})[0]
$baseMat=$source.Cabinet.LoadComponent($baseInfo.pathID)
foreach($kind in @('hair','outfit','face')) {
 $template=if($kind -eq 'face'){'head'}else{$kind}
 $parser=New-Object UnityPlugin.UnityParser (Join-Path $fit.cache ($template+'/original.unity3d'))
 $editor=New-Object UnityPlugin.Unity3dEditor ($parser,$false);$names=$editor.GetAssetNames($false);$parser.InitTextures()
 $bundle=$parser.Cabinet.Bundle
 if($kind -ne 'face'){$bundle.m_Container.Clear();$bundle.m_PreloadTable.Clear()}
 $bundle.m_Name='chara/pmx2kk/'+$r.identity.key+'/'+$kind+'.unity3d';$bundle.m_AssetBundleName=$bundle.m_Name
 $textures=@{}
 if($kind -ne 'face') {
  foreach($property in $fit.textures.PSObject.Properties) {
   $textures[$property.Name]=$parser.AddTexture([SB3Utility.Plugins]::ImportTexture($property.Value),$false,$false)
   $textures[$property.Name].m_Name=$property.Name
  }
 }
 if($kind -eq 'hair') {
  foreach($c in @($parser.Cabinet.Components)) {
   if($c.classID2 -ne [UnityPlugin.UnityClassID]::MonoBehaviour){continue}
   $mb=$parser.Cabinet.LoadComponent($c.pathID)
   if($mb.m_MonoScript.instance.m_ClassName -ne 'DynamicBone'){continue}
   foreach($pair in @(@('m_Damping',$r.settings.damping),@('m_Elasticity',$r.settings.elasticity),@('m_Stiffness',$r.settings.stiffness),@('m_Inert',$r.settings.inertia))) {
    $mb.Parser.type.Find($pair[0]).Value=[single]$pair[1]
   }
   foreach($key in @('m_DampingDistrib','m_ElasticityDistrib','m_StiffnessDistrib','m_InertDistrib')) {
    $curve=$mb.Parser.type.Find($key).Find('m_Curve').Members[0]
    foreach($point in $curve.Value){$point.Find('value').Value=[single]1}
   }
  }
 }
 $suffixes=if($kind -eq 'face'){@('')}else{@('','_low')}
 foreach($suffix in $suffixes) {
  $fbx=if($kind -eq 'outfit'){'outfit'+$suffix+'.fbx'}else{$kind+'.fbx'}
  $imported=[SB3Utility.Plugins]::ImportFbx((Join-Path $job $fbx),$false,$true,$false)
  $workspace=New-Object SB3Utility.ImportedEditor $imported
  $old=switch($kind){'hair'{'p_cf_hair_f_23'}'outfit'{'p_o_top_suspend_t08'}'face'{'p_cf_head_00'}}
  $va=Open-Prefab $parser $editor $names ($old+$suffix)
  $anim=New-Object UnityPlugin.AnimatorEditor $va
  $go=$va.m_GameObject.instance;$go.m_Name='p_'+$r.identity.key+'_'+$kind+$suffix
  if($kind -ne 'face') {
   foreach($mat in $imported.MaterialList) {
    if(!$textures.ContainsKey($mat.Name)){throw ('Missing texture for '+$mat.Name)}
    $newMat=New-Object UnityPlugin.Material $parser.Cabinet;$baseMat.CopyTo($newMat,$false);$newMat.m_Name=$mat.Name
    foreach($slot in $newMat.m_SavedProperties.m_TexEnvs) {
     $tex=$null;if($slot.Key.name -eq '_MainTex'){$tex=$textures[$mat.Name]}
     $slot.Value.m_Texture=New-Object 'UnityPlugin.PPtr[UnityPlugin.Texture2D]' -ArgumentList @($tex)
    }
    $anim.Materials.Add($newMat);$mi=$anim.Materials.Count-1
    $anim.SetMaterialColour($mi,'_Color',@(1.0,1.0,1.0,1.0));$anim.SetMaterialValue($mi,'_linewidth',[double]$r.settings.outline)
   }
  }
  $meshNames=if($kind -eq 'face'){@('cf_O_face')}elseif($kind -eq 'hair'){@('cf_hair_f_23_00')}else{@($anim.Meshes | ForEach-Object {$_.m_GameObject.instance.m_Name})}
  foreach($meshName in $meshNames) {
   $frameId=$anim.GetFrameId($meshName);$frame=$anim.Frames[$frameId]
   if($kind -eq 'hair') {
    $frame.m_LocalPosition=[SlimDX.Vector3]::Zero;$frame.m_LocalRotation=[SlimDX.Quaternion]::Identity;$frame.m_LocalScale=New-Object SlimDX.Vector3 (1,1,1)
   } else { Reset-MeshFrame $frame }
   $id=$anim.ReplaceMeshRenderer($workspace.Meshes[0],$frameId,$false,'Replace','Replace',$true)
   $anim.ComputeBoneMatrices(@($anim.Meshes[$id]))
   if($anim.Meshes[$id].m_Mesh.instance.m_VertexData.m_VertexCount -gt 65000){throw ('Exported mesh exceeds legacy vertex budget: '+$kind)}
   if($kind -eq 'face') {
    $shape=$anim.Meshes[$id].m_Mesh.instance.m_Shapes;$original=@($shape.channels)
    $shape.vertices.Clear();$shape.shapes.Clear();$shape.channels.Clear();$shape.fullWeights.Clear()
    foreach($morph in $workspace.Morphs){$anim.CreateMorph($morph,$id,$morph.Name,$false,0.000001,0.0001) | Out-Null}
    $channels=@($shape.channels);$shape.channels.Clear()
    if($original.Count -ne $fit.face.imported_key_order.Count){throw 'Native expression channel count changed'}
    for($j=0;$j -lt $original.Count;$j++) {
     $key=$fit.face.imported_key_order[$j];$short=$key -replace '_0$',''
     $match=@($channels | Where-Object {$_.name -eq $key -or $_.name.EndsWith('.'+$short)})
     if($match.Count -ne 1){throw ('Cannot map native expression '+$key)}
     $ch=$match[0];$ch.name=$original[$j].name;$ch.nameHash=$original[$j].nameHash;$shape.channels.Add($ch)
    }
   }
   'BUILT '+$go.m_Name+' vertices='+$anim.Meshes[$id].m_Mesh.instance.m_VertexData.m_VertexCount
  }
  if($kind -eq 'outfit') {
   foreach($c in @($go.m_Component)) {
    $mb=$parser.Cabinet.LoadComponent($c.Value.m_PathID)
    if($mb -is [UnityPlugin.MonoBehaviour] -and $mb.m_MonoScript.instance.m_ClassName -eq 'ChaClothesComponent') {
     foreach($key in @('useColorN01','useColorN02','useColorN03','useColorA01','useColorA02','useColorA03')){$mb.Parser.type.Find($key).Value=[byte]0}
    }
   }
  }
  $bundle.AddComponent($go.m_Name,$go,(New-Object 'System.Collections.Generic.List[UnityPlugin.Component]'))
 }
 if($kind -eq 'outfit') {
  $mask=$parser.AddTexture([SB3Utility.Plugins]::ImportTexture((Join-Path $job 'body-mask.png')),$false,$false);$mask.m_Name='body_mask'
  $bundle.AddComponent($mask.m_Name,$mask,(New-Object 'System.Collections.Generic.List[UnityPlugin.Component]'))
 }
 if($kind -eq 'face') {
  foreach($spec in @(@('face_albedo','face-albedo.dds'),@('face_albedo_low','face-albedo.dds'),@('face_color_mask','face-color-mask.png'),@('face_color_mask_low','face-color-mask.png'),@('iris_L','iris-L.png'),@('iris_R','iris-R.png'))) {
   $tex=$parser.AddTexture([SB3Utility.Plugins]::ImportTexture((Join-Path $job $spec[1])),$false,$false);$tex.m_Name=$spec[0]
   if($spec[0] -like 'face_albedo*') {
    if($tex.m_TextureFormat -notin @([UnityPlugin.TextureFormat]::ARGB32,[UnityPlugin.TextureFormat]::RGBA32)){throw 'Skin albedo must remain uncompressed 32-bit color'}
    if($tex.image_data.Length -lt $tex.m_Width*$tex.m_Height*4){throw 'Truncated uncompressed skin payload'}
    'SKIN_FORMAT '+$spec[0]+' '+$tex.m_TextureFormat+' bytes='+$tex.image_data.Length+' mipmaps='+$tex.m_MipCount
   }
   $bundle.AddComponent($tex.m_Name,$tex,(New-Object 'System.Collections.Generic.List[UnityPlugin.Component]'))
  }
 }
 $preview=Join-Path $job 'preview-front.png'
 if(Test-Path -LiteralPath $preview) {
  $thumb=$parser.AddTexture([SB3Utility.Plugins]::ImportTexture($preview),$false,$false);$thumb.m_Name='thumbnail'
  $bundle.AddComponent($thumb.m_Name,$thumb,(New-Object 'System.Collections.Generic.List[UnityPlugin.Component]'))
 }
 $cab=$fit.cabs.PSObject.Properties[$kind].Value
 Write-Bundle $parser (Join-Path $job ('package/abdata/'+$bundle.m_Name)) $cab
}
$source.Dispose()
