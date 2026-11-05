# 原始位流与原始摄像头案例对照（2026-10-20）

> 本文记录原始位流的对照阶段。后续项目参考输入已修正到完整版CLK1并上板通过，当前运行修正版，详见 [修正与验收](sdi-refclk-fix-20261020.md)。本文的原始位流启动身份、服务状态与恢复入口保留为当时记录；当前操作入口以 `../lan_stream/VPU_LIVE.md` 为准。

## 本次测试目的

此前已验证项目位流上的板内测试图采集、VPU JPEG 编码与内网传输；真实 SDI 测试未锁定。此前原始 BOOT 虽启动并执行过恢复任务，但没有完成原版摄像头程序测试，不能说原案例也收不到输入。本次补做原始位流与原始程序组合对照。

## 已执行操作

- 客户端本地时间 14:15 后，通过 `192.168.1.102 → 192.168.1.113` 核对当前启动 `5e10dfdf-2905-4778-975f-cd7b0fe821d2`；采集和照片进程均未运行，直播 HTTP 服务及 eMMC 存储服务运行。当前控制文件指向已经停止的 VTC 会话，不把它当作摄像头输入。
- 新任务目录为本地 `D:/yzd/tmp/factory-camera-ab-20261020`、板端 `/root/wcis-face/candidates/factory-camera-ab-20261020`，与此前案例切换记录分开。
- 只读挂载 SD 核对 BOOT、DTB、uEnv，另存项目 BOOT 到任务目录；保存服务启用状态及人员库全部文件 SHA256。NPU 与摄像头锁均可独占取得。
- 原始 BOOT SHA256 为 `0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca`，项目 BOOT 为 `f48397d08b1ccb1c950adafcebe5e36678154e73fa1d19792150aa5ddccd8ad1`。写临时文件、fsync、校验、替换 BOOT 后再次核对，DTB 与 uEnv 保持原值，卸载 SD 后请求重启。写入回执时间为客户端本地 14:17:30。
- 原版程序为 `sdicamera+yolov5+hdmi.vendor.bak`，SHA256=`ceab9cb128f2b78385a8b5c39c22b1fad2b6830505d5242ccd87affd4f53ab7a`。保留原始模型、配置及 HDMI 输出；测试配置仅将日志目录重定向到任务空间，`vtc: false`、输入 1920×1080。原配置 fps=60 是原案例参数，不把它当作摄像头实际输出帧率。
- 配置启动后自动短测服务：运行 15 秒后发送回车停止，超时再终止进程组；记录退出码、输入成功行、零输入计数及摄像头错误。是否真正执行和是否取帧成功，要以本次启动证明和结果文件为准，部署服务不等于测试已完成。
- 设置开机 8 分钟后的项目 BOOT 恢复定时任务。该任务依赖 Linux/systemd 能继续运行，不能保证覆盖早期启动挂起或内核完全停滞。
- 全程未编译模型或 C++，未更改分区表、DTB、uEnv、引脚、跳线、原始模型、人员库或外部案例源码。按用户要求未读取之前事故的心跳或内核日志。

## 14:21 网络检查

客户端直连 113，以及先连 102 再连 113，两条路径的 TCP 22、8092 均超时。102 本身可连接。ARP 邻居状态不能证明 Linux 用户态或 SSH 服务正常；目前不能由连接超时断言板子死机、原案例没有输入或测试已执行。

## 第一轮结果及运行库修正

14:26 左右，通过 102 重新连接成功。原始位流启动身份为 `aa804bff-5cb7-4621-8312-8d3dc330d74f`；本次 BOOT/DTB/uEnv 核对文件已经保存，原版程序确实执行，但约 0.62 秒以 127 退出，报 `Network::lazyLoadParamsFromFile` 未定义符号。这是运行库 ABI 不匹配；程序未进入摄像头采集，不能由输入成功行数 0 推断无 SDI 输入。恢复任务随后恢复项目 BOOT，重启身份为 `7de2e25e-6c58-4f26-a4c0-17be729808fd`，照片服务重新运行。

在 Downloads 原案例附带的 `Icraft_3.33.1_onchip.deb` 中找到对应运行库。只提取其中九个 `libicraft*.so` 到第二轮独立任务的 `runtime` 目录，未安装 deb、未覆盖系统库。deb SHA256=`72849792597d065869755e7ff97d49a9c5cf56c5154b5cd300c880d3b4178608`。使用进程专属 `LD_LIBRARY_PATH` 与 `LD_BIND_NOW=1`，以不存在的配置路径执行原版程序；程序进入配置读取并按预期报配置不存在，退出 255，未打开硬件。该检查证明动态链接入口已通过，不代表模型或相机已通过。

