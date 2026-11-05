> 已被后续核对取代：本记录使用较早且功能不完整的源码，不能作为原上板功能复现证据。参见 ../source-reconcile-20261104/README.md。

# 新建工程导入验证

2026-11-04，使用 Vivado 2018.3 新建 xc7z030ffg676-2 空工程。源码从提交目录 fpga_source 复制到独立英文路径，补入厂商 AI_Mate.edif 后导入。未提供原 XPR、DCP 或综合实现缓存。

首次生成 BD 后，测试命令对全部 get_ips 重复生成嵌套 BD IP，收到必须由父设计生成的错误。随后改为由 BD 生成内部 IP，分别生成 13 个独立 XCI，最终日志包含 NEW_PROJECT_IMPORT_AND_GENERATION_PASSED。该调整只影响测试命令，交付教程按 Vivado GUI 操作。

BD 生成报告 gp0_monitor/gp1_monitor 关联接口提示和 AXI ID 位宽提示，日志保留。此次范围为源文件导入、输出生成和编译顺序检查，未执行 IP 综合、整片布局布线或板端验收。
