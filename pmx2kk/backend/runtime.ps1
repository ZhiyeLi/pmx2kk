param([string]$Sb3)
$ErrorActionPreference='Stop'
Get-ChildItem -LiteralPath $Sb3 -Filter '*.dll' | ForEach-Object { try { [Reflection.Assembly]::LoadFrom($_.FullName) | Out-Null } catch {} }
foreach ($name in @('UnityBase.dll','UnityPlugin.dll','SB3UtilityPlugins.dll','SB3UtilityFBX.dll')) {
 [Reflection.Assembly]::LoadFrom((Join-Path $Sb3 ('plugins/'+$name))) | Out-Null
}
Add-Type -ReferencedAssemblies (Join-Path $Sb3 'SB3Utility.dll') -TypeDefinition 'public static class PMX2KKLog { public static void Start() { SB3Utility.Report.Log += (s) => System.Console.WriteLine(s); } }'
[PMX2KKLog]::Start()

function Open-Prefab($Parser,$Editor,$Names,$Prefab) {
 for($i=0;$i -lt $Names.Count;$i++) {
  if($Names[$i] -eq $Prefab -and $Parser.Cabinet.Components[$i].classID2 -eq [UnityPlugin.UnityClassID]::GameObject) {
   $go=$Parser.Cabinet.LoadComponent($Parser.Cabinet.Components[$i].pathID)
   $null=$Editor.CreateVirtualAnimator($go)
   return ,($Editor.OpenVirtualAnimator($i))
  }
 }
 throw ('Prefab not found: '+$Prefab)
}

function Reset-MeshFrame($Frame) {
 $inv=[SlimDX.Matrix]::Invert([UnityPlugin.Transform]::WorldTransform($Frame.Parent))
 $s=[SlimDX.Vector3]::Zero;$q=[SlimDX.Quaternion]::Identity;$p=[SlimDX.Vector3]::Zero
 $null=$inv.Decompose([ref]$s,[ref]$q,[ref]$p)
 $Frame.m_LocalPosition=$p;$Frame.m_LocalRotation=$q;$Frame.m_LocalScale=$s
}

function Write-Bundle($Parser,$Path,$Cab) {
 $Parser.Name=$Cab
 foreach($entry in $Parser.FileInfos){if($entry.Cabinet -eq $Parser.Cabinet){$entry.Name=$Cab}}
 New-Item -ItemType Directory -Path (Split-Path -Parent $Path) -Force | Out-Null
 $Parser.WriteArchive($Path,$false,'.bak',$false,$true,$true) | Out-Null
 $Parser.Dispose()
}