第二轮使用 `factory-camera-ab2-20261020` 独立目录，原版程序与原始位流不变，测试进程隔离加载原案例库；恢复定时改为开机 90 秒。后续结果以第二轮结果文件为准。

## 原始位流取帧对照结果

第二轮在 Device::Open 前因漏提取 `libaxizg330aiu.so` 设备插件退出。第三轮补齐 Icraft deb 的 21 个普通运行库，设备成功打开，但没有 DetPostZG 插件，模型初始化以 UnknownNode 未绑定后端退出。前三轮均不是摄像头无输入的证据。

第四轮补齐同包 `CustomOp_3.33.1_onchip.deb` 的七个算子插件（包 SHA256=`125170f43be6f016b4316792b626e4cefce80be2315c0d2e8c4174c426c9822e`），进程专属预加载 DetPostZG。原案例材料还存在版本混合：模型 JSON 记载 Icraft 3.36.0、XIR 3.36.0.1，附带运行库为 3.33.1；原二进制拒绝配置中的 `ocm_option: -1`。保持原始文件不动，仅任务配置将它改为支持的 `0`，关闭 OCM 优化。后续必须称作“原始位流、原始二进制与兼容配置”，不是所有参数逐字不变的原厂整套验收。

采用相同隔离运行库和兼容配置做对照：

| 启动与位流 | 实际摄像头结果 | 程序后续结果 |
|---|---|---|
| 项目位流，`d731833c-4e19-421a-b1a7-7b3b43321709` | 短测约15秒，10次 `data_in_num=0`，取帧超时，输入成功0 | 停止阶段输入队列异常退出 |
| 原始位流，`0d89d23a-c9b4-439a-836c-5671690a93d1` | **4次 `<Input:ok, ps_frame_ok>`**，首帧63.42ms，后续33.20/33.24/33.26ms；零输入和相机错误均0 | NPU forward 报输入张量数2与1不一致，异常退出 |

原始位流日志明确 `SDICameraInputActor initialized`、`All actors started`，并完成四个 PS UDMA 帧缓冲的真实取帧；`vtc: false`。本次证明当前摄像头/连接可以在原始位流路径下提供输入，不能再称为“原案例也没输入”。没有取得原 HDMI 显示截图或完整 YOLO 推理成功，不把四帧取帧成功扩写为完整案例通过或长时间稳定性通过。

对照将排查重点转向项目位流的 SDI 接收/复位/时钟等差异；尚未定位具体 RTL 或约束根因。原始 BOOT 本次仍配现有 DTB/uEnv，另有软件版本警告，这些变量保留，不能据此断言单一硬件模块已损坏。

14:40 之后恢复项目 BOOT，启动 `c0a85122-d779-45ba-8007-5b59fb209e10`。BOOT、DTB、uEnv 与初始检查逐项相同，照片服务 ready、eMMC运行，全部人员库文件与原应用文件哈希不变。四轮测试服务和恢复定时器均已禁用。Windows 直连 113:22 取得 OpenSSH banner，102 转连也可用。

本地新增证据为 `D:/yzd/tmp/factory-camera-ab{2,3,4}-20261020`；第四轮 `project-ocm0-reference-result.json`、`reference-result.json`、`factory-proof.json`、`final-verify.json`、`direct-final.json` 分别记录项目位流对照、原始位流取帧、启动证明、恢复完整性及本机直连。

## VPU 摄像头图像验证续做

原始位流不含项目新增 SDI2 监测块，旧直播程序会在真正取帧前拒绝。因此在 `wcis_sdi_vpu_live.cpp` 和启动器中增加只针对核验过的原始 BOOT 的兼容通路：启动器检查当前启动身份和原始 BOOT SHA256 后注入标记；此模式使用同样的有界取帧，未完成仍立即退出隔离。项目位流继续要求 SDI2 新鲜、锁定、格式正确，没有取消其门槛。

