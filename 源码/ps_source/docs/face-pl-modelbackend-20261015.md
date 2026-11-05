# 人脸 ModelBackend：原帧仿射采样

> 本文记录独立算子阶段。后续已接入官方 CustomOp 并完成6组集成仿真，
> 当前状态、寄存器和板端验收边界见[后续集成记录](face-pl-integration-20261015.md)。

## 本轮实现与边界

新增可综合的 `rtl/wcis_face_preprocess.v`，将一条描述符执行成一帧 RGB888：

```
已完成且被保留的原帧 DDR 缓存
    → 64-bit AXI 读适配器（只读、单 outstanding、8-byte cache）
    → 逆仿射坐标 / 四邻点双线性插值 / 边界处理
    → 右下补边 / RGB888 valid-ready / SOF-EOL-EOF
```

它是独立 ModelBackend 算子，尚未连接案例顶层、AI_Mate 或当前板端程序。
不是一份已可启动的摄像头人脸识别固件。本轮没有生成 bit/BOOT、写板、
改引脚、改 SDK、改 NPU 模型或改变现役照片服务。

支持两类几何描述：

- YuNet：全图等比缩放后左上放置、右下黑色补边，640×640；色彩和张量转换另行衔接。
- MobileFaceNet：PS 根据原帧五点求相似变换，PL 从同一原帧逆向采样，得到 112×112 对齐人脸。

CPU/PS 保留矩阵求解、模型调用顺序、结果解释；PL 只执行像素和握手状态机。
没有增加工作/待机策略、任务队列、身份管理、WebFrontend 或 OrchestrationLayer。

## 参考案例和采用方式

