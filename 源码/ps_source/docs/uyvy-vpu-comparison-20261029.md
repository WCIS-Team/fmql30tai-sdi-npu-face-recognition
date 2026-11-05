# 1080p UYVY / NV12 实测与优化问题核对（2026-10-29）

本轮接续用户授权的性能对比。任务目录沿用 `D:/yzd/tmp/uyvy-vpu-compare-20261028`，实际构建、板测和恢复日期为客户端 2026-10-29。未替换正式应用，未写 BOOT、DTB/uEnv 或重新生成位流。补充读取 `D:/xiangmuwendang/WCIS-FPAI/repos/FPAI30TAI图像FPGA/README.md`，它只作背景，实测以本轮收据为准。

## 结论和边界

- 1080p 的 RGB565→CPU NV12→VPU 路线能正常完成有限空闲采集/编码；本轮约 27.15 fps，但进程 CPU 平均 1.61 核。不能由像素量增至四倍直接断言此路线不可行。
- 原 BOOT 下 UYVY 输入已被 VPU 接受，试验程序的 JPEG 发布计数达到 73，随后帧停止更新，快照新鲜度检查失败。尚未取得完整解码/颜色验收和稳定性能窗口，不能把这次测试记成稳定预览成功，更不能给出有效 CPU 节省比例。
- 在先行 NV12 1080p 与固定旧帧人脸/防伪共存测试中，采集线程触发 `Owner camera DMA failed; no retry`。这不是 UYVY 测试的故障，也不能单凭它确定 CPU、DDR、SDK 复位或其他根因。
- 本轮没有完成有效的两路线持续性能配对，没有证明新路线适合正式部署。当前继续使用原 960×540 PS/VPU 预览。

## 实现与构建

仅在任务 `source/` 副本修改 `ps_app/src/wcis_camera_owner.cpp` 与 `wcis_owner_vpu.hpp`。两条路线均为 1920×1080、30 fps 上限、JPEG 质量 80；源格式分别为 RGB565 与 PL 输出 UYVY。UYVY 路线省去 CPU 的 RGB565→BGR→I420/NV12 转换，但仍使用 SDK 原有整帧 memcpy 入队。副本保留双缓冲、唯一 SDK 所有者、分配窗口、读回一致性、硬件锁和故障隔离检查。禁止把试验 1080p 原帧当成现役 540p 识别快照；共存负载使用固定 540p 旧帧。

学校入口 `10.101.54.192:18222` 主机身份与原固定记录不符，未修改信任记录或通过该入口发送凭据。改用原局域网入口 `192.168.1.102`，两级主机身份校验通过。复核工具路径和已有编译任务后，在 `D:/yzd/tmp/wcis-camera-preview-uyvy-85b19727` 隔离构建；显式工具 PATH 与 MSYS2 参数设置，缓存/临时目录位于本任务，不修改共享 SDK。

构建退出 0；二进制 SHA256 `aeadfb67a4afe4143eba2dc8fc997004793b02efacc939b8050c3413d9e8f4b3`。源码归档 SHA256 `321a33d7a7286b1ab2fc722eba833ffd5337598ecffa8be25e963b679ed19439`。详见 `build-receipt.json`、`source-manifest.json`、`source-changes.patch`、`build.log`。编译成功不等于板测成功。

## 板测结果

| 项目 | RGB565→CPU NV12→VPU | PL UYVY→VPU |
|---|---|---|
| 原生输入目标 | 1920×1080 | 1920×1080 |
| 有效空闲窗口 | 6.00327 秒、163 帧、27.1519 fps | 未取得有效持续窗口；发布计数 73 后停止更新 |
| 进程 CPU（单核口径） | 1.61412 核，约 161.4% 单核 | 不提供有效比较值 |
| 原帧复制 wall 时间 | 2.43276 ms/发布帧 | 不提供稳定值 |
| 图像准备 wall 时间 | 20.09699 ms/发布帧 | 分支已省转换，但未通过连续验收 |
| VPU 入队 wall 时间 | 2.79862 ms/发布帧 | 不提供稳定值 |
| JPEG 解码几何 | 1920×1080 | 未完成同帧解码/颜色检查 |
| 与人脸/PAD 同跑 | 先行测试触发 camera DMA 故障 | 未运行，不能称为通过 |

