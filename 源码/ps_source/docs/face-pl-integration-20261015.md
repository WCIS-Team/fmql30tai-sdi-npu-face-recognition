# 人脸 ModelBackend：官方 CustomOp 集成

> 后续照片服务的上传、登记入口已接入本PL后端，实际HTTP验证和当前页面状态
> 见[服务接入记录](face-pl-service-20261015.md)。下面保留独立硬件原型的验收证据。

这是对同日[独立算子记录](face-pl-modelbackend-20261015.md)的后续集成，
以本文件的当前验收状态为准。目标是文件输入的模型可用性原型。

## 实际连接

保留官方 SDI、DDR、AI_Mate、NPU、时钟、引脚及原有加法器。
`case/rtl/ai7030_edif_top.v` 的 `U_adder_top` 改为
`wcis_face_customop`，沿用官方 UserCustomOp_0 的 **512-bit PL-DDR**
接口，不把它误当成 PS HP DDR。

PS 上传 BGRX 原图到 SDK 分配的 PL-DDR，提交不可变描述符；PL 执行
逆仿射、双线性采样、边界和补边，再将 BGRX 结果写回 PL-DDR。
PS 读回结果，沿用现有模型的颜色、归一化、FP32 NHWC 和 PSIN 输入契约。
没有修改模型图，也没有声称已经实现 PLIN 直接喂入或摄像头实时链路。

GP 控制域沿用 100 MHz，原生 DDR 侧沿用 200 MHz。三个单项 mailbox
传递读请求、读响应和写请求；保持 payload 直到目的侧消费后 ACK 返回。
原生 DDR 读写仲裁在反压时锁定 owner，避免新请求改动被暂停的事务。
完成状态等待最终输出写请求被 DDR 接口接受；板端还检查全部输出像素的
X 字节哨兵，避免把未完成的写回当成图像。

## 寄存器及所有权

新寄存器页为 `0x400C2000`，原加法器页保持不变。
官方 `case/rtl/gp/gp0_manager.sv` 以 ASP=18 将 `0x400C0000` 起的
256 KiB 路由到 user_op；新页仍在这个窗口内。

| 相对偏移 | 内容 |
|---|---|
| 0x00 | 读 ID `0x46414331`；写 bit0 启动 |
| 0x04 | busy bit0、completed bit1、rejected bit3、error bits7:4 |
| 0x08 / 0x0C | 完成 frame_id / 像素数 |
| 0x10 | 原帧 frame_id |
| 0x14 / 0x18 / 0x1C | 输入基址 / pitch / 输出基址 |
| 0x20 / 0x24 / 0x28 | 原图 / 内容 / 画布高宽，各高16位、宽16位 |
| 0x2C / 0x30 | replicate、RGB565 标志 / RGB border |
| 0x34..0x48 | 输出到原图的六个有符号 Q16.16 系数 |

启动后描述符锁定；忙时修改或重复启动被拒绝。输入和输出分配不重叠，
输出按64字节对齐；原生端口按官方27位地址窗口限制到128 MiB以内。
范围校验按乘法、端点相加、比较三拍执行，随后才启动核心，避免在100 MHz
下串接长组合路径；验证期间同样保持 busy 和描述符锁定。
`wcis_face_pl` 要求调用者持有现有 `npu.lock`，验证所有描述符读回、
完成 frame_id、像素数和哨兵。硬件超时隔离当前 boot，禁止自动重试。

PS 保留五点矩阵求解与必要的模型调用次序。`pl_preprocess.py` 确保
检测缩放与人脸对齐绑定同一原图 SHA-256 和 frame_id。
不增加 OrchestrationLayer、WebFrontend 或身份库管理。

## 已完成的证据

- 独立算子的21组像素、反压、边界和 AXI 异常测试通过。
- 完整 CustomOp 的6组仿真通过：异步时钟、DDR 反压、原加法器实算、
  非法描述符、忙时修改、同地址换帧、RGB565、真实人脸和1080p缩放。
- 原照片服务的 CPU 五点对齐重构，对11张公开照片逐像素完全相同。
- C++ SDK 程序在学校服务器隔离目录交叉编译，并上传板端候选目录；
  依赖、帮助和6组无硬件描述符检查通过。这些不等于 PL 已运行。
- 新模块已经加入整板工程，首次完整布局布线发现范围校验路径 WNS -2.343 ns；
  将乘法、加法、比较拆成多拍，并按实际100 MHz更新仿真后，第二轮最终报告
  setup WNS +0.027 ns、hold WHS +0.007 ns，二者违规端点均为0，路由错误为0。
