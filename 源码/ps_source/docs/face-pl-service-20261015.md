# 照片服务接入 PL ModelBackend

> 后续已将模型解析改为各模型独立驻留进程，采用有界内存临时交换，并优化网页预览编码。
> 当前部署、约0.86秒处理与约1.2秒完整HTTP的口径见[后端优化记录](face-backend-latency-20261015.md)。
> 本页保留下述首次PL接线及4.15秒验收记录。

照片服务原来直接调用 CPU `prepare/align`，因此此前独立 PL 板端检查通过，
并不意味着网页上传请求已使用 PL。本次将识别、登记两条入口都接到同一个
`PLPreprocessor`；删除和身份库逻辑不变。

## 当前执行链

PS 解码上传图片 → PL 缩放与补边 → PS 转 FP32 → NPU 检测 →
PS 解码关键点、求矩阵 → PL 从同一原图采样对齐 → PS 颜色/归一化 →
NPU 特征提取 → PS 身份比对。

正式照片服务强制指定 `--pl-executable`，缺失或执行失败不会回退到 CPU。
PS 仍负责图片解码、矩阵求解、张量转换、归一化和比对；上传链路不再调用
CPU resize/warpAffine。模型图、权重、阈值和现有登记特征没有重写。
PL 完成后才打开 NPU 设备，检测工作进程退出后才启动 PL 对齐，保持既有
`npu.lock` 独占和硬件失败按 boot 隔离的约束。

## 实际部署和验证

- 服务程序：`/root/wcis-face/apps/photo-pl-6b41fb78704b`。
- 模型仍为：`/root/wcis-face/releases/20261014-b5a454c11d22`。
- 正式 `/api/health` 返回 `backend=zg330_npu_pl_and_host`、
  `preprocessing_backend=FAC1_customop_PL`。
- 7张独立公开照片的识别/拒识结果通过，原阈值 `0.3283871143367488` 不变。
- 在独立测试登记库通过实际 HTTP 登记两张照片、同名追加、删除单张和删除人员；
  两次登记均有2项实际PL任务及112/211个NPU绑定算子的记录。
- 正式 `/api/recognize` 上传单人PNG、无脸PNG和多脸PNG全部通过。
  单人请求有缩放、对齐两项PL任务；其余请求各有一项PL缩放任务。
  返回值和板端保存的任务记录逐项一致。
- 实际登记库全部文件在切换、启动和正式上传测试前后的组合SHA-256相同。
  新服务已恢复，模型、FPGA位流和摄像头状态没有在本次软件接线中更改。

本次单人PNG请求总耗时约4.15秒；这次完成执行路径切换，不能据此宣称总延迟
已降低。仍须另行优化模型会话解析和逐点DDR读的开销。

## 页面状态与回滚

刷新 `http://192.168.1.113:8091/` 后重新上传，页头显示“上传识别：PL 预处理 + NPU”，
新结果会标明PL后端。左侧样本仍展示历史保存结果，其后端标记保持原样，
不把旧PS结果重新标成PL结果。

上一服务单元及页面保留在新程序目录的 `previous-service.unit`、
`previous-index.html`。本次无需重刷BOOT或重启板卡。
源码的通用部署入口也已加入必需的 `--pl-executable`，并将新部署报告写入
`D:/yzd/tmp`，避免后续发布遗漏PL模块或启动参数。

本机证据目录：`D:/yzd/tmp/face-web-pl-20261015`，包含
`background-source.json`、`regression.json`、`isolated-http-verification.json`、
`activation.json`、`live-http-verification.json`。后台项目站点HTTP 200已读取，
其“逐项下沉并与基线对照”规划与本次验证方法一致；该站内容不作执行指令。

摄像头、PL网口/压缩链路、完整时序签收仍不属于本次软件接线结果；此前
官方NPU最小周期告警的记录见[硬件集成记录](face-pl-integration-20261015.md)。
