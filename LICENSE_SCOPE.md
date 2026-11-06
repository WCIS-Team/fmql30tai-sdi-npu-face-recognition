# MIT 许可的适用范围

自 2026-11-06 起，anxianji11-pixel 对本仓库中由其创作且有权授权的原创代码和配套文档采用根目录 [MIT License](LICENSE)。这允许使用、修改、商用和再分发这些原创内容，包括闭源衍生使用；仍须按 MIT 保留版权与许可声明。

根目录 MIT **不覆盖**以下内容，也不改变其原条款：

| 范围 | 适用规则 |
|---|---|
| 上游预训练模型及其转换、量化、编译产物 | 模型权利人的许可；特别是 InsightFace 权重的非商业研究限制 |
| `源码/fpga_source/rtl/wcis/jpeg_vendor/` 与 `源码/ps_source/rtl/vendor/mjpegzero/` | mjpegZero 的 Apache-2.0 + Commons Clause v1.0 |
| `FMQL30TAI-Install/vendor/` 中的依赖、配套 `.dist-info`、第三方许可文本 | 各依赖的原许可，包括 Paramiko 的 LGPL-2.1-or-later |
| `源码/ps_source/model_backend/face_pad.py` 中上游改编内容及其他带既有许可的文件 | 保留原 Apache-2.0 等条款、版权和修改声明；本次不重许可这些文件 |
| InsightFace 等参考实现中被复用的第三方部分 | 对应上游条款和署名；不得用本项目作者名替换原作者 |
| 厂商 IP、SDK、案例、启动文件、DCP、生成资源及其他受限材料 | 厂商或其他权利人的授权；未随公开版提供也不代表获准再分发 |
| `HA4FPAI.sh` 及其他非 anxianji11-pixel 作者的独立贡献 | 由对应权利人决定；本次不代替 takomitkm 或其他贡献者授权 |
| 照片、录像、人员特征数据和引用的外部资料 | 各自的版权、数据和使用条件，不能仅依据根目录 MIT 使用 |

目录边界是帮助识别的索引，不是把未列出的第三方文件自动变成原创内容。文件头、同目录 LICENSE/NOTICE、上游来源记录或依赖元数据中已有的条款继续有效。权属不清时应向维护者确认，不推定 anxianji11-pixel 有权替他人授权。

对第三方文件的原创修改也不能免除该文件原许可要求；根目录 MIT 不撤销先前有效的文件级许可。全部例外的来源索引见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)，作者说明见 [NOTICE.md](NOTICE.md)。

GitHub 显示的根级 MIT 标签仅概括本项目原创部分，不能作为整个仓库、全部模型或完整硬件产品可按 MIT 商用的证明。
