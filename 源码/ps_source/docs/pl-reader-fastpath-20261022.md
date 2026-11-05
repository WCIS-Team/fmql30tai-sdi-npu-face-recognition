# PL预处理控制周期优化（2026-10-22）

本轮完成像素读取缓存命中及仿射采样请求的RTL优化，保持原算法、像素精度、帧归属与错误检查。960×540 RGB565到640×640检测输入的同条件仿真作业时间由83.815170ms降至64.229730ms，减少23.3674%；112×112真实人脸对齐用例减少16.9705%。这是RTL仿真结果，尚未生成整板位流、BOOT或部署上板，不能当作正式网页或摄像头识别的实测提速。

日期依据本轮客户端日期2026-10-22。同步读取`D:/xiangmuwendang/WCIS-FPAI/wiki/PL/plvid.md`；其中intro的SFace描述与模型列表及当前应用的YuNet、MobileFaceNet存在差异，本轮按实际源码和现有模型接口处理。上一轮PL/NPU争用结果见`pl-npu-resource-20261022.md`，不将旧板测与本轮仿真混为同一测量。

## 实现过程

1. `rtl/wcis_pixel_read_axi.v`：保留原有单个64位缓存字、一次仅一个在途读请求。在成功检查的物理缓存字上附加base、pitch、格式、行号和字内像素组标签；base/pitch按8字节对齐且全部标签一致时，直接解包缓存像素，省去重复的行乘法、地址相加和地址检查状态。其他布局仍走原有分级检查路径。未增加缓存数据容量，也没有新增预取或突发访问。
2. `rtl/wcis_affine_sampler.v`：在NEIGHBOR已经确定某个插值邻点需要访问内存时，直接发出请求。读端未就绪则转REQUEST，保持同样的VALID与坐标；就绪时直接等待响应，减少一个控制周期。零权重点、常量/复制边界、Q16.16坐标、Q5插值及输出舍入不变。
3. 继续保留帧间缓存清除、输入描述符锁存、32位地址溢出/对齐检查、错误响应处理、异常多拍排空与背压保持。缓存快速路径只使用已经验证有效的同一物理字；错误响应不能建立有效缓存。源帧仍须在整个作业期间保持不变。

该优化减少控制空拍，不减少DDR事务，也没有修改模型算子、识别阈值或防伪判定。PAD预处理共用这两个模块，因此一并回归；像素回归通过不代表防照片攻击能力获得新的验收。

## 同条件仿真对照

新增`scripts/verify_face_fastpath.py`，使用冻结的旧reader/sampler、仅reader优化、两项合用三组源码，运行相同原厂FAC1/JPG1共享端口封装、CDC、DDR停顿与黄金输出。原厂case只读使用。native/HP时钟200MHz，预处理/GP时钟100MHz；表中作业时间从测试提交START到检查完成，包含接口、轮询及输出核对，既不是电脑运行仿真的墙钟时间，也不是纯核计算时间。

| 用例 | 原版ms | 仅reader优化ms | 两项合用ms | 作业时间减少 | native读/写次数，三组相同 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 960×540 RGB565检测输入 | 83.815170 | 73.440420 | 64.229730 | 23.3674% | 36000 / 25600 |
| 960×540 BGRX检测输入 | 90.316680 | 83.408010 | 74.184270 | 17.8620% | 72000 / 25600 |
| 真实人脸112×112对齐 | 4.998390 | 4.635600 | 4.150140 | 16.9705% | 7079 / 784 |
| 1920×1080检测输入 | 43.182690 | 43.182690 | 40.883280 | 5.3248% | 43200 / 25600 |
| 小尺寸旋转和补边 | 0.057660 | 0.055050 | 0.049830 | 13.5796% | 50 / 18 |

1080p整数抽样用例的仅reader优化没有收益：其大量有效采样点不能复用同一64位字，零权重点原先已经跳过。这说明收益取决于源格式、缩放比例与坐标轨迹，不能统一外推23.4%。之前板测FAC1等待DONE约93ms与这里的64.23ms来自不同环境和计时边界，不能据此宣称板端已经降至64ms。

验证结果：

