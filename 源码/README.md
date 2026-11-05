# FMQL30TAI 视觉工程交付包

## 先看目录

| 目录 | 放什么 | 什么时候用 |
|---|---|---|
| [fpga_source](fpga_source/README.md) | FPGA 设计源码、BD、XCI、约束与厂商 IP 定义 | 查阅 FPGA 设计与恢复脚本 |
| [ps_source](ps_source/README.md) | PS 业务源码、网页源码、构建脚本、测试与开发参考 | 修改采集、识别、预览、录像程序 |
| [board_runtime](board_runtime/README.md) | 配套启动文件、已编译程序、模型、SDK 和安装脚本 | 安装到板卡运行 |
| [fpga_restore](fpga_restore/README.md) | 原上板版已布线 DCP | 恢复已验证版本的位流 |
| [logpack](logpack/README.md) | 验收证据、最终报告及历史记录 | 核对版本、过程和验证边界 |

`ps_source` 是可编辑源码，`board_runtime` 是配套运行副本；两处同名 Python/网页文件分别服务开发与安装。`fpga_restore` 保存实现结果，不是第二份 FPGA 源码。旧 `wcis-official/submission`、`board-run/submission` 和双层 `logpack/logpack` 已取消。

环境：Vivado 2018.3、配套 JFM_Kits 时序库、Procise 2025.1.1 temp、FMQL30TAI 完整版；板端为厂商 AArch64 Linux 和 iCraft/CustomOp 3.39.0。外部厂商资源见 [EXTERNAL.md](EXTERNAL.md)。

## 外设：SDI 摄像头

| 项目 | 本项目使用配置 |
|---|---|
| 摄像头 | 魔客仕（MOKOSE）SHD30，2.8–12 mm 变焦镜头 |
| 视频输入 | HD-SDI（SMPTE 292M），1920×1080 逐行、30 帧/秒（1080p30） |
| 接线 | 摄像头 `SDI OUT` 通过 75 Ω BNC 同轴视频线接 FMQL30TAI 完整版的 `XS1 / SDI0` 输入 |
| 供电 | 摄像头使用独立的 DC 12 V / 1 A 配套电源 |

断电接好同轴线后上电，将摄像头设为 **1080p30**。SHD30 还提供 1080p25 和 CVBS 输出，复现本项目请使用上表的 HD-SDI 设置。型号和供电规格见 [SHD30 厂家资料](https://www.mokose.cn/productinfo/117098.html?templateId=1133605)。1080p30 为项目实际使用并有板端采集记录的输入档位。

## 使用 DCP 恢复原上板版位流和 BOOT

这是本包唯一提供的 FPGA 复现流程。保留设计源码供查阅；未完成验证的纯源码构建流程已撤下。

1. 将完整提交包放到英文目录，保留上述结构。按《30TAI使用教程》第一章准备配套时序库。
2. 启动 Vivado，在未打开其他工程的窗口选择 Tools → Run Tcl Script，运行 `fpga_source/restore_implemented.tcl`。脚本读取 `fpga_restore/refclk-final.dcp`，在 `build-restored/` 生成位流、报告和 Procise 命令，不重新综合或布局布线。
3. 将外部提供的 `FSBL251210_ddr400_demo.out`、`bl31.elf`、`u-boot` 放进 `fpga_source/boot/`，保留其中的 `wcis.bif`。
4. 把 `build-restored/procise-command.txt` 中的两行命令复制到 Procise Tcl Console 执行。脚本选择 `JFMQL30TAI676H`，执行 `disable_icap`，在 `build-restored/` 生成 `BOOT.bin`。

这是基于已布线 DCP 的恢复，必须保留 `fpga_restore/refclk-final.dcp`。原路径恢复和 BOOT 打包曾实测与原上板版逐字节相同，BOOT SHA-256 为 `f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`。本次只修订操作说明，未运行 Vivado/Procise、生成位流或改写板卡。历史证明见 [版本核对记录](logpack/source-reconcile-20261104/README.md)。

## 安装和打开网站

按 [板端运行说明](board_runtime/README.md) 准备 SD 卡、安装服务并验收。使用另行生成的 BOOT 时，按其中 `--boot-bin` 步骤生成匹配配置。

电脑与板卡接入同一局域网，按板卡实际 IP 打开 `http://板卡IP:8091/`；`8092` 为实时预览，`8093` 为录像页面。此前使用的地址是 `192.168.1.113`，换板或换网络后须重新确认。首次安装、开机启动和没有画面的排查见 [网站访问指南](网站访问指南.md)。

主站底部为“直播 / 录像 / 数据库”。手机登记可用“手机系统拍照”；电脑摄像头登记运行根目录 `启动电脑摄像头登记.cmd` 后访问 `http://localhost:18091/#database`。操作细节见网站访问指南。

## 查看源码与检查打包

FPGA 设计资料与恢复脚本见 [fpga_source/README.md](fpga_source/README.md)，PS 开发资料见 [ps_source/README.md](ps_source/README.md)。FPGA 恢复按上面的 DCP 步骤执行。

全包实际文件及 SHA-256 见 `filelist.json`，纯路径清单见 `filelist.txt`。先运行 `python -B package.py --check` 检查完整性；需要压缩包时运行 `python -B package.py --out 包外路径.zip`。打包脚本拒绝混入缓存、源码区构建输出和标准 IP 自动生成副本。

当前网页已按 2026-11-04 确认版整理：运行首页只保留 `board_runtime/reference_release/app/site/`，录像只使用 `board_runtime/reference_release/recorder/`。源码入口见 [网页开发说明](ps_source/docs/website-current.md)。旧网页、闲置副本和迭代记录均已移到包外备份。

源码区已清理重复的发布历史文件；当前代码位于 ps_source 的功能目录，历史收据只在 logpack/05-release-receipts 保留一份。编译缓存和临时产物不随包交付。
