# 环境搭建

## 1. 版本与依赖

| 组件 | 本次验证版本 / 要求 | 获取入口 |
|---|---|---|
| 系统 | Windows；64 位 PowerShell / .NET 桌面环境 | 系统自带 Windows PowerShell |
| Blender | **4.5.0 LTS** | [官方 4.5 下载目录](https://download.blender.org/release/Blender4.5/) |
| mmd_tools | 本地验证 **4.5.13**，兼容 Blender 4.5 的扩展 | [项目](https://github.com/MMD-Blender/blender_mmd_tools) / [Blender 扩展](https://extensions.blender.org/add-ons/mmd-tools/) |
| SB3Utility | **24.3.3**，完整解压的 Windows x64 包及其运行库 | [作者 Releases](https://github.com/enimaroah/SB3Utility/releases) |
| 游戏 | 自备原版 Koikatsu，Unity **5.6.2**，本地完整资源 | 不含 Sunshine |
| KK mod 环境 | BepInEx、BepisPlugins 中的 Sideloader / ExtendedSave | [BepInEx](https://github.com/BepInEx/BepInEx) / [BepisPlugins](https://github.com/IllusionMods/BepisPlugins)；使用适配原版 KK 的包 |
| 彩色瞳孔 | KK OverlayMods，验证环境 **6.3** | [OverlayMods](https://github.com/ManlyMarco/Illusion-Overlay-Mods)；选择 KK 版本 |
| Studio 材质模板 | 本地 Unity 5.6 bundle，首个 Material 使用 `Shader Forge/main_item_studio` | 见下一节 |

上述是本次验证组合，不表示所有更新版本都已验证。插件用 Blender 自带 Python 启动后台任务，不要求安装 Conda、系统 Python、MCP 或代理服务。教程中的辅助脚本也能用 Blender 执行。

## 2. 准备 Studio 材质模板

插件用一个已有 Studio 材质作为头发和衣服的材质基底；**任意 `.unity3d` 文件不能替代它**。v0.2.1 后端会取 bundle 的首个 Material，因此名称相似但内容不同的 bundle 也可能无效。

本次实际验证的模板位于本机已安装的 `[JustWaitAMinute] Porygon 1 v1.0.zipmod` 中，成员路径是：

```text
abdata/studio/illusionmods/example_studio_item.unity3d
```

若你自己的 Sideloader Modpack 中已经有此文件，可用下面的脚本只读提取。先将仓库或示例文档包解压到一个工作目录，在该目录打开 PowerShell。把以下示例路径换成你的实际路径：

```powershell
& 'D:\Apps\Blender 4.5\blender.exe' --background --factory-startup --python-exit-code 1 --python tools/extract_studio_template.py -- --mod 'D:\Games\KK\mods\Sideloader Modpack\JustWaitAMinute\[JustWaitAMinute] Porygon 1 v1.0.zipmod' --output 'D:\pmx2kk-work\dependencies\studio_template.unity3d'
```

脚本只读取指定 ZIP 成员，校验大小 **92717 字节** 和 SHA256 后写入新文件，已有目标文件会拒绝覆盖。验证模板的 SHA256：

```text
877740bae73b56f746fc761de20d0ae652ff16e7a028840a52ad06c06087cbed
```

模板不在本仓库、安装包或示例包中。如果没有这个 mod，可以参考 [KoikatsuModdingTools](https://github.com/IllusionMods/KoikatsuModdingTools) 的 [Studio Item Example](https://github.com/IllusionMods/KoikatsuModdingTools/tree/master/Assets/Examples/Studio%20Item%20Example)，在 Unity 5.6.2 中按上游 `_readme.txt` 构建自己的 Studio 示例 bundle，再用 SB3Utility 检查首个材质及 shader。**自行构建的替代模板未纳入本次验收，仍需在 KK 验证材质效果。** 本项目不提供受限 mod 的镜像下载。

## 3. 安装 Blender 插件

从 Release 下载 `pmx2KK-0.2.1.zip`。Blender 4.5.0 → 编辑 → 偏好设置 → 插件 → 右上角菜单 → 从磁盘安装，选择该 ZIP，然后启用 pmx2KK。这是传统插件 ZIP；不需要解压后手工合并到 Blender 安装目录。

通过 mmd_tools 官方发行包安装 MMD Tools。避免同时加载旧版 CATS / MMD 插件造成注册冲突。pmx2KK 后台使用隔离配置，不修改全局插件设置；当前交互界面仍需要没有冲突的 Blender 环境。

## 4. 填写五项路径

| 首选项 | 应指向 |
|---|---|
| 原版 KK 目录 | 包含 `abdata/`、`BepInEx/`、`UserData/` 的游戏根目录 |
| SB3Utility 目录 | 包含 `SB3Utility.dll` 与 `plugins/` 的解压目录，不是 EXE 文件 |
| mmd_tools 模块目录 | 名为 `mmd_tools`、含 `__init__.py` 的文件夹；Blender 扩展通常位于用户配置的 `extensions/blender_org/mmd_tools/` |
| 本地 Studio 材质模板 | 上一节得到的 `studio_template.unity3d` |
| 基础人物卡（可选） | 本地原版 KK 女性 PNG 卡；要复现完整彩色眼睛，请提供该项 |

基础卡建议用简单、无额外插件依赖的女性卡，后发/侧发/扩展发尽量为空。转换替换头型、前发和上衣，重置体型/脸型滑块并清理饰品；未替换的头发依赖仍会保留。若空发型来自 mod，该 mod 也必须安装。不要使用 KKS 卡、图片编辑器重存的卡或从网页压缩后的预览图片。

KK 下应存在以下资源（缺失时不要从其他游戏版本拼凑）：

```text
abdata/chara/oo_base.unity3d
abdata/chara/bo_head_00.unity3d
abdata/chara/bo_hair_f_08.unity3d
abdata/chara/co_top_10.unity3d
abdata/list/characustom/00.unity3d
```

## 5. 目录规划与首次检查

例如原模型放 `D:\Models\角色\`，工作目录用 `D:\pmx2kk-work\jobs\`。不要把工作目录设为原模型目录或其上级。保留 PMX 与贴图相对路径。

在 N 面板选择 PMX → 检查 PMX。成功后出现部件列表，任务目录内有 `recipe.json`、`inspect.json` 和 `source.blend`。接着按照[使用教程](USER_GUIDE.md)分类和转换。首次转换会从本地 KK 提取模板缓存，因此比后续重建更慢。
