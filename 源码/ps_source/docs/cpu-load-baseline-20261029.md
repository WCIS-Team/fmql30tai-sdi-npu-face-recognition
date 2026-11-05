# CPU/VPU 负载基线与 PL 预览收益复核（2026-10-29）

**本文为只读测量记录：未修改文件、服务、位流或启动分区，未打开 SDK，未访问 FAC1/NPU。测量窗口 2026-10-29 01:35～01:45（Asia/Shanghai），板卡启动 `b1419f84-7dfc-4b11-926b-e2f5f2241964`。**

> **后续修正（2026-10-29 晚）**：同日后续记录 [PL 原始画面直送 VPU](pl-direct-vpu-20261029.md) 已推翻或更新本文以下结论——
> 1. “1080p 预览在 VPU 上成本约 4 倍、不可行”：后续已跑通 1080p NV12 27.15 fps 与 UYVY→VPU H.264 900 帧/29.9 s；当前结论是“1080p 与 NPU 共存未通过”，不是分辨率不可行。
> 2. “免转换只能让 PL 输出 UYVY/RGBA，属于位流改动”：原 BOOT 上 UYVY 已被 VPU 协商并接受，不需要改位流。
> 3. “三项软件优化尚未实施”：后续已实现并部署（`camera-psopt-20261029`、`recording-psopt-20261029`），两进程合计 0.6380→0.3896 核；owner 的线程设置是 C++ `cv::setNumThreads(2)`，不是 Python。
> 本文其余测量数据仍按当时口径有效。

## 结论

1. 现役系统空闲时整机 CPU 约 18%～22%（4 核），owner 以 29.7 fps 稳定编码 960×540，没有观察到“VPU 已到极限”。
2. `wcis_camera_owner` 的 0.48～0.49 核是最大单点；其中 RGB565→BGR→I420 转换实测占 0.16～0.26 核，其余主要是帧拷贝、每帧两次文件发布和 VPU ioctl。
3. 实测枚举的 VPU 编码输入格式**没有 RGB565**，因此“RGB565 直接喂 VPU、省掉转换”不可行；要免转换只能让 PL 输出 UYVY/RGBA，属于位流改动。
4. 960×540 下 PL 预览的净 CPU 收益预计只有 0.1～0.35 核（PS 侧要增加 UDP 重组，普通画面估算 0.1 核、高噪声实测 0.32～0.40 核）；三项纯软件改动即可回收约 0.22 核。1080p 预览在 VPU 上成本约 4 倍，不可行，只能走 PL JPEG。
5. VPU 以 29.7 fps 工作受 `fps_limit=30` 限制，不能据此推断 30 fps 以上的硬件余量；本轮未做更高帧率试验。

## 测量环境与方法

- 板卡 `192.168.1.113`，启动 `b1419f84-7dfc-4b11-926b-e2f5f2241964`，当时 uptime 7:43，4 核，内存 993 MB，load 1.24/0.99/0.98。
- 只读 SSH，沿用项目既有文档凭证，未输出凭证内容；未打开 SDK，未启停服务。
- 命令：`top -b -n 2 -d 5`；两次读取 `/proc/stat`；逐个读取 `/proc/305/task/*/stat`；两次读取 `/dev/shm/wcis-owner-bre_jzrg/status.json`；`v4l2-ctl -d /dev/video0 --list-formats-out` 与 `--list-formats`；板端 `python3` 跑 OpenCV 转换基准。
- 站点当时空闲：`status.json` 的 `commands=273`（自启动约 7.7 小时），没有持续识别请求。

## 实测数据