新版本在学校独立目录 `D:/yzd/tmp/wcis-camera-preview-factoryvpu-510520e7` 完成交叉编译，二进制 SHA256=`339fe415623f019779e9f9561c8d6fada607598adaf3232a04a756c37cbdcb88`。本地构建材料在 `D:/yzd/tmp/sdi-vpu-factory-20261020`。板端任务 `factory-vpu-20261020` 使用原始位流采30帧，并记录当次网络地址、监听端口和待完成系统服务，不读取之前事故日志。

该次启动 `dce0af47-e1e7-4eb7-b5b3-c5976e113116` 上，真实camera输入采集30帧、VPU JPEG编码30帧，退出0。保存了带来源、启动身份、帧号、采集时间的JPEG；取回并检查960×540真实室内图像，画面偏虚。不是VTC图。该有限测试后按定时恢复项目位流，启动为 `6333c820-5fd2-4d1e-996e-fc121300dea5`。

## 原始位流下网络恢复与实际内网直播

本次启动状态证据表明，SSH已监听0.0.0.0:22，HTTP已监听0.0.0.0:8092，但eth0为DOWN、MAC为00:01:02:03:04:05、没有IP和路由，systemd-networkd未运行。该观察解释本次原始位流下的端口不可达；不将它无证据推广成所有历史失联事件的根因。对照项目位流下实际网络为MAC ae:59:f4:2d:3a:99、192.168.1.113/24、网关192.168.1.1。

创建独立 `factory-vpu-live-20261020` 任务。其启动服务每次先只读核验原始BOOT及启动身份，确认eth0属于已见过的默认/项目MAC，随后仅在当前Linux启动中恢复上述既有MAC、IP及路由、启用eth0，再独占启动camera VPU持续采集。未改写系统网络配置文件或板卡引脚、电平、跳线。

当前保留**原始位流**运行真实摄像头预览，启动 `1d51bcaf-5a4a-4f04-aaaa-ab00ad5e920e`：

- `http://192.168.1.113:8092/` 提供实时MJPEG，输入camera，输出960×540、上限5fps，经PS eth0输出。PL网口的MAC/RGMII传输逻辑仍未实现。
- Windows本机直连取得帧159/160/161/162/163；102主机取得160/161/162/163/164。同一会话 `234ac25e9fdc473787fa6006dbc5f5f7`，帧具有完整JPEG边界及不同帧号。Windows还成功取回实时快照。
- 核对时采集241帧、编码241帧，`ready=true`、来源camera，eth0为UP/LOWER_UP、113地址和既有MAC正确，连续采集服务active。该计数仅是短时验证，不是长期稳定性或1080p30编码性能承诺。
- 两台主机真实传输验收通过后禁用并停止90秒恢复定时器，保留当前直播。直播服务和HTTP服务启用开机启动；直播启动服务每次重新建立本次启动的BOOT证明，不复用旧启动证明。
- 原照片服务及启动仍禁用，以避免原始位流下启动新增FAC1路径；原始位流不含项目新增eMMC通路，当前不是完整人脸门锁项目部署。此前恢复项目时人员库与全部应用文件均已核验不变，本次摄像头预览不写人员库。
- 一键回到完整项目：板端启动 `wcis-factory-vpu-live-20261020-recover.service`。它停止采集、核对任务备份和DTB/uEnv、恢复项目BOOT、恢复原照片服务启用状态并重启；随后需要重新核验服务和人员库。不要在原始位流上直接启动照片服务。

当前证据：`D:/yzd/tmp/factory-vpu-live-20261020/{factory-proof.json,network-restored.json,windows-stream.json,gateway-stream.json,live-verified.json,camera-live.jpg,board_task.py}`；先前30帧证据为 `D:/yzd/tmp/factory-vpu-20261020/{capture-result.json,camera-vpu.jpg,project-network.json}`。所有启动/测试/恢复脚本只位于各自任务目录，没有在板子执行模型或C++编译。

## 本地证据

- `D:/yzd/tmp/factory-camera-ab-20261020/board_task.py`、`control.py`。
- 同目录 `preflight.json`、`switch.json`、`stage-output.txt`、`direct-network.json`、`gateway-network.json`、`network-check.json`。
- 背景来源：`D:/xiangmuwendang/WCIS-FPAI/wiki/PS/OrchestrationLayer/VPU串流直播SOP.md`；原案例源码 `C:/Users/anxianji/Downloads/20260916/fpai_demo_app/fpai_demo_app/examples/1_single_input+ai/PLin+SingleNet+HDMI/src/sdicamera+yolov5+hdmi.cpp`，未修改。