- `sim/tb_pixel_reader_fast.sv`：105次请求检查通过，覆盖两格式字内像素、标签变化、非8字节对齐的合法独立读端布局、换帧清缓存、错误后重读、多拍排空、溢出、最高地址字、共享复位和背压稳定。既有读端仍只有一个在途事务。
- 通用预处理23组通过，包括4张真实人脸、1080p/竖图、两个新增960×540摄像头格式、边界和故障注入；黄金值沿用固定OpenCV4.10规则。黄金输入及源码前后SHA核对通过。
- PAD预处理20组通过，包括ROI边界、单像素、换帧、错误注入和已有MiniFASNet图像黄金向量。未改变PAD模型与阈值。
- 实际原厂adder/FAC1共享封装常规6组通过，409600像素完整输出一致。
- 候选写回确认桥开启并注入接受后100个HP周期才可见的DDR模型：1080p大帧、真实人脸、同地址换帧3组通过。确认桥仍为默认关闭的既有候选；本轮没有改变其开关或部署状态。

## 独立综合与布局布线

Vivado2018.3，兼容代理器件`xc7z030ffg676-2`，顶层`wcis_face_preprocess`，100MHz独立OOC。使用项目只读工具保护，未修改安装目录、时序数据库、case、引脚或时钟配置。

| 项目 | 原版 | 两项合用 |
| --- | ---: | ---: |
| LUT | 1502 | 1585 |
| 寄存器 | 1075 | 1187 |
| BRAM tile | 0 | 0 |
| DSP | 10 | 10 |
| setup WNS | +3.418ns | +3.272ns |
| hold WHS | +0.105ns | +0.089ns |

优化后3225个需布线网络全部完成，布线错误0。增加83 LUT、112寄存器，换取上述控制周期减少；没有新增BRAM或DSP。前后DRC均有相同的21项Warning：DSP输入/输出流水建议20项、独立OOC缺PS7实例1项，无Error。工具同时提示HD.CLK_SRC未指定，且OOC端口没有整板I/O约束，因此这里只证明模块内部在该OOC约束下满足时序，不能代替整板时钟树、跨模块时序和上板稳定性。

## 证据、复跑和剩余事项

所有任务产物位于`D:/yzd/tmp/pl-reader-fastpath-20261022`：

- `reader-before.v`、`sampler-before.v`：优化前冻结源码。
- `verification/verification.json`：三版本15次作业、23组预处理、20组PAD、单元结果和校验值；`passed=true`、`board_verified=false`、`bitstream_generated=false`。
- `native-regression/verification.json`：常规6组实际封装验证。
- `posted-compatibility/verification.json`：开启写回确认及100周期延迟的3组兼容性验证。
- `ooc/compare.tcl`及`ooc/before/`、`ooc/after/`：独立综合、时序、资源、DRC、route_status与routed DCP。baseline/after比较均在同一脚本和约束下执行。

复跑需使用新私有目录，并在现有Python环境提供固定OpenCV4.10、NumPy及ModelSim；驱动复用`D:/yzd/tmp/face-pl-20261015/verification`与`D:/yzd/tmp/minifas-pad-20261018/pl-verification`黄金向量，迁移电脑时需显式保留这些依赖。

```text
python fpga_project/scripts/verify_face_fastpath.py --baseline-reader D:/yzd/tmp/pl-reader-fastpath-20261022/reader-before.v --baseline-sampler D:/yzd/tmp/pl-reader-fastpath-20261022/sampler-before.v --out D:/yzd/tmp/<新任务>/verification
python fpga_project/scripts/verify_face_customop.py --recording --verified-writes --simulator modelsim --cases detector_1080p face_obama cache_new_frame --posted-write-cycles 100 --poll-gap 256 --timeout 120 --out D:/yzd/tmp/<新任务>/posted
```

当前完成到RTL、仿真、模块独立布局布线。下一阶段应核对现役整板工程，将这两个已验证模块接入整板候选，重新跑完整时序与位流打包；部署后再对同一输入做像素/帧归属、DDR可见性、识别结果和持续相机负载验收。此前双行缓存候选曾出现DDR预检失败，不能省略新位流的DDR预检和回退准备。本轮没有生成/部署新整板位流，没有重启板卡或更改正式服务。