| 项 | 数值 | 来源 |
|---|---|---|
| 4 核整机忙 | 17.9%（`/proc/stat` 5 s 差：busy 355 / total 1988） | 只读采样 |
| `top` 第二帧 | `%Cpu(s) 11.0 us, 6.8 sy, 82.0 id` | 只读采样 |
| owner (pid 305) | 48.9%～50.0%（单核百分比） | `top` 两帧 |
| owner 线程分解 | 315≈10.0%、316≈9.8%、317≈9.7%、319≈18.7%，合计 0.482 核 | `/proc/305/task/*/stat` 6 s 差 |
| 采集/编码速率 | `captured` 824643→824822，6.03 s 共 179 帧 = **29.68 fps**；`encoded` 与 `captured` 相等 | `status.json` 两次 |
| 录像服务 (pid 292) | 12.5%～15.5%，且 `--mode off` | `top` 两帧 |
| `serve_photos.py` (pid 289) | 0.0% | `top` |
| 1 MB 帧拷贝 | 0.575 ms/帧（30 fps 时约 1.7% 核） | 板端基准 |

`status.json` 同时显示 `preview_mode=continuous_vpu`、`width=960`、`height=540`、`fps_limit=30`。

## 颜色转换基准（OpenCV 4.6.0，板端）

| 线程数 | wall ms/帧 | CPU ms/帧 | 30 fps 下折算 |
|---|---:|---:|---:|
| 1 | 5.33 | 5.33 | 16.0% 核 |
| 2 | 3.14 | 5.93 | 17.8% 核 |
| 4（默认） | 2.70 | 8.69 | 26.1% 核 |

测试内容与 owner 当前路径一致：`COLOR_BGR5652BGR` + `COLOR_BGR2YUV_I420`，输入 960×540 `CV_8UC2`。数据为随机帧，不是真实画面；结论只用于量级比较。

## VPU 格式枚举

`/dev/video0` 的 Video Output Multiplanar（编码器输入）枚举包含：压缩格式、AFBC YUV、`YM12/NV12/NV21`、`YUYV/UYVY/Y210`、`BA24/RGB4/RA24/AB24/AR24/BGR4`（32 位 ARGB/BGRA 系列）。**没有 RGB565/RGB24/BGR24**。Video Capture（编码输出）同样只有压缩与 YUV 格式。

因此：当前“PL 输出 RGB565 → PS 转 NV12 → VPU”的链路里，CPU 转换无法靠改一个格式常量绕过。

## 分析

### 1. “VPU 太极限”目前没有数据支持

VPU 以 29.7 fps 稳定工作，但这是 `fps_limit=30` 的配置上限，不能证明 VPU 硬件在 30 fps 以上还有余量。能确认的是整机并不缺 CPU：4 核中约 82% 空闲。若要判断 VPU 上限，需要单独做 60 fps 或更高码率的受控试验，本轮未做。

### 2. owner 的 CPU 花在哪

按实测与代码路径拆分，部分为估算：

| 组成 | 估算 | 依据 |
|---|---|---|
| 颜色转换 | 0.16～0.26 核 | 基准 5.33～8.69 ms/帧 |
| 1 MB 原始帧拷贝 | 约 0.017 核 | 0.575 ms/帧 |
| NV12 二次拷贝（约 1.5 MB） | 约 0.027 核 | 按同带宽线性估算 |
| 每帧 `status.json` + `latest.frame` 写与 rename | 约 0.02 核 | `status()` 每帧调用；`/proc/305/io` 显示 `syscw≈1.70M`、`wchar≈11.6 GB`，约 2 次写/帧 |
| VPU 入队/出队与驱动 | 余量约 0.15 核 | 差值，未单独测 |

### 3. 录像服务在 off 模式仍耗 0.13～0.15 核

`npu_photo/recording_service.py` 的 `capture()` 循环固定 `stop.wait(.01)`，每 10 ms 调一次 `frames.read()` 读 `latest.frame`，与 `recorder.mode` 无关；off 模式仍以 100 次/秒读约 10 KB。这是可直接消除的空转。

### 4. PL 预览的净收益

- 960×540：PL 预览会去掉 owner 的 VPU 编码与转换路径（约 0.48 核），但 PS 侧要新增 UDP 重组与 HTTP/MJPEG 供流；10-24 高噪声 1080p 实测接收进程 0.32～0.40 核，普通画面按包量估算约 0.1 核。净收益约 0.1～0.35 核，且需要新位流并承担 PHY/DDR 风险。
- 1080p：VPU 路线的转换成本约 4 倍（≈1 核），不可行；只有 PL JPEG 能承担，但当前卡在 PHY 身份全零与候选 DDR 保护失败。

