# 第1项优化：人脸识别与PL JPEG共用原帧（2026-10-18）

后续更新：[真正NPU/JPEG重叠执行](npu-jpeg-parallel-20261018.md)已通过板测；
本文件保留前序“分时共存”的实现/证据，不覆盖后续并行结果。

对应`project-capabilities-20261018.md`最初优化清单的第1项“先核清并发契约，再做识别与录像共存”。
本轮已实现并上板验证ModelBackend的**分时共存**：同一原帧只上传一次，交替执行人脸预处理/NPU与PL JPEG，
每个SDK请求完成并关闭设备后再交给下一个消费者。未删除全局锁，没有同时运行两个硬件任务。

这次改动属于PL加速器访问与DDR输入复用；没有新增前端、语音、权限、事件录像调度或摄像头驱动。
现役HTTP服务入口未换成新流程；新能力通过独立后端入口验证，不能称正式网页已支持识别录像同时使用。

## 原因与实现

原`wcis_jpeg --serve`在整个会话内保持设备和独立源/输出分配，旧启动器因此暂停照片服务。
识别的缓存进程则每次请求打开设备、建会话、完成后关闭。直接去掉锁，会使不同SDK实例各自分配内存，
还未证实保存中的原帧不会被另一个实例覆盖，不能据整板已有FAC1/JPG1就假定安全并行。

复用现有、已经上板的`src/frame_lease.h`契约及`retained_pl_runner.cpp`、`cached_npu_runner.cpp`：

1. `wcis_face_pl_retained`通过SDK分配原帧、保护头尾与身份预处理scratch，生成包含boot、frame_id、随机token、
   base、大小、宽高、pitch、格式的描述符。CPU保持原帧所有权，各SDK句柄不跨Device::Close存活。
2. 新`src/leased_jpeg_runner.cpp`编译为`wcis_jpeg_leased`，启动/空闲不打开设备。每次请求解析原帧描述符，
   拒绝旧boot、非法token、超窗口/不匹配大小、非紧密排列的1920×1080输入。
3. 打开设备后**先用SDK保留原帧的准确区间，再分配独立JPEG输出区**。通过MemManager检查与头尾guard，
   向已有JPG1寄存器提交原帧源地址；不再读入/上传另一份原图。
4. JPEG输出单独申请8 MiB容量及两端64字节guard，总计8,388,736 B；限制在已验证128 MiB窗口。
   验证完成状态、帧号、长度、非零周期、SOI/EOI、源/输出guard，读回实际JPEG字节，独占新文件并fsync。
5. 先销毁SDK内存句柄、关闭设备，再回传完成。结果绑定frame_id/token、pts_us及调用方提供的原帧SHA。
   pts是本次离线测试合成时间戳，SHA是来源绑定信息，不能当作硬件自行计算的摘要或真实采集时钟。
6. 新`leased_jpeg.py`只允许一个命令在途，校验回传身份、未重新上传、原帧保护和设备已关闭。
   调用者整段持有现有`npu.lock`；原帧最后由原所有者释放。与既有人脸租约接口兼容。

先实现并验证串行交接，没有改JPEG固定优先的RTL仲裁。当前没有两个核并发争抢，因此不能从本次测试推断公平性、
最大等待时间或硬件重叠能力。若以后并行，必须另行验证SDK、多分配器、仲裁及等待上界。

## 构建与测试

学校独立任务：`D:/yzd/tmp/wcis-face-coexist-20261018`。
本机证据：`D:/yzd/tmp/face-jpeg-coexist-20261018`。
连接、其他Python任务、GCC/CMake/SDK已重新核实；AArch64程序在学校服务器使用GNU 10.3.1编译。
任务专用TMP/TEMP/TMPDIR、XDG_CACHE_HOME；显式设置PATH、CROSSWIN_TC、MSYS2_ARG_CONV_EXCL。
共享环境、SDK及其他任务只读复用，未改停止其他任务。

新增构建脚本`scripts/build_face_coexist_school.ps1 -TaskRoot D:/yzd/tmp/wcis-face-coexist-...`，
上传源码至任务`cross-source/npu_photo`后仅构建`wcis_jpeg_leased`。初次编译发现SDK的write接受可变char指针，
已将guard写缓冲改为可变vector后编译通过；未通过宽松编译选项掩盖类型问题。
未重新编译模型、修改RTL、生成bit/BOOT、改时钟或重启板卡。

使用已有单人、四人拼图、无脸公开测试图；部分960×540素材在本机按明确步骤放大至1920×1080后打包，
各生成BGRX8和RGB565LE两种格式，共6份源内容。不是SDI实采、原生1080p细节或真人准确率样本。
输入JSON记录来源SHA、原尺寸、格式、pitch及原始像素SHA。

首轮2轮共12个保留帧，最终源码另做1轮6帧回归，共18个完整保留帧：

```text
上传一次/PL检测输入 → NPU检测及各脸特征（before）
→ JPG1压缩A → 同帧PL检测输入/NPU再次识别（after）
→ JPG1压缩B → 完整原帧读回验证 → 最后释放
```