| 来源 | 采用内容 | 未作出的假设 |
|---|---|---|
| 厂商 `case/rtl/display/aq_axi_master.v`、`frame_fifo_read.v` | DDR 边界为 32-bit byte address、64-bit AXI beat；后续复用原 DDR/HP 互连 | 没有把原顺序显示读控制器当成随机 ROI 读控制器 |
| 厂商 SDI、色彩转换、FIFO、AI_Mate 通路 | 保持原始工程作为实时链路集成基础；本轮未修改 case | 没有重写 SDI、DDR 控制器或引脚配置 |
| 厂商 `cmos_resize_24bit.v` 和既有逐像素仿真 | 核实原模块为整数抽样，1080p→640×352 的采样为 x=2+3i、y=14+3j | 没有宣称它等同 OpenCV 全图 resize |
| [InsightFace face_align.py，固定提交](https://github.com/deepinsight/insightface/blob/81929474ec02e54e3655f6841bced800009c592d/python-package/insightface/utils/face_align.py) | 112×112 五点模板、SimilarityTransform、原帧 warpAffine 和黑色边界；执行实际上游函数作对照 | 没有自己设计一套人脸对齐规则，也没有把检测框裁切替代五点对齐 |
| [OpenCV 4.10 imgwarp.cpp](https://github.com/opencv/opencv/blob/4.10.0/modules/imgproc/src/imgwarp.cpp) | 逆映射、1/32 像素插值网格、constant/replicate border；用实际 cv2.remap 产生 golden | 定点近似不等于任意尺寸下与 cv2.resize/warpAffine 逐位相等 |
| [Open Model Zoo face recognition demo](https://github.com/openvinotoolkit/open_model_zoo/tree/master/demos/face_recognition_demo/python) | 检测→关键点→同帧对齐→特征的成熟流程作为接口分工依据 | 没有移植其 OpenVINO 运行时，也没有开始写完整调度器 |

上游源码快照、来源 URL 和 SHA-256 在
`D:/yzd/tmp/face-pl-20261015/upstream`。
本轮只是读取并记录厂商文件哈希，没有修改 case，因此没有新增 case 补丁。

## 描述符及数据接口

所有端口在同一个 `clk` 域，`reset` 为同步复位。只有
`cmd_valid && cmd_ready` 的时钟沿接受一条命令；执行中忽略未被握手的命令，
所有参数锁存。PS 不能直接用异步多位 GPIO 驱动这些端口；后续需要原子寄存器
提交/CDC 适配，此处不假装已有该控制器。

| 字段 | 约定 |
|---|---|
| `cmd_frame_id` | 原帧身份；执行期间和完成时通过 `frame_id` 保持 |
| `cmd_base_addr`, `cmd_pitch_bytes` | 32-bit 字节地址、按行 pitch；两者必须 8-byte 对齐；pitch 至少容纳完整像素行，包含尾部对齐空间 |
| `cmd_src_w/h` | 1..8192；整个 `pitch*height` 分配不得越过 32-bit 地址空间 |
| 默认像素存储 | little-endian B,G,R,X，每像素 4 bytes，完整保留 8-bit RGB；并非声称现役 RGB565 抓图已经变成该格式 |
| `cmd_rgb565=1` | 可读取官方 RGB565 预览缓存并位复制展开；其精度损失必须另测，不能当作现有模型 RGB888 基线 |
| content/canvas | 内容位于左上；各维 >0，content≤canvas，canvas≤640×640；超出 content 的像素填 border |
| `cmd_m00..m12` | 输出坐标→原帧坐标的六个 **有符号 Q16.16** 系数；不接收正向矩阵 |
| `cmd_replicate` | resize 的边缘复制；0 为常量边界，适用于对齐人脸；逐邻点判断越界 |
| `cmd_border` | 24'hRRGGBB；当前两种人脸描述均填 0，未沿用旧 padding 默认 114 |
| `m_rgb` | 24'hRRGGBB；标记与像素共同握手，暂停时保持；不能直接把它当作 float32 NPU 输入 |

坐标用 48-bit 累加器，先舍入到 1/32 像素，半格取向正无穷，再由整数部分和
5-bit 小数选点/加权。插值只在最终像素处加半并取整；零权重邻点不访问 DDR。

例如 1920×1080→640×360 内容再补为640×640：逆矩阵为
`[[3,0,1],[0,3,1]]`。有效采样位置是 `(1+3x,1+3y)`，不是旧案例的 `(2+3x,...)`。
缩放回原图时保留 `sx=content_w/src_w`、`sy=content_h/src_h`，分别还原坐标；
取整后的两轴比例不能一律用理论 ratio 代替。

`done` 为一个时钟的完成脉冲，`error` 保持到下条命令/复位：

- 0：最后一个像素已被消费。
- 1：描述符无效，未发起 DDR 读取。
- 2：AXI 返回错误或本应单 beat 的响应缺少 RLAST；整帧结果失效。
- 3：采样核心非法状态恢复。

错误可能发生在部分像素已经输出后，消费者必须将该 frame_id 的**整帧丢弃**，
不得提交部分 NPU 张量。AXI 缺少首个 RLAST 时先排空到 RLAST，再允许下一条命令。
若总线永久不回应，模块保持 busy；外部系统需有故障恢复，不能靠本模块单方面
放弃 outstanding 读。reset 必须与 AXI 互连协调，不能只复位客户端而保留旧读响应。

原帧从提交到 done/错误排空期间必须不可覆写；本算子不负责摄像头 DDR 缓冲区
所有权。PS cache flush/invalidate、DDR 区域分配和跨帧绑定也是集成前的必要条件。

## 验证结果

命令与依赖见 `../model_backend/README.md`。实际日志和机器可读结果位于：

- `D:/yzd/tmp/face-pl-20261015/verification/verification.json`
- `D:/yzd/tmp/face-pl-20261015/verification/*/simulation.log`
- `D:/yzd/tmp/face-pl-20261015/synthesis/{utilization,timing,drc}.rpt`

21 组 RTL 自检覆盖：全帧像素、奇数宽度/pitch、旋转、常量/复制边界、补边、
RGB565、1×1、宽有符号坐标、非法尺寸/pitch/地址、AXI RRESP、异常多 beat 排空、
已输出部分帧后的错误、共享复位恢复、同地址换帧的缓存失效，以及四张实际照片
的112×112对齐、1080p检测画布和非整数纵向图片缩放。内存延迟和输入/输出握手
采用确定种子的伪随机暂停；运行中故意改变 live 参数来验证锁存。

golden 是 OpenCV 4.10 在**相同定点坐标网格**上的真实 remap 输出，RTL 要逐通道
完全相同。另对不量化的成熟函数记录误差：

| 与成熟函数输出比较 | 本组测试的通道最大差 / 平均绝对差（0..255） |
|---|---|
| 1080p→640×360＋黑色补边 vs cv2.resize | 0 / 0 |
| 非整数纵向图缩放 vs cv2.resize | 3 / 0.06334 |
| 四张人脸 vs InsightFace norm_crop | 最大 1..3；各图平均 0.00287..0.00811 |

这只证明本组像素误差范围，不证明特征余弦、身份阈值、其他图片精度或板端时延。
还读取了此前保存的四张板端对齐图进行比较，最大通道差仍为1..3；记录见
`verification/saved-board-crop-comparison.json`。这是旧板端图像对照，不是本轮上板。
OpenCV 5.0 的部分半整数舍入行为不同，golden 固定为4.10而不混用；skimage
0.26 的 estimate 弃用提示保留在日志。

Vivado 2018.3 独立综合：代理器件 xc7z030ffg676-2，1502 LUT、1075 FF、10 DSP、
0 BRAM；100 MHz 下综合后内部路径 WNS +4.612 ns、WHS +0.197 ns。
地址计算已拆分为锁存坐标、行乘积、加地址、校验阶段，修复初版单周期地址路径
的 setup 违规。日志仍有 DSP 吸收/删除寄存器、OOC 时钟源未指定等警告；DRC 有
DSP pipeline 和独立 Zynq 模块缺 PS7 的提示，不表述为无警告。
该检查没有完整输入输出时序约束，也没有整板布局布线，不能作为板卡时序签收。

## 性能与后续集成限制

此版按点读 DDR、一次只处理一条读事务，优先验证模型像素约定和原帧 ROI；
**不是高吞吐全图缩放的最终实现**。当前随机内存延迟仿真中，1080p 检测画布
需要5,289,502个周期；即使假定100 MHz，也约52.9 ms，不能宣称优于已测的
CPU前处理，更不能承诺20次/秒完整识别。真实 DDR 争用和NPU时延尚未计入。

实时检测应继续复用官方流式 SDI/缩放/FIFO 基础，按模型约定修正采样，再衔接
黑色补边和 ImageMake。随机原帧采样主要服务于检测后的同帧人脸 ROI；是否值得
代替PS五点对齐，需要板端测量，必要时再增加行/块缓存和批量读。

集成仍需完成：RGB888原帧缓存和所有权接口、描述符控制/CDC、DDR仲裁、输出
帧缓存/AI_Mate握手、检测BGR/识别RGB与归一化/张量打包、对应PLIN模型图适配、
特征及识别回归、整板时序和上板验证。模型图转换/编译继续默认使用学校服务器，
所有临时文件使用独立的 `D:/yzd/tmp/<task>`。本轮未做这些模型编译操作。
