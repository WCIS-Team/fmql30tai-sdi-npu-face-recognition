# 自有照片人脸识别项目重新部署

用户指定重新上板的是本项目人脸识别。案例仅用来确定兼容的平台和验证接口。
学校编译、模型、工具和日志全部位于 `D:/yzd/tmp/wcis-face-32b2a267`。

**完整板端验收已通过。** 同一局域网访问
[照片识别页面](http://192.168.1.113:8091/)，选择照片后点击“上传照片并识别”。
当前身份库是公开演示照片登记的“样本A”和“样本B”；其他人应输出“未知”。
后续新增网页多照片登记和删除，当前登记库可由用户修改，见
[登记库管理](gallery-management-20261015.md)。下述 A/B 验收仍为原演示记录。
服务 `wcis-face-photo.service` 已启用并运行，重启后服务自动启动，空闲时不打开 NPU。

## 已确认的平台

原板 BOOT 是 2025 年 12 月的 `ai7030_top`，与教程 9 月的
`ai7030_edif_top` 不同。已核实 9 月完整 BOOT 的 FSBL、BL31、U-Boot
分区与原版本逐字节相同，只更换 PL 及其打包。原 BOOT 已备份并验证校验值，
板端 SD 备份名为 `FB202614.BAK`。

本次 BOOT SHA256 为
`b87024cef9ee06936ac7123c2c976552beb0938d255abf27036dc9bbafeddc94`。
重新启动后，adder 版本读回 `0x20230628`，16 项加一计算通过。
SDK 实测 NPU 为 4 行、2 列，所有新模型已按该尺寸生成；程序启动时检查匹配。
原厂摄像头程序通过已有 `live.disabled` 机制暂停，让本项目独占 NPU。

本轮没有部署尚未完成时序验收的自有 RTL 候选，也没有调整引脚或时钟。

## 软件和模型适配

PS 读照片、补边、解码检测结果、五点对齐和余弦比较；YuNet、MobileFaceNet
由 iCraft 3.39 FP16 生成。学校完成 AArch64 交叉编译，板端逐文件 SHA256
及输入输出合同检查通过。程序等待 Tensor ready，再用 SDK `SFB` 导出 FP32
软件顺序数据，避免把异步或填充布局数据当作最终输出。

YuNet 的六个 cls/object 分支，将线性 1x1→单通道 3x3 等价合并成密集
3x3，保留固定 640 输入的精确边界修正。11 份 CPU 输入最大误差小于
2.3e-5。只改 object 分支时身份判断通过，但四张照片的特征对照失败；
补齐 cls 分支后，11 张照片的完整流程特征对照全部通过。

MobileFaceNet 原生 PReLU 指令生成缺少配置。最初等价 ReLU/Neg 改写在
14x14 特征图的 Neg 同步失败；关闭 OCM 优化后相同失败。改成
`relu(x)+alpha*(x-relu(x))` 后，失败转移到该尺寸的逐通道 Multiply。
最终模型用中心为 alpha、其余为零的深度 3x3 卷积实现乘法；11 份 CPU
特征与原模型一致，学校生成通过。该模型单独运行在 NPU 成功，使用同一输入
的特征与 CPU 余弦相似度为 0.999956。两个网络在同一设备进程依次运行时
仍同步失败，释放 Session 也没有解决；**每个推理请求使用独立进程，并在
结束时关闭设备**后，完整流程连续运行通过。问题与运行时设备状态有关，
内部根因未确认，不能将之前的 Neg、Multiply 或某项优化认定为根因。

## 验收边界

本次板端启动号为 `ef3d1758-7d54-4811-bb83-480bc71642ae`，模型版本目录为
`/root/wcis-face/releases/20261014-b5a454c11d22`。实际绑定的 NPU 算子为
YuNet 112 个、MobileFaceNet 211 个；没有 CPU 神经网络推理回退。

- 11 张照片均检测出单脸并提取 512 维特征。
- CPU/NPU 完整流程特征余弦相似度为 0.993736～0.999879，全部达到原定 0.99。
- 最大检测框坐标差为 1.315 像素以内。
- 仅用校准照片确定阈值 0.328387，再测试：A 两张、B 一张、未知四张，全部符合预期。
- 无脸、多脸场景均拒绝识别。
- 新上传接口的 A、B、未知、无脸、多脸五类请求通过；浏览器实际选择并上传
  `img11.jpg`，识别为 A，页面显示本次推理耗时 3.60 秒。

单脸上传照片的端到端耗时约 3.55～3.60 秒，拒绝场景约 1.79～1.85 秒；
含模型进程启动、NPU 推理、PS 处理及导出，不是 NPU 单独推理时间。
两个人的小规模公开照片只证明功能流程。未验证摄像头、活体、广泛准确率
或实时帧率，也没有验收新的自有 PL RTL。

板端命令行也可以识别新照片。接口程序位于
当前 `gallery-interface-deployment.json` 中 `app` 路径下的 `recognize_photo.py`；参数为 `--root 模型版本目录`
`--photo 照片绝对路径 --out 一个尚不存在的结果目录`。登记库、阈值和模型
校验不匹配时拒绝运行。

记录：`outputs/redeploy-20261014/boot-deployment.json`、
`partition-validation.json`、`adder-validation.json`，以及
`outputs/photo-board-20261014/board-staged-release.json`、各次运行日志和
`models/*parity.json`。最终本地结果在 `accepted-results/verification.json` 和
`accepted-results/site/results.json`；上传入口验收见 `photo-interface-validation.json`，
部署与 systemd 配置见 `photo-interface-deployment.json`。失败试验按 attempt
目录保留，不自动重试。
