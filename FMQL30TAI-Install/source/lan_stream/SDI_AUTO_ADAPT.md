# SDI 自动适配需求与当前证据

**2026-10-14修正：下文“未导出状态”只对本项目拷贝的参考源码成立，不代表当前板上位流。**
用户仓库最新记录表明当前纯视频设计已用独立AXI写通道，把SDIS状态导出到
`/dev/udmabuf0`首4KiB；但没有NPU/AXI寄存器桥，现有SDK取帧入口不可用。
详见 `../docs/board-hardware-review-20261014.md`。自动适配应从实际加载位流的接口继续核对，
不能用本地旧参考的缺口当作当前板端事实。

目标：摄像头在板卡可接收的SDI范围内改变规格时，检测实际输入，自动配置采集，
把新尺寸/格式发送给同一网页；无需用户一直固定摄像头为1920×1080。
当前预览程序仍是配置驱动，**未实现自动检测或运行中换制式**。

## 已核对的源事实

- `case/rtl/sdi/k7_sdi_rxtx.v:347`：接收IP `rx_mode_en=3'b111`，接入SD/HD/3G
  三种模式，内部有`rx_t_family/rx_t_rate/rx_t_scan`与lock信号。
  源码配置不能替代这些模式的板端测试，也不证明6G/12G或任意像素格式支持。
- `case/rtl/sdi/rx_sdi.v:321`：family送给frame_convertor；顶层模块只导出
  cam_hs/cam_vs/cam_rgb/cam_clk/cam_data_en和LED，没有向PS导出这些制式状态。
- `case/rtl/sdi/frame_convertor.v:44`：按family选择1920/1280/720/2048行有效像素宽度；
  当前处理的是两路10bit Y/C数据转8bit分量，未知family默认1920，不可把默认值当检测成功。
- `rx_sdi.v:329`将锁定信号用作converter的clken，并未将SD接收节拍使能贯通；
  没有从源码或测试证明SD/隔行/3G Level B的整个后级转换都正确。
- `case/rtl/ai7030_edif_top.v:214`只连接这些像素输出。
  已检查frame_ctrl的AXI状态表，未发现可读取的SDI检测制式/真实输入宽高接口。
- `ps_app/vendor/include/pipeline/io/input/sdicamera.hpp` 构造需要camera_width/height，
  根据它们配置PS/PL采样、尺寸和搬运长度；不是从驱动查询实际video format的接口。
- 新网页按每个原子包的width/height/stride绘图，没有写死1080p；
  能显示320×180及1920×1080合成数据，属于网页测试，不是720p/隔行摄像头上板证明。

## 合理后续工程范围（未实现）

1. 将制式锁定、模式、family、rate、scan、Level A/B等状态及有效像素几何
   形成完整快照提供给PS，跨时钟同步与快照一致性需另验。
2. 明确支持列表，核对字段与帧、SD节拍、逐行/隔行及Level B到当前像素流水的转换。
   未知/失锁应拒绝取帧，不静默假设1080p。
3. PS在锁定且状态稳定时配置尺寸和缓冲；切换期间暂停取帧，确认DMA已停止，
   再释放旧缓冲并重建。现有SDK取消DMA能力尚未确认，不能直接free正在写的buffer。
4. 切换建立新stream_id，清除旧帧/模型结果；网页在新帧里读取新尺寸。
5. 对每个承诺支持的制式做信号源/板端验证，测带宽与CPU/DDR成本。

这可能涉及RTL、寄存器、PS适配器和新的位流，不是只改网页尺寸。
本轮没有为此修改RTL/生成位流/部署；用户会在首版代码完成后决定上板。
