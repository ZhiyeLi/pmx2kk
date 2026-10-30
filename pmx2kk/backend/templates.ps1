param([Parameter(Mandatory=$true)][string]$Recipe,[Parameter(Mandatory=$true)][string]$Cache)
$ErrorActionPreference='Stop'
trap { $_.Exception.ToString();exit 1 }
$r=Get-Content -LiteralPath $Recipe -Encoding UTF8 -Raw | ConvertFrom-Json
. (Join-Path $PSScriptRoot 'runtime.ps1') -Sb3 $r.sb3
New-Item -ItemType Directory -Path $Cache -Force | Out-Null
# All parsers work on local copies. SB3 can create a .swap next to a bundle.
$specs=@(@('hair','bo_hair_f_08','p_cf_hair_f_23'),@('body','oo_base','p_cf_body_bone'),@('head','bo_head_00','p_cf_head_00'),@('outfit','co_top_10','p_o_top_suspend_t08'),@('outfit_low','co_top_10','p_o_top_suspend_t08_low'))
foreach($spec in $specs) {
 $out=Join-Path $Cache $spec[0];New-Item -ItemType Directory -Path $out -Force | Out-Null
 $bundle=Join-Path $out 'original.unity3d'
 Copy-Item -LiteralPath (Join-Path $r.game ('abdata/chara/'+$spec[1]+'.unity3d')) -Destination $bundle
 $parser=New-Object UnityPlugin.UnityParser $bundle
 $editor=New-Object UnityPlugin.Unity3dEditor ($parser,$false);$names=$editor.GetAssetNames($false)
 $va=Open-Prefab $parser $editor $names $spec[2]
 $anim=New-Object UnityPlugin.AnimatorEditor $va
 [UnityPlugin.Plugins]::ExportFbx($va,[object[]]$anim.Meshes.ToArray(),[object[]]@(),0,0,$false,0.25,$false,(Join-Path $out 'template.fbx'),'.fbx',$true,$true,$true,1.0,$true,$false,$false)
 $frames=foreach($f in $anim.Frames){[PSCustomObject]@{name=$f.m_GameObject.instance.m_Name}}
 $frames | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'frames.json') -Encoding UTF8
 $parser.Dispose()
}
$out=Join-Path $Cache 'lists';New-Item -ItemType Directory -Path $out -Force | Out-Null
$bundle=Join-Path $out 'original.unity3d'
Copy-Item -LiteralPath (Join-Path $r.game 'abdata/list/characustom/00.unity3d') -Destination $bundle
$parser=New-Object UnityPlugin.UnityParser $bundle
$editor=New-Object UnityPlugin.Unity3dEditor ($parser,$false);$names=$editor.GetAssetNames($false)
for($i=0;$i -lt $names.Count;$i++) {
 $c=$parser.Cabinet.Components[$i]
 if($c.classID2 -eq [UnityPlugin.UnityClassID]::TextAsset -and $names[$i] -match 'bo_head|co_top|mt_eye') {
  $asset=$parser.Cabinet.LoadComponent($c.pathID);$asset.Export($out)
 }
}
$parser.Dispose()
