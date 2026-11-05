# SDI 参考时钟输入修正与验收（2026-10-20）

## 修正范围

根据 `sdi-bitstream-compare-20261020.md` 的实物型号、时钟接线及最终 DCP 对照，用户授权将项目的 SDI 参考输入从 Lite 板的 R6/R5（CLK0）切换到完整版 U6/U5（CLK1）。不改电平、跳线、时序数据库或启动分区布局。固定入口约束见 `constraints/fmql30tai_full_sdi_refclk.xdc`，后续工程准备脚本以 LATE 顺序应用该覆盖。

本次在最终 `D:/yzd/tmp/face-cache-resume-20261020/preserved-routed.dcp` 上局部修改三个输入相关单元、三条参考时钟相关网络，并补齐输入缓冲 CEB 的接地支路。其余单元和非恒定网络分别比较位置与布线，保留已有 FAC1、缓存优化、DDR、eMMC 和 SDI2 逻辑。没有重新综合模型，也没有在板端编译。

学校服务器本次复查未找到 Vivado，本机使用既有 Vivado 2018.3 和 Procise；临时文件、报告和产物独立放在 `D:/yzd/tmp/sdi-refclk-fix-20261020`。首次局部布线调用因旧版工具不支持同时使用 `-preserve` 与 `-nets` 而退出，改用明确三网范围的 `-nets` 并保留范围外一致性断言。

## 验证进度

第一遍局部修正后，126818 个范围外单元的位置、514026 项层次网络布线记录比较一致，setup WNS=+0.005ns、hold WHS=+0.004ns。514026 是层次查找返回的布线记录数，包含层次/匹配展开，不是整片独立物理网络数；报告中的 logical nets 为145824。

最终 DRC 阻止第一遍候选生成位流：`GLOBAL_LOGIC0` 的新位置 `MGTCLKIN0/CEB` 未布线。不能把该候选视为通过。独立完成接地支路后，再次比较全部非恒定网络及单元位置。重新打开 DCP 时 REQP-52/56 恢复默认 Error；与旧候选报告逐项核对发现它们是原有 GTGREFCLK 提示，按原项目已有四条规则 REQP-44/46/52/56 的 Warning 设置复现，不新增 DRC 降级。原有 NPU 两项最小脉宽违例（WPWS=-0.409ns）仍是完整时序签核的限制，不能宣称生产时序收敛。

接地完成后的第二遍检查：126821 个非恒定原语的位置一致、514031 项非恒定层次网络布线记录一致；104649 条可布线网络全部布好，routing errors=0。setup WNS=+0.005ns、hold WHS=+0.004ns；bus-skew 无 VIOLATED。沿用已有厂商代理器件规则后，最终 DRC 无 Error/Critical Warning，没有为新增故障降低检查等级。已安装工具库3个文件与旧基线校验值一致。

最终 DCP 为 `D:/yzd/tmp/sdi-refclk-fix-20261020/refclk-final.dcp`，SHA256=`8e54e4cb42be0164d7925e9d2ef877745d663f79a87f4d8272414543441be2e8`。Vivado 成功生成 `refclk.bit`，Procise 完成 disable-ICAP 处理并生成 `boot-candidate/BOOT.bin`。新 BOOT SHA256=`f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297`。分区解析确认 FSBL 183892B、BL31 53824B、U-Boot 802400B 与旧项目逐字节一致；它们此前也与原始 BOOT 核对一致。本次只改变 PL 分区，DTB 和 uEnv 未改。

## 实际部署与板端验收

