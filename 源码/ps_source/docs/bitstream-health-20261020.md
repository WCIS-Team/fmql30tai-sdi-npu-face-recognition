# 当前位流运行检查（2026-10-20）

## 结论

当前位流的 SDK/DDR 与 FAC1 人脸预处理路径通过本轮有限板测，没有整片功能失效的证据。但真实 SDI 未锁定，且实现报告并非全部时序通过，不能判定整片“完全正常”。未定位 SDI 失锁根因。

## 本轮实测

- 当前 boot_id 为 `d4c98f4d-da2b-4bb8-bd98-66a6dcfdde6c`，所有本轮板测均绑定这个启动，未冒用先前验收 boot_id。
- 重新只读挂载 SD 核对 BOOT.bin SHA256 为 `f48397d08b1ccb1c950adafcebe5e36678154e73fa1d19792150aa5ddccd8ad1`，与已验收版本一致；DTB/uEnv 哈希也相同。没有 `/download.bit` 自动覆盖，存在 `/root/live.disabled`。这是启动介质和运行功能核实，没有做 FPGA 配置存储的完整读回比对。
- 在 SDK 分配范围内进行 4 组 4,147,200 字节写入/两次读回，错误数均为 0。不同偏移和分块方式复用有限缓冲区，不是完整 PL DDR 2GB 扫测，也不能称作覆盖了 4 倍的独立容量。
- 复用已验收原始向量，对 8 组 FAC1 输入各执行 11 次，88 次输出全部与独立期望字节一致，原始输入完整读回一致。未重新运行模型输出或 JPEG 编码回归，不能把本轮结果称为 NPU/JPEG 的新验收。
- SDI2 连续 3 次一致快照均成功：seen/fresh/ref_stable/gt_reset_released 为真，RX 时钟计数增长；rx_flags=122，lock=0，已锁定真实帧/行/有效像素计数均为 0，几何为 0。没有发送摄像头捕获请求，也没有生成图片。
- 维护期间停止照片服务以隔离设备，完成后恢复 ready。服务文件、应用文件、运行设备树和人员库哈希与本轮开始相同，硬件锁可取得，无当前启动隔离标记。

## 实现报告核对

复查 `D:/yzd/tmp/face-cache-resume-20261020/timing-gate.json` 中的报告哈希，timing/route-status/bus-skew/DRC 全部与已部署候选记录一致；没有重新运行 FPGA 实现或生成位流。

- route-status 报告 routing errors=0。
- 建立时间最差余量 WNS=+0.005ns，保持时间 WHS=+0.004ns；余量很小。
- 脉宽检查分类中有两个最小周期违例：NPU `AI_CORE_CLK` 的 BUFG 为 -0.409ns、PLL 输出为 -0.071ns。报告明示 `Timing constraints are not met`。既有记录将其归为厂商 NPU 继承项，不能因此视为完成生产时序签核；FMQL 与 Xilinx 代理器件模型差异尚需按厂商依据核实。
- DRC 包含 SDI 组合逻辑驱动时钟和潜在 hold 风险（PDRC-153、PLHOLDVIO-2），以及 GT 通用参考时钟等告警。存在告警不等于已证明它导致本次失锁；不得靠降级规则或清除告警声称修复。

## 新发现：SDI 诊断频率声明不一致

`frame_trans` 的诊断实例未覆盖 `wcis_sdi_monitor` 默认 CFG_HZ=50,000,000、SAMPLE_CYCLES=500,000、STALE_CYCLES=5,000,000，板端 0x130 也返回 50MHz。
但源码时钟连接为 `clk_wiz_0.clk_out1 -> gp_axi_aclk -> ps_clk_out -> gp_clk -> frame_trans.S_AXI_ACLK -> monitor.cfg_clk`，本次部署候选的实现报告把 `clk_out1_clk_wiz_0` 约束为 100MHz。
因此工程时钟和诊断声明不一致：按该实现时钟，快照间隔为 5ms、过期窗为 50ms，而非旧文档的 10ms/100ms。寄存器频率字段是常量，不是独立频率测量。
这个问题影响诊断的时间单位/过期窗口，不能直接解释上游接收器 lock=0；原始锁定位和零帧结果仍然成立。本轮仅检测和记录，没有因此修改位流或混用新旧寄存器协议。

## 后续范围

若继续定位 SDI，应在硬件设置不变时用已知原案例做真实画面对照，并针对接收时钟、复位、GT 及最终实现检查。VTC 图只能验证板内测试源，不能代替摄像头画面。PL 网口逻辑未实现，不能把它没有视频当作现有位流传输模块损坏。

## 来源和输出

- 本轮输出目录 `D:/yzd/tmp/bitstream-health-20261020`：before/after、boot-inventory、ddr、fac1-verification、inspection、results、summary 各 JSON。
- 复用程序 `fpga_project/scripts/check_jpeg_ddr.py`、上一轮 `check_cache_board.py` 与 `ps_app/src/wcis_camera_single_frame.cpp`；本轮没有编译新程序，未调用学校服务器构建。
- 实现报告 `D:/yzd/tmp/face-cache-resume-20261020/{timing.rpt,drc.rpt,route-status.rpt,timing-gate.json}`。
- 时钟源码 `D:/yzd/tmp/pl-jpeg-board-20261016/case/rtl/{ps_ai_wrapper.sv,ps_ai_peripheral.sv,utils/demo_clkrst_wrapper.v,display/frame_trans.sv,wcis/wcis_sdi_monitor.v}`。
- 后台读取补充资料 `D:/xiangmuwendang/WCIS-FPAI/wiki/todo/PS-PL_AXI_HP口与复位语义.md`；它是项目对厂商说明的整理，本轮未独立核验原始厂商 PDF。
