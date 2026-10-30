# 实现与开发

## 数据流

```text
PMX + 本地贴图
  -> Blender 后台 inspect -> source.blend + inspect.json
  -> 用户检查 -> recipe.json
  -> 本机 KK 模板缓存 + 归一化 / 蒙皮 / 脸型 / UV 采样
  -> converted.blend + FBX + 贴图 + fit.json
  -> SB3Utility PowerShell 后端 -> Unity bundles
  -> Sideloader zipmod + 可选原生 PNG 卡（含 KSOX 虹膜）
  -> KK 内独立验收
```

后台 Blender 使用隔离用户配置和禁用用户 site-packages 的环境；它不打开交互场景。SB3Utility 在独立 PowerShell 中操作模板副本，原游戏文件只读。运行时模型是原生部件，不依赖 pmx2KK 自定义 C# 桥接插件。

| 文件 | 职责 |
|---|---|
| `pmx2kk/__init__.py` | Blender UI、参数、异步任务、预览载入 |
| `core.py` | 配方、哈希身份、骨骼映射、分类规则 |
| `worker.py` | MMD 导入、材质拆分、隔离任务入口 |
| `convert.py` | 本机模板、身体适配、头发绑定、FBX 与预览输出 |
| `head.py` | 头部特征点、归一化、有界平滑脸型拟合 |
| `appearance.py` | 脸部与虹膜贴图转移、连续皮肤补色、DDS 写入 |
| `backend/*.ps1` | SB3Utility 模板提取、bundle 构建、原生形态键与材质检查 |
| `packaging.py` / `card.py` | Sideloader 清单与资源列表、原版卡与 KSOX 数据 |
| `vendor/msgpack/` | Apache-2.0 的独立第三方 MessagePack 实现 |

身份由 PMX SHA256 生成：`p<前12位>n21` / `local.pmx2kk.<key>`。同一源文件重建复用 ID；不同版本命名空间隔离。该标识只基于 PMX，不基于贴图文件；贴图变动需主动重建。

## 开发与构建

Python 3.10+ 或 Blender 自带 Python 足够运行发布辅助脚本，不需要 pip：

```powershell
python -m unittest discover -s tests -v
python tools/build_release.py
```

生成 `dist/pmx2KK-0.2.1.zip`、`dist/pmx2KK-0.2.1-examples-and-docs.zip` 和 SHA256 清单。构建脚本使用明确文件列表、固定 ZIP 时间戳，不扫描用户模型或工作目录。安装包只有 `pmx2kk/` 顶层目录。

核心转换需要 Blender 与本机游戏依赖；不能用普通 Python 单元测试代替 KK 验收。`worker.py` 的命令形式为 `blender --background --factory-startup --python-exit-code 1 --python pmx2kk/worker.py -- <recipe.json> inspect|convert|build`，但调用者必须像 UI 一样设置隔离 `BLENDER_USER_CONFIG`、`PYTHONNOUSERSITE=1` 和所有路径。普通用户建议使用 UI。

## 修改和贡献

提交小范围修改，描述输入类型、错误表现、修复后行为及真实测试范围。涉及面部时检查 UV 不变、81 个表情通道、接缝、法线与实际皮肤格式；涉及蒙皮时在 KK 验证动作和换装；涉及卡时验证保存重载和瞳孔。不要提交本地模板、游戏 DLL、模型、贴图或完整 recipe。

原生脸与 PMX 源 UV 不相同，因此脸部必须重新采样；直接替换贴图会产生错位。Blender 烘焙图正确也不代表 Unity 中正确，打包阶段必须核对纹理格式与实际 payload，不能只改文件后缀。有关 API 的原始参考：[Blender 4.5](https://docs.blender.org/api/4.5/)、[Unity 5.6 Mesh](https://docs.unity3d.com/560/Documentation/ScriptReference/Mesh.html)、[SB3Utility](https://github.com/enimaroah/SB3Utility)。
