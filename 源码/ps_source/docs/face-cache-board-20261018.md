# 双行缓存整板构建、DDR预检失败与回退（2026-10-18）

2026-10-20后续：[保留DDR实现的双行缓存部署实测](face-cache-resume-20261020.md)已通过两次正常重启回归并最终接受。该新候选的成功不改变本页原整片候选失败事实，其根因仍未确定。

后续工作见[10月18～19日静态实现保留试验](face-cache-preservation-20261019.md)。本页保留原整片试验结果；
新一轮采用不同替换范围，不能据其离线结果改写本页DDR失败事实。

**结果：新位流实际试启动成功，但DDR写读预检失败，未通过板上验收，已恢复原位流。没有新缓存的板上性能结果。**
工作日期以本次构建、部署和板测日志为依据，均为2026-10-18，Asia/Shanghai。

## 改动与来源

本轮仅把此前已仿真的FAC1双64字节行缓存放入整板实现。继续复用原FAC1接口、单笔在途读、mailbox及JPEG包装层。
源码工作区中的公平仲裁改动没有合入本轮候选；PAD裁图也未接入。
候选工程复制自已经过板测的`D:/yzd/tmp/pl-jpeg-board-20261016/case`，保留其旧版仲裁器。

- 原`wcis_face_customop.v` SHA256：`fe5799617f041805192ba661d19e6bdf2e531987d896eeb88ad964d5823e3a44`。
- 缓存候选SHA256：`d9cd41923dffaab3e3f48e4a38f02449b90079f45b34e56719acb501a35f54bf`。
- 独立任务：`D:/yzd/tmp/face-cache-board-20261018`。`cache-only.patch`与`source-manifest.json`绑定来源、改动及文件校验值。
- 关键本地来源：`rtl/wcis_face_customop.v`、`scripts/verify_face_line_cache.py`、
  `scripts/preserve_jpeg_shell.tcl`、`scripts/release_jpeg_conflicts.tcl`、
  `scripts/audit_jpeg_board.tcl`、`scripts/check_jpeg_ddr.py`、`npu_photo/src/jpeg_runner.cpp`。

本轮复核学校连接成功，检查的Vivado常用安装位置不存在、安装根目录未发现相关工具；
使用本机已安装的Vivado 2018.3和Procise完成RTL整板实现。本轮未重新构建模型或C++。
学校共享环境、Downloads原案例和外部仓库未修改。后台补充站点连接被拒绝，未读取最新正文或凭证。

## 构建及工具问题

私有副本只替换缓存源码，板卡管脚、时钟及`constrs_1`约束与原工程一致。
复制后发现旧任务的post-route脚本路径仍被工程引用，导致首次实现启动检查停止；
清除该旧钩子，在私有副本中复用已完成的综合，再运行布局、物理优化及布线。
原厂部分脚本不是UTF-8，路径重写改用字节替换，保留原编码。

沿用既有DDR保留流程：522个DDR物理接口/时钟单元位置固定，保留专用DDR路径，普通逻辑允许重新实现。
安装目录写入保护阻止工具脚本改写共享时序库；3个工具数据文件前后SHA一致。
厂商钩子重新生成了MIG DCP及5个派生元数据/仿真桩文件；登记的其他RTL与约束在构建前后保持一致。
这些构建检查不能替代实际DDR写读验证。

| 检查 | 结果及边界 |
|---|---|
| 旧/新缓存RTL比较 | 7组通过；包含换帧、格式、边界及1080p缩放 |
| 综合及整板布线 | 成功；最终布线错误0 |
| setup / hold | WNS +0.030 ns / WHS +0.004 ns，TNS与THS均0 |
| NPU脉宽 | 原有2项告警，WPWS -0.409 ns；不是生产时序签收 |
| 整板资源 | LUT 45515，寄存器63228，BRAM tile 172.5，DSP 50 |
| 缓存网表审计 | 第二组数据512个寄存器及1个有效位存在，未混入公平仲裁 |
| 跨时钟数据 | 6组mailbox路径均可见且余量为正，bus skew无违例 |
| DDR校准连接 | 5个IDELAYCTRL的RST/REFCLK均有驱动 |
| 打包 | 新PL有效载荷匹配；FSBL、BL31、U-Boot与板上备份逐字节一致 |

仿真中，两行采样读次数2176→272，人脸对齐24912→7079，1080p检测缩放43200→43200。
**这些是仿真计数，现有FAC1没有对应的板上读取次数计数器，不能称板测降幅。**

## 板上试验与失败

原位流先取得8组标准输入的基线，每组1次首轮及10次重复，共88次预处理；
所有输出与独立像素参考逐字节一致，每组完整原帧读回一致。
输入包括双行采样及更换源内容、RGB565、非整齐步长、旋转边界、112对齐和1080p检测缩放。
另保存同一公共测试照片的12个检测输出tensor SHA、特征SHA和检测结果。