CPU 来自 `/proc/<pid>/stat` 的用户态和内核态 CPU 时间差 / 单调时钟差；它是测试进程所有线程总计，不是整机占用或 VPU 利用率。准备/入队计时是 wall 时间；计数异步且有 VPU 在途帧，不能严格相加或归因全部 CPU。帧率为板端发布计数，不是浏览器显示帧率；frame_age 使用采集请求时间下界，不是精确曝光至显示延迟。随机/真实画面、SDK/OpenCV 版本及负载窗口不同，不能把此次 1.61 核与旧 540p 约 0.48 核直接当作严格倍率对比。

UYVY 协商记录为单平面、bytesperline=3840、sizeimage=4147200，未因格式不被驱动接受而失败。随后新鲜度失败时，状态显示 captured=74、encoded=73、camera_requests=75。尚不能确定停帧发生在采集、VPU 缓冲交接、驱动阻塞或其他环节。未以更宽的新鲜度阈值放行，也未在故障启动上重试 SDK。

## 失败保存与现场恢复

两次失败分别在启动 `b1419f84-7dfc-4b11-926b-e2f5f2241964` 和 `d262832b-eece-4f76-99f9-ae17917cdd80`。程序故障退出未取得正常 SDK 关闭证明，因此保留本次启动隔离标记，用原启动镜像正常重启恢复；没有删除标记继续调用硬件。

最终 NV12 空闲测试正常退出，captured=encoded=198，requests=199，末帧排空 1，camera_pending=false，sessions_released=true、sdk_closed=true，随后恢复原正式服务。最终启动 `914b5737-515e-4847-b619-3aa88b26c5ef`，BOOT SHA256 仍为 `f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`，正式应用清单散列全部匹配；健康、硬件准入、模型缓存 ready，540p 预览帧号推进，录像 off，正式图库散列与本轮已挂载基线一致。一轮真实摄像头识别成功，现场无人脸，约 508.04 ms，不能当作真人/攻击样本验收。

证据：任务 `fault-inspection.json`、`idle-failure.json`、`recovery-output.txt`、`recovery-health.json`、`results/`、`idle-results/`、`nv12-results/comparison.json`、`final-verification.json`；板端各候选目录 `uyvy-vpu-compare[-idle/-nv12]-20261029` 保留原始日志与收据。

## 新补充优化记录的修正与后续排序

对 `cpu-load-baseline-20261029.md` 的测量与推断应分别使用：

1. “1080p VPU 不可行、只能走 PL JPEG”不能由四倍像素成本推导，本轮已完成有限 1080p 编码；但共存与稳定性仍未通过。
2. 现有源码有 YUV422 格式选择，且原 BOOT 上已协商并发布 UYVY JPEG 计数，因此“免转换必须改位流”不能作为已确认结论。实际流畅度、颜色和同帧正确性仍待验证。
3. 关闭录像后 10 ms 轮询、OpenCV 线程数、状态文件发布频率是独立软件优化候选。收益必须测量，不能把估算相加写成已实现的 CPU 降幅。
4. owner 是 C++ 程序，应使用 C++ `cv::setNumThreads` 或适当进程配置验证；Python `cv2.setNumThreads` 只改变所在 Python 进程，不能直接调整 owner。
5. 状态文件降频需要核对各消费者的新鲜度和心跳契约，不能只按写文件次数推断安全；录像 off 是否保留预录环形缓存也须核对模式契约。

本轮未部署这三项优化，避免在格式对照中混入其他变量。根据剩余交付时间，优先验证上述可回退软件改动，暂不把 UYVY 持续预览或新 NV12 位流当作保证完成项。

本文同步补充到 `D:/bigfuture/竞赛/记录/2026-10-29.md`，保留已有记录和来源文档。