- 三个 mailbox 真实数据路径的 REQUIREMENT / SLACK 分别为：读请求8 / +6.455 ns、
  写请求8 / +6.561 ns、读响应20 / +18.375 ns。新 payload max-delay 未被覆盖。
- 新位流生成并经厂家 DISABLE_ICAP/VCCM 修补，Procise 打包后逐字核实 PL 载荷，
  三个 PS 分区与现役固件一致；2026-10-15 已写入 BOOT 并正常重启。
- 新启动中先完成6像素逐字节对照，再通过11张公开照片及无脸、多脸共13项检查。
  11张CPU参考特征余弦为0.9971137～0.9998088；YuNet绑定112个NPU算子，
  MobileFaceNet绑定211个NPU算子，无CPU推理回退。
- 24项PL任务中，11对检测/对齐保持同一原图frame_id。原照片服务已恢复enabled/active，
  `http://192.168.1.113:8091/` 返回HTTP 200。本轮没有操作用户身份库。

首次布线还发现 Vivado 2018.3 XDC 不支持 `foreach`，跳过了 mailbox
约束；生成器已改成逐条展开。不能将首次 `bus_skew.rpt` 当成新 mailbox
通过证据。第二轮明确检查 payload 与 capture 寄存器存在，并在布线后
逐条读取真实 timed path 的 REQUIREMENT 和 SLACK，防止 false path 隐藏数据路径。

证据统一在 `D:/yzd/tmp/face-pl-integration-20261015`。学校构建仅使用
`D:/yzd/tmp/wcis-face-pl-20261015-*`，共享 SDK 只读。板端候选程序在
`/root/wcis-face/candidates/face-pl-20261015`。

## 当前验收边界

本次按用户指定的文件输入 ModelBackend 原型进行受控上板验证，不能称为
全设计时序、CDC或生产发布签收。官方未改动的1 GHz NPU BUFG/PLL仍有
2项最小周期告警（WPWS -0.409 ns），尚无厂家豁免依据，未隐藏或改变该时钟。
新CDC的970位保持数据、6条同步握手均已核查；另8条CDC-10只在复合异步复位
进入两级本地复位同步器的首级PRE上，按异步置位、同步释放结构逐项审查。
旧案例其余CDC和物理兼容性告警不作为本轮整体签收对象。

三份安装工具库文件在构建后仍与构建前SHA一致。新BOOT SHA-256为
`0e44eea591fb9dcfba724ddde17b590d5ce0005904d87f6edbcae8c6e20ae0d2`，
修补位流SHA为`e0dddc749adda5ae22c577c32b723822e45e6e324ba69ef6a177a70ff19b0e82`。
当前启动编号`10e03733-bac1-4faa-ab79-792fabaf9db7`。
SD回滚副本`FPL1015.BAK`及本机`BOOT.before-face-pl.bin`均为原现役固件
`b87024cef9ee06936ac7123c2c976552beb0938d255abf27036dc9bbafeddc94`。
没有重分区、改变引脚、电平或GT跳线。摄像头启动仍禁用。

逐点DDR原型偏重正确性。本轮640画布的启动至读回/落盘为48.7～296.0 ms
（13次中位241.4 ms），112对齐为8.4～11.0 ms（11次中位10.6 ms）。
这些计时含PS读回和输出文件写入，不含先前原图上传、SDK初始化及模型解析，
不是纯PL核时间或整链路帧率；不能宣称已解决现有3至4秒延迟。
摄像头连续流、高效行缓存、PL 网口压缩传输不属于这次已完成的实现。

独立板端复核入口为`npu_photo/check_pl_pipeline.py`。持有项目`npu.lock`，
使用新的`--out`目录，检测缩放在打开NPU会话前执行，对齐在检测工作进程退出后执行。
硬件失败会按当前boot隔离，禁止未审查的自动重试。网页服务现已调用同一PL适配器；
`check_pl_pipeline.py`本身仍是独立回归入口。

主要证据（均在上述本机任务目录）：`physical-review.json`、
`boot-candidate/manifest.json`、`boot-deployment.json`、`tiny-job/board-verification.json`、
`board-pipeline-verification.json`、`final-board-state.json`。

案例补丁与原始 SHA 记录见 `source_manifest.json`、`case_changes.patch`。
Downloads 原案例和已安装工具库未修改。
