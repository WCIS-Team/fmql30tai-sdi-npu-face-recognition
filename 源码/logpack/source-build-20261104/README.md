> 已被后续核对取代：本记录使用较早且功能不完整的源码，不能作为原上板功能复现证据。参见 ../source-reconcile-20261104/README.md。

# 从新建工程生成位流的验证

2026-11-04，使用交付包 fpga_source，新建 Vivado 2018.3 工程，器件 xc7z030ffg676-2。补入指定厂商 AI_Mate.edif，生成 BD 和 IP 输出，完成 24 个 IP 单独综合。随后加载本机已有配套 JFM_Kits，执行 add_hook_tcl_to_prj，启动 impl_1 至 write_bitstream，对应 GUI 的 Generate Bitstream。

顶层综合、布局、布线和位流写出全部完成，最终状态为 write_bitstream Complete!。92928 个可布线网络全部完成，路由错误为 0。生成 ai7030_edif_top.bit 与厂商钩子处理的 ai7030_edif_top_disable_icap.bit，大小和 SHA-256 见 verification.json。位流可重新生成，提交材料保留验证记录和原始日志。

新实现的建立时间最差裕量为 -0.497 ns，保持时间裕量为 +0.029 ns，脉宽裕量为 -0.409 ns。位流生成通过，时序尚未收敛。本次没有用新位流做板端验收。冻结发布版的历史报告及运行结果仍单独保留。

源码导入说明按官方教程第 2.3 节；第 2.5 节的 Generate Bitstream 自动执行综合、布局、布线和位流生成。