1. 试验前仍是原始 BOOT `0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca` 的真实直播。独立备份该 BOOT，保留原查看器单元和原直播服务作为回退，设置240秒开机恢复期限；该恢复依赖Linux正常启动，并非硬件双镜像容灾。
2. 将修正版写入原 BOOT 文件，回读哈希一致；DTB `e7edf0bc5eb31485962c9bfbefff60c250c9ec14363ccdd41a695173a127d3af`、uEnv `a13c985eb5031d75ec7069333897cae38944ba5fbadd509828b63e6a48408560` 保持一致，卸载文件系统后重启。
3. 新启动身份 `b174ec4a-a93d-4833-81ca-962ecdf4ba9a`，当前 BOOT 已只读核验为 `f6da96…`，没有 `/download.bit` 覆盖启动位流。启动程序恢复此前验证的PS网口MAC/IP，不改永久网络文件。
4. **真实摄像头30帧采集、30帧VPU JPEG编码成功，程序退出0。** 输入配置1080p30，输出960×540、上限5fps。复用学校服务器先前交叉编译的程序，SHA256=`339fe415623f019779e9f9561c8d6fada607598adaf3232a04a756c37cbdcb88`，没有在板端编译。此修正版走SDI2新鲜/锁定/1920×1080门控，不使用原始位流的无SDI2特例；实际截图可见桌面、笔筒与置物架。
5. 摄像头有限采集正常退出后释放硬件锁，再运行原有 retained FAC1 worker：**8组、每组11次，共88次金标输出哈希一致**；每组完整输入源读回相等，worker退出0。未把小缓冲验证外推为完整2GB PL DDR容量测试。
6. 启动eMMC存储服务、恢复挂载后，原人员库6个文件（含4个原始文件）的哈希与切换前记录逐项相等；本次直播不写人员库。
7. 开启持续采集。Windows直接访问收到帧44–48，102主机收到帧45–49，两端都为camera、同一新启动与同一会话 `b2784c6d3f2f4acaa667f71fb9d1f61c`，各5个不同帧号且JPEG首尾标记正确。最终接受时连续采集/编码均到79帧，最新帧年龄0.068秒。
8. 上述检查全部通过后保存 `accepted.json`，停止并禁用240秒恢复计时器，保留修正版作为当前启动版本。启动服务为 `wcis-sdi-refclk-fix-20261020.service`；查看器仍在 `http://192.168.1.113:8092/`。原始位流直播服务停止且禁用，回退入口为 `wcis-sdi-refclk-fix-20261020-recover.service`，会恢复原始BOOT和原始直播服务。

收尾复查：仍为同一修正版启动和camera会话，连续采集/编码均到1008帧，最新帧年龄0.196秒；采集和查看器active/enabled，恢复计时器inactive/disabled，eMMC存储active，照片服务inactive/disabled，当前启动没有硬件隔离标记。证据为 `final-health-output.txt`，不把短时间运行外推为长期稳定性验收。

本轮对照支持：项目缺少SDI输入的直接原因是完整版板卡参考时钟入口适配错误；在其余非恒定布线保持的条件下改至U6/U5后，摄像头恢复。此前缓存优化不是本轮已证实的故障原因。保留不同硬件/跳线配置可能产生不同结果的边界。

## 验证边界与维护

- 已通过的是摄像头采集/编码/内网传输与独立FAC1回归，**没有验收摄像头到人脸识别、权限或活体防伪的完整链路**，更不能据此宣称防照片攻击通过。
- 直播使用PS `eth0`，尚未实现PL网口MAC/RGMII。960×540、5fps是当前配置上限，不是1080p30全速编码吞吐基准。
- 照片识别服务与开机启动仍停止/禁用，避免与持续采集同时打开SDK。未来切换识别模式须先停止采集并核对锁和硬件隔离标记；本次未新增业务编排或前端。
- 原有NPU脉宽告警、厂商GTGREFCLK/代理器件告警仍在；`production_timing_signoff=false`。另有SDI2诊断频率常量50MHz与实现CFG 100MHz不一致的历史问题，本轮未改该RTL常量，不能直接将其换算频率当作独立实测。
- 后续从源码重建需使用 `scripts/prepare_case.tcl`，以 LATE 顺序应用完整版约束。旧阶段的 `source_manifest.json` 不代表本轮最终DCP；当前输入、工具库、报告和产物以任务目录的 `input-proof.json`、`timing-gate.json`、`package-gate.json` 为准。
- 本轮完整脚本和证据在 `D:/yzd/tmp/sdi-refclk-fix-20261020`。当前部署、回退和HTTP接口说明见 `fpga_project/lan_stream/VPU_LIVE.md`。

## 来源

- `fpga_project/docs/sdi-bitstream-compare-20261020.md`
- `fpga_project/docs/factory-camera-ab-20261020.md`
- `D:/xiangmuwendang/WCIS-FPAI/wiki/SOP/bitproc.md`
- `D:/xiangmuwendang/WCIS-FPAI/wiki/SOP/BOOTbin位流替换手术.md`
- `D:/yzd/tmp/sdi-refclk-fix-20261020/repair.tcl`、`repair-console.txt`、`school-preflight.txt`
