> 历史记录：本目录旧 site-template.html 已移出交付包。当前网页仅使用 ps_source/npu_photo/site-template.html；请按包根 README 和 ps_source/docs/website-current.md 操作。以下正文描述 2026-10-31 的旧基线。

# 540p r2 发布基线（2026-10-31）

操作入口：[发布与回退说明](../../../ps_source/docs/release-runbook.md)。文件映射：[对应表](../../../ps_source/docs/release-source-map.md)。

这里保存冻结的期望值和页面模板，不是自动安装包，也不是可直接覆盖运行目录的文件树。

- `app-manifest.json`：r2 主应用的 39 个受管文件。
- `recorder-manifest.json`：独立录像服务的 7 个运行依赖；不把主应用中的同名副本当成录像实际入口。
- `services-manifest.json`、`startup-manifest.json`：本次四个服务单位和启动前置文件。
- `baseline-manifest.json`：`outputs/release-baseline-20261031` 保存副本的完整性；不证明以后板端状态。
- `source-map.json`：本地源文件、生成页面、历史副本、原生程序分别标注。
- `site-template.html`：保留当前完整首页的不变部分，由 `scripts/assemble_camera_site.py` 插入现有 `npu_photo/camera_panel.html` 与版本号。
- `owner-build.json`：学校历史构建收据；源码包位于 `D:/yzd/tmp/preview-maintenance-20261030/integration-source.tar.gz`。不是本次重新编译的证明。

完整 r2 和 r1 回退副本位于 `outputs/release-baseline-20261031/`；原始证据仍保留在各次任务目录。之后发布应新增版本目录，不更新本目录的期望散列来掩盖差异。不能将应用根目录旧 index.html 或 camera_panel.html 用作正式首页覆盖来源。