结论：“解放 CPU”不足以单独支撑 PL 预览的投入；PL 预览的价值主要在 1080p 画质和 PL 侧确定性，而这两点目前都未闭环。

## 可落地的软件优化（当时尚未实施；已于当日晚部署，见上方修正说明）

| # | 改动 | 预期收益 | 风险 |
|---|---|---|---|
| 1 | 录像服务 off 模式读取间隔 10 ms → 500 ms（`recording_service.py` 的 `capture()`） | 约 0.12 核 | 低；off 模式不产生录像，ring 预录仅 auto/manual 需要 |
| 2 | owner 的 OpenCV 线程数 4 → 2（`cv2.setNumThreads(2)`） | 约 0.08 核 | 低；wall 每帧 +0.44 ms，需复核 30 fps 是否保持 |
| 3 | `status.json` 由每帧写降为 1 Hz；`latest.frame` 保持每帧 | 约 0.02 核 | 低；网站按请求读状态，1 Hz 足够 |

三项合计预计整机 CPU 从约 20% 降到约 13%，owner 0.48→约 0.36 核、录像 0.13→约 0.01 核。均不涉及位流、BOOT、引脚或服务接口；部署只替换应用文件，可回退。

UYVY 直通 VPU 可再省约 0.16～0.26 核，但与 FAC1 的 RGB565 输入冲突（见 `wcis_face_customop` 的 `cmd_rgb565`），需要新模式或二次转换，不建议在 11-4 前实施。

## 验证边界

- 单次启动、单一时段；空闲无脸场景，`commands=273`，不代表识别、录像、多客户端并发时的负载。
- `top`/`/proc` 为短窗采样，CPU 百分比是单核口径；读数为近似值，4 核满载为 400%。
- 转换为合成随机帧基准，非真实图像；OpenCV 4.6.0，与 owner 实际调用路径一致但不等同整条链路。
- 未测 VPU 在 30 fps 以上的能力，不能由 29.7 fps 推断硬件余量。
- 接收端 CPU 引用 10-24 高噪声实测；普通画面 0.1 核为按包量估算，未实测。
- 本次为只读测量，没有落盘原始输出；命令已在上文列出，可复跑。若需长期对照，应在 `D:/yzd/tmp/<task>` 保存原始输出。

## 后续

- 等待用户确认是否实施上述三项软件改动：离线修改、学校服务器构建、部署前再确认。
- PAD 校准需要真人到场，采集协议另行准备。
- 1080p 预览暂不在 11-4 前实现；文档口径写“960×540 已稳定，1080p 受 PL 网络未闭环限制”。

## 关键来源

- `fpga_project/ps_app/src/wcis_camera_owner.cpp`：第 73、81 行状态发布；第 205 行帧拷贝；第 213、222～230 行转换、NV12 拷贝与 VPU 入队。
- `fpga_project/ps_app/src/wcis_owner_vpu.hpp`：VPU 使用 NV12，允许 960×540 与 1920×1080。
- `fpga_project/ps_app/vendor/include/pipeline/io/input/sdicamera.hpp`：`camera_fmt::YUV422` 时写 `0x78=1`、`0x7c=frame_w`。
- `fpga_project/npu_photo/recording_service.py`：`capture()` 的 10 ms 轮询；`detector()` 的 0.5 s 间隔。
- `fpga_project/docs/pl-jpeg-ethernet-validation-20261024.md`：接收进程 0.318/0.401 核的高噪声实测。
- 本次只读 SSH 命令输出（`top`、`/proc/stat`、`/proc/305/task/*/stat`、`v4l2-ctl`、板端 OpenCV 基准），未落盘。

日期按客户端 2026-10-29 凌晨；测量发生在 01:35～01:45。
