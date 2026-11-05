# 当前网页源码与运行入口

交付基准：2026-11-04 用户确认的“直播 / 录像 / 数据库”页面。说明默认收起，点击“说明”展开，再次点击收起。网页操作见包根目录《网站访问指南》。

## 只从这些文件修改

- `../npu_photo/site-template.html`：主站模板。
- `../npu_photo/camera_panel.html`、`camera_panel.js`：直播区块及交互。
- `../npu_photo/site_app.js`：切页、人员库、手机/电脑拍照登记。
- `../npu_photo/recording_embed.js`：载入录像页。
- `../npu_photo/recording_panel.html`、`recording_panel.js`：录像页面。
- `../scripts/serve_desktop_site.py`：电脑摄像头的本机入口。

人员登记使用打开网页的设备摄像头，先预览，再确认上传。历史样本入口已移除。实际手机和实体电脑摄像头尚未现场验收，已有模拟采集流程与正式页面检查证据。

## 运行副本

主站唯一入口是 `../../board_runtime/reference_release/app/site/index.html`，同目录保存主站三个脚本。H.264 播放器由主站后端单独提供，保留在 app/h264_player.js。录像服务与页面使用 `../../board_runtime/reference_release/recorder/`。

重新组装主站时，在包根目录运行下例，将输出放在包外：

```powershell
python -B ps_source/scripts/assemble_camera_site.py --template ps_source/npu_photo/site-template.html --panel ps_source/npu_photo/camera_panel.html --version 20261104-copy-1 --out D:/yzd/tmp/site-rebuilt-current.html
```

更新时同步 site/ 下页面与脚本，以及 recorder/ 下两份页面文件；不要从旧发布目录恢复网页。版本参数对应当前脚本缓存标识，后续修改应更新版本。

源码与板端安装文件分开放置，属于必要的开发/运行副本。运行目录根部的重复页面和未使用的录像副本已移出。旧 540p-r2 网页模板和本轮迭代记录已归档包外；其他历史报告不代表当前网页或新的硬件验收。

当前文件与在线网页的核对结果及清理去向见 `../../logpack/website-current/verification.json`。本轮只清理交付包，没有改动正在使用的网站、人员资料、录像、模型或 BOOT。

回收站中点击“← 返回录像”即可回到全部录像；存储区按钮也随当前列表切换为“返回录像”。范围下拉框变更后立即刷新列表。此修复不更改录像或回收站内容。