部署前只读挂载并备份启动文件，持有硬件锁、停止照片服务后替换BOOT；
使用独立`wcis-cache-trial-20261018.timer`准备240秒未验收恢复，不覆盖历史JPEG回退单元。
该计时器依赖Linux能够启动，不保证无法启动时的软件回退。

| 阶段 | boot ID | 有界DDR写读 | FAC1/NPU验证 |
|---|---|---|---|
| 原版基线 | `43d0a6fd-ef63-4b81-8972-173d658eff1e` | 4组零错误 | 88次像素参考及公共照片输出基线通过 |
| 缓存候选 | `0546e36e-09b8-4054-bd4b-ee0388d12fc4` | **失败** | 停止，未启动FAC1/JPEG测试命令 |
| 回退原版 | `e9983c3a-858a-4aa9-be4d-7af946632243` | 4组重新零错误 | 88次像素参考通过，公共照片模型输出及检测结果与基线一致 |

新BOOT SHA256：`8a6e38e18daac73f3f1b259daf40ddc8a5e9ddd6b8701754a78de18840977c14`。
新bit SHA256：`cc2009d38bd0a6ea127d5de1ad0c96bbdcc77f2e7613bbf096e4b065d9a80f2d`。
已恢复的原BOOT SHA256：`e472e96cdf7ce6d82d1f278fda0240b68580e71558c031045210f844865d629b`。

预检复用相同SDK程序及其分配的内存，每组4147200字节，组合覆盖offset 0/64与整块/64 KiB分块。
新候选四组不同比特的字节数分别为8025、8015、8017、8019；二次读取间变化16、22、17、27字节。
错误均集中在64字节块中索引61的字节、该字节的bit 1（索引从0计数）。
这些是SDK缓冲读回的统计位置，**没有未经映射核实就换算为实板某根DQ管脚**。
程序退出码为0，但数据比较失败；验收检查正确拒绝了该候选。
该阶段`customop_started=false`，不能把错误直接归因于新缓存处理算法，也不能排除整板实现/初始化的影响。

检测失败后，当前启动被隔离，没有重试硬件命令，立即执行已校验的恢复流程并正常重启。
候选未写入accepted标记。新缓存、JPEG/NPU重叠及真实性能在该候选上均未验收。

## 回退后的状态与离线定位

回退后再次只读核对BOOT、DTB及uEnv与任务前备份一致；运行中的FDT及服务文件SHA也一致。
人员库全部文件SHA保持一致，照片服务ready，硬件锁可释放，当前启动无隔离标记。
失败启动的隔离记录保留，不删除或当作当前启动故障。
原位流完成DDR、像素及NPU回归后，仅把`video-stream-current.json`、`replay-current.json`
的`verified_boot_id`刷新到本次已验证的回退启动。缓存回退计时器已disabled。

只读比较新旧完整布线检查点：24466个同名DDR相关/时钟原语中，1366个单元的LOC或BEL发生变化；
筛选出的物理I/O/PHY/专用时钟类原语位置无变化。**仅锁物理接口并没有完整保留原DDR内部实现。**
这是实现差异，尚不是错误根因；不能由正setup/hold余量断言DDR一定稳定。

还导出了新旧完整CustomOp模块边界：均1876个引脚，但有两对综合优化产生的输入名不一致
（`busy142_out`/`busy151_out`、`p_0_in41_out`/`p_0_in50_out`）。
未证明其逻辑等价前，不强改名字或绕过严格接口检查来替换模块。
后续需要先解决DDR实现保留与初始化稳定性，并核实可替换的模块边界；不是继续堆缓存或仲裁优化。

## 证据和未完成项

任务目录中的关键证据：

- `simulation/verification.json`、`source-manifest.json`、`cache-only.patch`。
- `timing-gate.json`、`timing.rpt`、`route-status.rpt`、`drc.rpt`、`mailbox-audit.txt`、`cache-netlist-audit.txt`。
- `boot-candidate/manifest.json`、`board-before.json`、原启动文件备份、`deployment.json`、`trial-boot.json`。
- `memory-probe-before.json`、`memory-probe.json`、`memory-probe-rollback.json`。
- `before-verification.json`、`rollback-verification.json`、`face-before-summary.json`、`face-rollback-summary.json`。
- `rollback-verified.json`、`checkpoint-comparison.json`、两套DDR原语/模块边界导出、`completion-summary.json`。

当前状态是**保留原可用位流，新优化验收未完成**。真实SDI采集、PAD攻击验收、新公平仲裁及新缓存性能均不由本轮证明。
本记录同步归档至`D:/bigfuture/竞赛/记录/2026-10-18.md`，保留此前同日记录。
