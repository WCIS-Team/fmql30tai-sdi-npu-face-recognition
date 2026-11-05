# 500 MHz 真人补验收（2026-10-23）

## 本轮结论

**真人持续检出未通过，暂不作为正式门锁镜像放行。** 500 MHz 候选已实际检测到真人，并完成特征提取/人员库比对；但约 6 秒的 18 次请求中仅 3 次检出人脸。用户明确说明测试者未录入，三次结果均为 unknown，符合这一已知标签；这不等于已验证授权人员识别，也不代表活体、防照片或防视频攻击通过。

负载和固定图片复算的工程检查通过，与真人持续检出验收分别记载。`acceptance-result.json` 是复算/负载驱动结果，其 passed 字段仅限该驱动；全面状态以 `acceptance-summary.json` 的 complete_acceptance_passed=false 为准。测试结束已恢复原镜像，服务 ready。

## 过程与观测

- 本轮开始原 boot ID：`807f9b44-818d-4045-9514-04085b52bd6b`，BOOT 为原已验收 f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297，和上一轮恢复状态一致。
- 初次“就位”样本 18 次全部无脸，预览是桌面/显示器；提示用户入镜后原镜像样本为 2/18 次有脸，后续人脸已离开画面。该组不能用作持续在镜头内的检出率基线。
- 复用冻结的 500 MHz BOOT 1ccf96fa0d3e422484797cbbfdb13b8156ee8b430aebb9d6e76da706423edff2，本轮 boot ID：`1127f1f5-f92e-4de5-b551-469aee444080`。没有重新综合、布线、模型编译或板端编译。
- 新启动重新通过 4 缓冲区 DDR 读写、8 用例/88 次 PL 像素回归及完整 YuNet/MobileFaceNet 回归；24 组原始输出哈希与冻结的 1 GHz 对照一致。之后才接入原服务，保留新一轮 600 秒自动回退。
- 用户再次确认可以采样，500 MHz 样本 18 次中 3 次有脸。检测分数分别约 0.743、0.640、0.772；三次 unknown。有脸请求的板内 HTTP 耗时中位数约 439.1 ms。这是少量不同现场帧的耗时，不能和上一轮固定公开图片直接比较。
- 人工查看真实推理所选帧 JPEG（从响应 image 原字节提取，SHA 与 result.photo_sha256 一致），可见照度偏低、倾斜和部分运动模糊。这些是可见干扰因素，尚未建立单变量实验，不能断言它们是全部漏检的唯一原因。

## 相同现场输入复算

从 500 MHz 实时样本中选择索引 1、8、17 的准确推理帧 JPEG，保存原字节和哈希。分别在 500 MHz 与恢复后的原镜像下经上传图片路径复算，同一组输入的检测原始张量哈希、人脸框、识别特征哈希和身份结果完全一致：

| 固定现场 JPEG | 原镜像人脸数 | 500 MHz 人脸数 |
|---|---:|---:|
| frame-1.jpg | 1 | 1 |
| frame-8.jpg | 0 | 0 |
| frame-17.jpg | 1 | 1 |

无脸样本在两版复算均未检出。这不支持“只有 500 MHz 才造成这张固定输入漏检”的解释；不能由三张图片证明所有场景均等价。JPEG 上传路径与原始 RGB565 现场路径也并非完全相同，复算是辅助定位证据，不替代现场准确率验收。

## 扩展负载与恢复

500 MHz 下持续 121.2 秒完成 177 次固定图片识别（单脸、双脸、无脸循环），每次原始输出和结果均匹配已保存的 1 GHz 对照。负载期间采集计数速率 29.33 帧/秒；这是采集速率，不是 NPU 推理帧率，也不是长期稳定性签核。

恢复后 boot ID：`14e1cdc4-db01-4ba9-8007-482fc3cf9d84`。全部 30 个启动文件与本轮开始相同，原 BOOT f6da...，人员库 6 个文件一致。服务单元、camera-control、deployment 恢复，试验回退定时器及网络辅助单元禁用，原服务与预览状态 ready。人员库没有登记、删除或改写，未执行开门授权。

## 频率核对与未完成项

读取本机 SDK `C:/Icraft/CLI/include/icraft-xrt/dev/zg330_device.h`：第 53 行 icore_clk_freq 默认 1000E6，第 230 行为 setIcoreClkFreq；当前头文件没有提供真实频率测量的直接证据。摘录、行号和源哈希见 frequency-api-review.json。资料 D:/xiangmuwendang/WCIS-FPAI/wiki/man/NPU调用链.md 也将 860 MHz 描述为显示值，并指出 ZG330 不支持其通用设频方式。默认值、计时换算参数和实际硬件测频必须分开。

已存在的 core-clock-topology.txt 可见网表中，该 BUFG 的直接负载是 ai_core_clk_locked_reg/C，不能据此断言它与硬核实际工作频率的完整对应关系。没有新增 FPGA 测频电路、改寄存器设频或猜测地址探测。本轮仍未测得真实 NPU 内核频率，500 MHz 仅指候选 PLL 输出配置。

下一项应先用固定摄像头角度、清楚的正面照明和静止正脸复测持续检出，再逐项加入转头与运动。未调整检测/身份阈值以迎合这组样本。ASR/LLM、温压边界/长时间稳定性、已登记人员准确识别、防照片/视频攻击仍未验收。

关键本地来源：D:/yzd/tmp/npu-500mhz-acceptance-20261023 下 initial.json、各组 samples.json、human-summary.json、frozen-manifest.json、replay-*.json、extended-load/load.json、boottrial/basic-trial-500mhz.json、boottrial/final-restoration.json、frequency-api-review.json、acceptance-summary.json；前一轮完整 A/B 记录为 D:/renlianshibie/fpga_project/docs/npu-clock-500mhz-board-comparison-20261023.md。记录日期按本轮北京时间 2026-10-23。
