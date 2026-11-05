# 登记候选特征比较模块（2026-10-18）

工作日期：2026-10-18，Asia/Shanghai，以聊天客户端日期为依据。

## 范围修正

用户指出“这不是前端逻辑吗”后，本轮将实现限定为ModelBackend的只读特征比较：
计算查询向量与登记特征的相似度，分别返回目标人员和其他候选。
是否允许登记、如何人工确认属于后续业务策略；显示提示属于前端。
本轮不接入登记API、不修改前端、不自动阻止登记、不合并/修改人员库。

## 具体实现

- 源码：`D:/renlianshibie/fpga_project/model_backend/enrollment_compare.py`。
- `compare_features(embedding, gallery, pipeline_id, target_name=None, top_k=5)`接受显式人员库快照和一份查询特征。
- 复用上一轮`face_history.store.normalized`的512维向量检查及归一化，不新增模型、推理流程或运行时依赖。
- 校验模型/预处理pipeline_id，支持现有schema 1/2；最多100人、每人30份特征。
- 分别计算每人的最高单样本余弦与均值归一化中心余弦，不混用两种数值。
- 返回目标人员、按最高单样本分数排列的其他候选、其他最佳候选减目标的分数差、库revision等。
- 相同分数按人员ID稳定排序；空库、目标不存在、没有其他候选均显式返回空值，不虚构分数差。
- 拒绝错误维度、非有限/非归一化登记向量、重复人员名/ID、重复样本ID及无法形成中心的相消特征。
- 不设置重复登记阈值，不输出允许/拒绝结论，`admission_decision=null`、`calibrated=false`。
- 读取显式JSON快照，不创建Gallery/PersistentGallery实例，不执行它们的初始化、孤立文件恢复或写入流程。

依据：现有`npu_photo/gallery.py`的多照片特征均值算法、`persistent_gallery.py`的数据结构，
以及上一轮已读取的InsightFace维护说明§6的同人/其他人特征比较设计。
没有复制上游代码，也没有把其他模型的余弦阈值带入本项目。

## 使用

查询文件可以是`{"pipeline_id":"...","embedding":[...]}`，或现有单人NPU输出结果；多人结果拒绝比较。

```powershell
& 'D:/yzd/tmp/face-video-stream-20261016/venv/Scripts/python.exe' `
  'D:/renlianshibie/fpga_project/model_backend/enrollment_compare.py' `
  --gallery 'D:/path/gallery-snapshot.json' `
  --probe 'D:/path/single-face-result.json' `
  --target-name '待追加人员姓名' --top-k 5
```

未指定目标名称时，返回所有人员中的相似候选；指定名称时，目标结果与其他候选分别返回。
这是供后续策略调用的计算结果，不构成身份确认、登记冲突定论或自动放行规则。

## 验证与结果

`D:/renlianshibie/fpga_project/tests/test_enrollment_compare.py`的8项检查通过，覆盖：
同人换名候选、向其他人追加时的分数对照、最高样本/中心分数区别、空库/单人库、
错版本/坏向量/重复姓名、相消特征、同分顺序，以及CLI只读与输入不变。

另外复用上一轮真实PL+NPU特征：从14条公开测试历史库中只读取得两个公开人物的样本，
在本任务目录组成临时人员库；使用此前独立同人查询照片的特征比较：

- 同人样本相似度约0.702381903；对照人物约0.058506388。
- 指定对照人物为目标时，其他最佳候选减目标约+0.643875515。
- 指定同人为目标时，上述差值为负；指定新名字时，返回正确的相似候选。

这验证了真实特征接线及分数方向，不是新板测、新推理或真实场景误判率评估。
本轮没有上传/部署该模块到板卡，没有修改现役服务、登记接口、模型、位流或正式人员库。

证据目录：`D:/yzd/tmp/enrollment-compare-20261018/`。
其中`gallery-snapshot.json`仅含上述公开测试特征，`probe.json`为已有查询特征；
`new-name.json`、`wrong-target.json`、`correct-target.json`记录三种调用输出。
原始特征来源为`D:/yzd/tmp/face-history-20261018/history.sqlite`、`query-result.json`。

项目背景站本轮后台连接被拒绝，未读取最新内容；失败发生在身份验证前。
本记录按本轮实现/验证日期归档为2026-10-18。
