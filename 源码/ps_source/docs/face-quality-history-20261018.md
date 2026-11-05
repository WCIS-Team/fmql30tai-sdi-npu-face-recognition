# 人脸质量检查与历史人脸检索后端（2026-10-18）

工作日期：2026-10-18，Asia/Shanghai，以聊天客户端日期为依据。
本轮实现两个独立后端模块，不新增前端、业务调度器或模型，不修改现役应用源码、RTL、位流和正式人员库。

## 先查案例，再确定复用边界

| 已查成熟来源 | 采用内容 | 本轮实现选择 |
|---|---|---|
| [InsightFace Server维护说明](https://github.com/deepinsight/insightface/blob/master/server/docs/maintainer-guide.md)，§6至9 | 质量检查与特征提取契约分层；FP32归一化特征；SQLite持久化和精确检索 | 复用现有MobileFaceNet特征，不移植其服务端、Web、ONNX运行时或GPU依赖；质量分数仅为启发式 |
| [Faiss距离与度量说明](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances) | 入库和查询均归一化，内积作为余弦相似度 | 小规模原型使用NumPy分块精确扫描，无需在AArch64上新增Faiss；不采用近似检索 |
| [OpenCV Laplacian教程](https://docs.opencv.org/4.13.0/d5/db5/tutorial_laplace_operator.html) | 复用OpenCV图像处理算子 | 在固定尺寸灰度人脸框上计算Laplacian方差，同时测原始框亮度、像素大小、裁切比例 |
| 项目现役`recognize_photo.py`与`ModelBackend` | 已验证的YuNet、FAC1预处理、MobileFaceNet和DDR租约 | 通过已验证的video-stream配置定位当前应用，复核文件哈希、启动号和模型契约，调用已有后端，不复制另一套识别流程 |

未直接复制上游代码；复用既有模型调用、OpenCV/NumPy/SQLite库及上述设计契约。
InsightFace与Faiss文档快照及SHA保存在`D:/yzd/tmp/face-history-20261018/references/`和`references.json`。
OpenCV教程通过网页工具读取成功，单独下载快照返回HTTPError，未假称已保存该快照。
背景信息站`http://10.101.54.192:18080/`后台连接被拒绝，未进入认证阶段，也未读取最新站点资料。

## 已实现的接口

入口：`D:/renlianshibie/fpga_project/scripts/face_history.py`。
代码：`D:/renlianshibie/fpga_project/model_backend/face_history/`。

| 命令/API | 输入 | 输出 |
|---|---|---|
| `review` / `face_quality` | 原始BGR照片、同图检测框及分数、可选质量策略 | 接受与否、原因、像素/亮度/清晰度/裁切指标、策略ID |
| `best` / `select_best` | 调用方明确归为同一人的质量候选 | 选出通过质量检查且排名较高的候选；全部不合格则返回空 |
| `index --image` | 板端单张照片、现役后端配置 | PL+NPU提取最多4脸，质量检查后写独立历史库 |
| `index --video` | 板端离线视频、抽帧间隔和帧数上限 | 每个采样帧的多脸结果、来源视频、帧号和视频时间；不合格特征不入库 |
| `import` | 显式清单，包含照片和既有带embedding的多脸结果 | 导入已有特征，不重新推理；核对照片SHA及结果绑定 |
| `search` | 板端查询照片、历史库、显式余弦阈值 | 提特征并返回Top-K历史记录、源视频及时间点 |
| `search-result` | 照片和对应已有特征结果 | 在普通电脑查询历史库，无硬件访问，无CPU模型回退 |

查询默认要求恰好一张脸；多人图须显式指定`--face-index`，指定脸若未提取或质量不合格则拒绝。
记录返回相似候选，不确认身份，不将余弦显示为概率；不同时间的同一人可能返回多条记录。
本轮实现时间点检索，未新增录像播放器、自动片段裁剪、跨帧跟踪或跨帧投票。

## 质量测量及默认值

质量检查从原始照片的检测框取像素，不用对齐图黑色补边来计算清晰度。
灰度框固定缩为112×112后测Laplacian方差；亮度与极暗/极亮比例在原始框上测。
默认阈值：可见短边40像素、检测分数0.8、Laplacian方差20、平均灰度40至215，
灰度≤10与≥245的总占比不超过0.6，出界裁切面积比例不超过0.05。
`--policy`可加载`QualityPolicy`字段组成的JSON；策略内容哈希进入每条记录。

原因包括`face_too_small`、`low_detection_score`、`low_detail_or_blur`、`too_dark`、`too_bright`、
`excessive_clipping`、`truncated_face`。清晰度不足也可能来自纹理少，噪声则可能虚增该指标。
默认值尚未经真实摄像头标定；输出明确带`calibrated=false`。未声称能可靠测量侧脸、遮挡或活体。
`heuristic_rank`只用于候选排序，不是质量合格概率。最佳抓拍要求调用方先提供同人分组，不能自动把不同人混在一起选。
当前质量检查在既有完整特征提取后独立执行，未实现提特征前拦截，不能宣称因此节省NPU调用。

## 历史库与资源边界

- SQLite保存来源ID、类型、URI、源文件SHA、帧号、视频时间、脸索引、框、质量及512维FP32归一化特征；与正式人员库分离。
- 模型/预处理`pipeline_id`与库绑定，写入、查询、重新打开均检查；跨版本特征拒绝混用。
- 默认容量10000条，可显式设置1至100000；达到上限拒绝写入，不自动删数据。未验收满容量性能。
- 一个帧内的合格脸通过单个事务写入；中途失败整帧回滚。视频或清单是逐帧提交，后续失败不会删除此前已提交帧。
- 同来源、同帧、同脸重复导入幂等；内容、来源映射或质量策略不一致则报错，不静默覆盖。重新评估应建独立库。
- 每次查询分块256条，Top-K最多100，避免一次加载全库；支持来源和视频时间区间过滤，同分按记录ID稳定排序。
- 向量检查512维、有限值与非零范数；持久化使用小端FP32。SQLite使用WAL、FULL同步和有界等待，数据库不依赖另存的易过期索引文件。
- 摘要和标准输出不包含向量。历史库本身包含人脸特征，保存位置由调用方显式选择。
- `import`信任调用方提供的模型结果；SHA可检查文件绑定，不能证明外部调用方没有伪造向量或模型ID。

视频入口有采样数与解码数上限，默认最多30个采样、10000个解码帧；最大允许300采样、100000解码帧。
优先采用解码器视频时间戳；不可用时使用标明`estimated_nominal_fps`的名义帧率估算，非单调时间拒绝。
离线视频先解码后按间隔采样，不声称是PL采集节流或实时视频调度。

板端提取仍使用既有`npu.lock`，忙时失败，不与现役请求抢占设备，不删除全局锁。
SDK工作进程置于独立会话；CLI收到SIGINT/SIGTERM后完成在途请求再正常退出，不强杀DMA设备所有者。
CPU模型解析进程常驻于单次命令内，正常结束关闭；无模型编译、CPU推理回退或故障自动重试。

## 使用方法

本机已有依赖环境：`D:/yzd/tmp/face-video-stream-20261016/venv/Scripts/python.exe`。
普通电脑可以做质量复核、导入和已有特征查询；新照片/视频的NPU提取在板端运行。

```powershell
$py = 'D:/yzd/tmp/face-video-stream-20261016/venv/Scripts/python.exe'
$cli = 'D:/renlianshibie/fpga_project/scripts/face_history.py'
& $py $cli --help
& $py $cli review --image 'D:/path/photo.png' --result 'D:/path/result.json' --out 'D:/path/quality.json'
```

`result.json`须来自同图的现有检测结果；导入或查询时还须包含`pipeline_id`、`photo_sha256`、
`identities[].embedding`以及原始脸索引/框关系。既有`recognize(..., return_embedding=True)`可生成。
不能拿仅含姓名与框的HTTP展示摘要当作特征文件。

导入清单示例，路径相对清单文件：

```json
[
  {"image": "photo.png", "result": "photo-result.json"}
]
```

```powershell
& $py $cli import --db 'D:/path/history.sqlite' --manifest 'D:/path/import.json'
& $py $cli search-result --db 'D:/path/history.sqlite' --image 'D:/path/query.png' --result 'D:/path/query-result.json' --threshold 0.5 --top-k 5 --out 'D:/path/hits.json'
```

0.5仅为调用格式示例，必须用独立实际数据确定阈值，不沿用示例为现场验收指标。

板端本轮隔离安装位置：`/root/wcis-face/candidates/history-20261018/src/face_history`。
可通过既有SSH终端运行，不启动网页。以下为有界视频样例，输出路径请换成新的任务目录：

```sh
export PYTHONPATH=/root/wcis-face/candidates/history-20261018/src
python3 -m face_history index \
  --backend-config /root/wcis-face/video-stream-current.json \
  --video /root/wcis-face/candidates/history-20261018/samples/four-person.avi \
  --sample-ms 0 --max-frames 2 \
  --db /root/wcis-face/candidates/history-20261018/my-run/history.sqlite \
  --work /root/wcis-face/candidates/history-20261018/my-run/work \
  --out /root/wcis-face/candidates/history-20261018/my-run/index.json
```

把`index --video`换成`index --image`可建立照片记录；`search --image`支持同样的`--backend-config`与`--work`。
本轮测试库放隔离候选目录，不自动迁移正式eMMC存储。需要长期保存在eMMC时应先复核挂载身份，
再选择独立历史目录和配额；本模块未新增自动挂载、空间轮转或启动服务。

## 本轮检查与真实板测

本机17项新测试通过，覆盖质量扰动、最佳候选、CLI导入/查询、图片SHA绑定、错版本、坏向量、重复导入、
整帧回滚、容量边界、分块结果与独立余弦重算、时间过滤、稳定同分顺序和防止摘要覆盖输入。
现有多脸8项回归通过。所有测试均不修改正式人员库。

板端通过原有模型与PL路径执行：

- 单人公开照片2张各入库1条，四人拼图入库4条，无脸图入库0条；重复导入返回duplicate。
- 独立同人照片查询：对应人物相似度约0.702382，对照人物约0.058506，排序正确。此为有限功能样例，不能推导真实识别准确率。
- 同一原图的清晰度约800.11；合成强模糊约6.51，被`low_detail_or_blur`拒绝；合成变暗/过曝分别命中对应原因；最佳候选选回原图。
- 实际离线视频解码2帧，每帧4脸，新入库8条，总库14条；帧号与视频时间递增。多人查询显式选择脸索引后可检索对应视频时间记录。
- 数据库关闭后只读重新打开，查询结果保持；实际CLI收到SIGTERM后正常返回`stopped`、退出码0，完成在途帧后退出。
- 本机下载同一14条测试库及真实查询结果，`search-result`成功返回视频帧及时间点，无模型或硬件访问。
- 最终7个Python模块板端/本地SHA全部一致，`python3 -m face_history --help`通过；不以测试速度作为性能承诺。
- 测试未停止或重启现役照片服务；原人员库、现役配置与启动号均保持不变，健康接口最终ready。

板测原始结果与代码来源清单位于`D:/yzd/tmp/face-history-20261018/`；正式测试结果以最终`board-final-verification.json`为准。
`local-tests.json`和`unit-tests.log`记录25项通过；`source-checks.json`记录最终部署哈希，
`local-hits.json`为本机查询结果，`references.json`为上游资料快照清单。
本轮未重新编译模型或C++，未更新BOOT或位流；不把本次后端功能验收升级为真实SDI、录像并发或长期性能验收。