| 验证 | 结果 |
|---|---|
| 完整保留帧 | 18帧，0/1/4张脸，两种格式，包含反复切换帧内容 |
| 实际NPU调用 | 完整帧测试共96次，before/after全部检测头与特征原始SHA一致 |
| 实际PL JPEG | 完整帧测试共36张，A/B字节一致、帧号及读写块计数正确 |
| 原帧保护 | 每个完整帧在NPU/JPEG交接后全量读回一致，不仅检查guard |
| 新/旧帧绑定 | 不同源SHA不能返回同一旧JPEG；相同源重复压缩字节一致 |
| 独立解码/像素对照 | 首轮24张及最终12张逐一与对应打包源比较，完整1920×1080；首轮最低PSNR 39.17 dB，预设下限20 dB |
| 描述符拒绝 | 10项在SDK访问前拒绝，未探测猜测物理地址，既有输出未覆盖 |
| 停止请求 | JPEG完成边界停止、JPEG同步命令在途时停止，均正常收尾、原帧完整 |
| 最终子进程 | 最终6帧回归和命令在途停止均4个子进程退出码0 |

10项拒绝覆盖旧boot、错误token、超窗口、分配大小不符、错误布尔类型、布尔帧号、错误几何、负时间戳、
无效摘要、已有输出文件。无效描述符按源码控制流在Device::Open前退出，不用非法地址触发硬件错误测试。
源描述符/guard并非抵御恶意本机root的授权机制；这是受控后端的内存与帧所有权契约。

停止测试通过20 ms定时向测试父进程发送SIGTERM，JPEG命令返回前已收到停止请求。
JPEG worker在独立进程组，当前命令完整返回后验证原帧并关闭所有worker；未向SDK/DMA进程发终止信号。
这是命令在途停止证据，没有通过硬件trace证明信号恰在某一个AXI beat。
SDK发生错误/超时后保留本boot复核标记；停止时等待当前操作，若正常期限内不能收尾，保持锁等待，
不强杀并提前回收DMA内存。真正设备卡死或断电恢复不在本轮验证范围。

## 收益和代价

新JPEG路径每次回传`source_uploaded=false`；每个保留帧只由FAC1上传一次，供识别和两次JPEG共用。
相对JPEG与识别各自上传同一原帧，按当前1080p格式，每帧可省去一份4,147,200 B（RGB565）
或8,294,400 B（BGRX）的源传输；这是输入复用量，不是实测整条链路提速比例。

首轮24个JPEG命令的worker中位约72.87 ms，PL提交/轮询中位约41.74 ms。
worker包括设备打开、保留/分配、压缩、读回、文件写入及fsync；本次测试还反复推理、全帧读回、保存证据，
不能以这些数据承诺持续录像FPS。分时入口增加设备开关成本，纯JPEG吞吐可能低于旧持久设备入口。
本轮优先解决能否安全共存与重复输入，不声称同时实现2轮/秒识别、20 FPS录像或长期无泄漏。
两种格式的JPEG输出分配分别重复落在相同SDK选择地址，测试范围内未见分配增长；不是完整DDR容量/长期压力测试。

照片服务进程本轮没有停止，前后health均ready；但测试整段持有全局锁，其他识别请求仍可能收到busy。
所以“测试中共存”指新后端单一所有者交替调用两个消费者，不代表两个独立旧客户端可不加约束地同时运行。
原`launch_jpeg_stream.py`仍使用旧持久JPEG路径并会暂停服务，本轮未偷偷更改其行为。

## 新入口和证据

最新候选目录：`/root/wcis-face/candidates/coexist-20261018-b340c231a419`。
完整测试入口为其`src/check_face_jpeg_coexist.py`，独立JPEG接口为`src/leased_jpeg.py`和`wcis_jpeg_leased`。
板端例子（输出目录必须是新目录，运行时占用原硬件锁）：

```sh
python3 /root/wcis-face/candidates/coexist-20261018-b340c231a419/src/check_face_jpeg_coexist.py \
  --jpeg-binary /root/wcis-face/candidates/coexist-20261018-b340c231a419/wcis_jpeg_leased \
  --cycles 1 \
  --seeds /root/wcis-face/candidates/coexist-20261018-b340c231a419/seeds/group-4-BGRX8.json \
  --out /mnt/wcis-emmc/wcis-face/recording-tests/coexist-manual-001
```

最多120个保留帧；启动前按每帧两份最大8 MiB JPEG预算，额外预留512 MiB空间。
读取人员库采用只读快照和既有纯模板计算，未调用会自动建库/恢复孤儿文件的构造逻辑；逐帧核对存储身份与快照SHA。
后续接入真实SDI时还需生产者/消费者缓冲契约、源帧写入完成/释放、持续采集时间戳及掉帧策略；
JPEG写盘重叠、业务事件和长期性能属于后续工作，不能因本次有界交错通过而视为完成。

本机关键证据：

- `normal-verification.json`、`final-verification.json`：12帧首轮及最终6帧回归。
- `stop-verification.json`、`inflight-stop-verification.json`：边界/在途停止。
- `rejection-verification.json`：10项拒绝；`decoded-source-verification.json`及`final-decoded-source-verification.json`：图像对照。
- `measurement-summary.json`、`board-before.json`、`board-final.json`、`final-audit.json`、`source-manifest.json`。
- 各`*-run.json`给出确切候选、板端输出目录和命令；首轮、停止、最终回归使用各自保留的候选版本。
- 学校产物`npu-build/wcis_jpeg_leased`，本机收集在`school-build/npu-build/`。

前后boot、现役FDT、服务单元、正式应用文件及6个人员库文件SHA保持一致；硬件锁可再次取得，当前boot无复核标记。
后台信息站`http://10.101.54.192:18080/`本轮仍连接被拒绝，未读取最新内容。
同日工作记录同步追加到`D:/bigfuture/竞赛/记录/2026-10-18.md`，保留既有记录。
