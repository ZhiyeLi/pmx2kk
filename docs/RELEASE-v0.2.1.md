# pmx2KK v0.2.1

Blender 4.5.0 的 PMX → 原版 Koikatsu 转换插件，输出原生头型、前发、整套上衣 zipmod，以及可选的人物卡。无需额外的 pmx2KK 游戏运行时插件。

本版修复眼周/嘴周环状着色、腮部异常鼓起和皮肤渐变色差：使用源 UV 采样与连续补色、有界平滑脸型位移、接缝一致位移与法线更新，皮肤通过未压缩 DDS mip 链导入 Unity ARGB32。保留原生拓扑、UV 与 81 个表情通道，以及已验收的比例、身体适配和虹膜。

下载：

- `pmx2KK-0.2.1.zip`：Blender 插件安装包。
- `pmx2KK-0.2.1-examples-and-docs.zip`：完整中文教程、三个示例配置与辅助脚本，无模型资源。
- `SHA256SUMS.txt`：上述两个文件的 SHA256。

文档补充（2026-10-30）：新增 `pmx2KK-0.2.1-examples-and-docs-illustrated.zip` 与 `SHA256SUMS-illustrated.txt`，收录三个示例的 18 张 KK Studio 实际验收截图，并在 README 末尾加入作者的话。可直接查看[最新图文复现](https://github.com/ZhiyeLi/pmx2kk/blob/main/examples/README.md)与[README](https://github.com/ZhiyeLi/pmx2kk/blob/main/README.md)。本次仅补充文档，原插件包和 v0.2.1 标签保持原样。

安装及复现请从 [README](https://github.com/ZhiyeLi/pmx2kk/blob/v0.2.1/README.md) 开始。需要自备 Windows、原版 KK、mmd_tools、SB3Utility、正确 Studio 材质模板；完整彩色瞳孔卡需要女性基础卡与 KK OverlayMods。不支持 Sunshine。衣服目前是整套上衣，长发/裙摆物理需要人工适配，面部是近似拟合。

自主源码、文档与配置仅限非商业使用，见仓库 LICENSE；msgpack 按 Apache-2.0。三个模型均未另获再分发授权，因此不包含 PMX、贴图、人物卡或 zipmod。

模型来源与规约：德丽莎（神帝宇 / miHoYo）见 [作者模型页](https://www.aplaybox.com/details/model/vanHVdtz5qq6)；女魔王（星塔旅人 / 魔王酱酱酱_ / 悠星网络）见 [作者公告](https://www.bilibili.com/video/BV1TuQmBVEon/)；利维坦（神帝宇 / 深空之眼）见 [作者作品页](https://www.aplaybox.com/u/359396473/model)，独立配布页尚未确认。三者禁止二次分发和商业用途，并限制成人、极端宗教、血腥恐怖及攻击性作品；请阅读原下载包完整规约。允许使用本工具不等于允许分发转换产物。
