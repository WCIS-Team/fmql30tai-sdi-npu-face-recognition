# Face ModelBackend

**当前入口（2026-10-30）：** [阶段验收](../docs/acceptance-20261030.md)与[维护计划](../docs/maintenance-plan.md)。现役摄像头使用单 owner 与 NPU 会话缓存，已接同帧最多四脸 PAD 模型证据；预览/录像为 540p H.264。PAD 未校准，不作为开锁许可。停止新增功能，以下按日期保留历史实现，不能把早期“摄像头未接入”等句子当作当前状态。

2026-10-27 [会话复用与 PS 展开优化](../docs/face-pad-speed-20261027.md)已部署：有限旧帧对照单脸完整请求中位约降 39%、双脸约降 46%，原始输出一致；保留完成复位、原帧校验及图片上传兼容性。

2026-10-27 [多人逐脸防伪](../docs/face-pad-multi-20261027.md)已部署：最多四脸逐项输出，同帧绑定、超限、过期及分项耗时已接入；旧帧 NPU 回放通过，现场多人实拍与校准仍待完成。

2026-10-20[双行缓存部署实测](../docs/face-cache-resume-20261020.md)完成：新位流两次正常重启回归及有界NPU/JPEG并行检查通过并最终接受，裁图预处理耗时降低约40%、双行用例约42%；服务正常，普通SDI防伪仍未验收。

2026-10-19继续[缓存增量替换](../docs/face-cache-preservation-20261019.md)：
当日已核查模块边界、原版配置复现及旧时钟分支冲突；该阶段候选仍在离线实现，未完成新位流板测。

2026-10-18双行缓存[整板试验](../docs/face-cache-board-20261018.md)：新位流DDR预检失败，已恢复原位流并完成回归；
新缓存没有通过板上验收，不能引用RTL读取量降幅作为实际性能结果。

2026-10-18补充[真正NPU/JPEG重叠](../docs/npu-jpeg-parallel-20261018.md)：
`../npu_photo/src/parallel_npu_jpeg_runner.cpp`用单个SDK设备与分配器保护原帧/两个输出，
通过真实卷积输出ready和JPEG busy采集重叠证据；`check_npu_jpeg_parallel.py`进行串行配对板测。
这不移除全局锁，也未切换正式服务入口。

2026-10-18新增[同帧识别/JPEG分时共存](../docs/face-jpeg-coexist-20261018.md)：
`../npu_photo/src/leased_jpeg_runner.cpp`和`../npu_photo/leased_jpeg.py`借用现有人脸租约，
先保留原帧再分配JPEG输出，完成后关闭SDK设备；`check_face_jpeg_coexist.py`做独立有界验证。
保留原全局锁，不增加前端/事件调度，未改变正式服务入口。

2026-10-18新增[MiniFASNet防伪模型原型](../docs/face-pad-minifas-20261018.md)：
`face_pad.py`提供官方双尺度裁图/输入和融合合同，`face_pad_inference.py`提供独立板端调用，
`../scripts/run_face_pad.py`显式接收同帧bbox和frame_id。两模型已有NPU板证，
`../rtl/wcis_pad_preprocess.v`有20组仿真；新PL未接入现役位流，真实SDI抗攻击能力未验收。

2026-10-18新增[登记候选特征比较](../docs/enrollment-compare-20261018.md)：
`enrollment_compare.py`只读比较单份特征与人员库快照，分别返回目标和其他候选分数。
不做登记放行判断，不接登记API或前端，不写人员库。

2026-10-18新增独立[质量检查与历史人脸检索](../docs/face-quality-history-20261018.md)：
入口为`../scripts/face_history.py`，支持质量原因、最佳候选、照片/离线视频建库及按图查询历史时间点。
复用现有PL+NPU提取，不新增前端，不改变正式人员库；默认质量阈值尚未经过摄像头标定。

本目录原有几何工具提供模型所需的几何配置；新增`face_history/`为独立后端入口，
按显式命令调用现有模型并管理独立历史特征库，不管理正式登记库、工作模式或网页。
RTL 入口为 `../rtl/wcis_face_preprocess.v`；完整接口、验证与未接入部分见
`../docs/face-pl-modelbackend-20261015.md`；后续 CustomOp/SDK 集成和当前验收状态
见 `../docs/face-pl-integration-20261015.md`。

当前 Python 几何工具在开发机用于对照和生成描述符，尚未部署板端；不要求
为了使用 RTL 就在板上安装 scikit-image/SciPy。新增板端适配沿用现役 OpenCV/NumPy，
在 `../npu_photo/pl_preprocess.py`，本次新固件已通过13项PL+NPU板端联合检查。
现役网页的上传与登记已接入同一PL后端，见`../docs/face-pl-service-20261015.md`；
PS保留图片解码、矩阵与张量转换，摄像头尚未接入。

后续模型运行时在 `../npu_photo/model_backend_runtime.py` 和
`../npu_photo/src/cached_npu_runner.cpp`：各模型驻留独立进程，设备按请求顺序打开/关闭，
图像与张量在有界内存临时区交换；同图约4.16秒降至0.86秒处理时间。
摄像头缓冲与调度仅记录接入约束，未实现实时视频链路；见
`../docs/face-backend-latency-20261015.md`。

`face_geometry.py` 的五点相似变换使用 InsightFace 同款
`skimage.transform.SimilarityTransform`，以 OpenCV 逆变换生成 PL 的 Q16.16 系数。
没有使用 RANSAC，也没有把整帧缩成 112×112 当成人脸对齐。

参考固定在 InsightFace 提交 `81929474ec02e54e3655f6841bced800009c592d`，
文件 `python-package/insightface/utils/face_align.py` 的 SHA-256 为
`a8b34ddd06716f5ca7e7501415cbd3789ccbce18db9e557b35e537695290d922`。
上游代码许可见同一提交 README 的 License 部分（MIT）；本次没有打包模型权重。

验证用依赖：Python 3.12、NumPy 2.5.4、OpenCV-headless **4.10.0.84**、
scikit-image 0.26.0。依赖和上游参考副本放在 `D:/yzd/tmp/face-pl-20261015`，
不要装进官方案例或共享 SDK。0.26 的 `estimate` 有弃用提示；当前为与固定上游
逐项对照而保留调用，不能据此宣称未来版本兼容。

在 PowerShell 中复跑：

```powershell
$env:PYTHONPATH='D:/yzd/tmp/face-pl-20261015/opencv410;D:/yzd/tmp/face-pl-20261015/python'
$env:PYTHONPYCACHEPREFIX='D:/yzd/tmp/face-pl-20261015/pycache'
python D:/renlianshibie/fpga_project/scripts/fetch_face_pl_reference.py
python D:/renlianshibie/fpga_project/scripts/verify_face_pl.py
```

验证运行 OpenCV 和固定上游的实际函数生成 golden，再对实际 RTL 输出逐像素比较。
它不运行推理、不重新编译模型、不访问板卡，也不改变正在使用的照片识别服务。
