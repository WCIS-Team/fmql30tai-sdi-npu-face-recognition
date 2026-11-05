# 学校服务器构建准备（2026-10-13）

2026-10-14 已整理可直接复用的[学校服务器连接记录](学校服务器连接记录.md)。以下内容保留当时的排查过程；当前认证路径、连接命令和目录规则优先看该记录。

用户指定后续适合的编译任务使用学校 Windows 服务器。说明文件：
`C:/Users/anxianji/Downloads/Telegram Desktop/win无wsl交叉编译.md`。

## 已确认的连接信息

- 跳板：`user@192.168.1.102`，已实际登录。
- 目标：从跳板机转发到 `127.0.0.1:13401`；用户名 `YiZhidi`。
- 用户报告目标没有管理员权限、WSL 或 GPU；尚未登录目标独立核实。
- 提供的旧私钥路径不在本机。按用户选择生成新密钥，公钥 comment 为 `wcis-codex-20261013`，等待添加到目标账户的 `.ssh/authorized_keys`。
- 密码已用本机 Windows 用户 DPAPI 加密保存，长期记忆仅记录连接信息和凭据位置。
- 2026-10-13 后续检查：用户提供的 SSH ZIP 中，authorized_keys 与本机生成的公钥逐字匹配，没有 UTF-16 BOM。归档中的 id_ed25519_tunnel 与该公钥不同，不将隧道密钥当作学校登录密钥尝试。目标仍拒绝认证，未登录、未上传。
- 用户提供的实际服务进程启动参数为 `C:/Users/YiZhidi/sshserver/OpenSSH-Win64/sshd.exe -f C:/Users/YiZhidi/sshserver/sshd_config -E C:/Users/YiZhidi/sshserver/sshd.log`。该配置第 5 行明确指定 `AuthorizedKeysFile C:/Users/YiZhidi/sshserver/authorized_keys`，所以此前账号 `.ssh/authorized_keys` 中的公钥不在服务使用的路径。已请用户将同一公钥追加到正确文件；等待完成后实际验证认证，不把这条来源定位当作连接已经成功。

`scripts/school_connection.py` 可直接建立转发连接；密码与私钥不放进工程。

## 构建范围

文档中的 Arm GNU 10.3 工具链用于 aarch64 Linux C++ 交叉编译；它不证明服务器安装了 Vivado、JFM 或 Procise。

目标账户授权后，先检查 `D:/yzd/WCIS/crosswin` 的 kit、toolchain、板端库清单以及正在运行的任务。新项目使用独立目录，复用已有 kit，不调用会重建其源树/kit 的总脚本，也不跳过运行任务检查。

**用户新增目录约束：所有上传、解包、源码、构建输出、日志、临时文件均放在 `D:/yzd/tmp` 的本任务独立子目录。只读复用 D:/yzd 下现有工具链/kit；不在服务器用户目录、系统临时目录或其他工程目录散落文件。编译进程的 TMP/TEMP/TMPDIR 也定向到任务子目录。**

本次本机 Vivado 构建已经启动，保留其运行结果。板端原生编译占用了较多内存，已经仅终止本任务的临时编译进程；不再在板上编译。没有运行 NPU 应用、改启动文件或重启板子。

## 当前配套源码

`ps_app` 为厂商 SDI/YOLOv5/HDMI 程序的隔离副本。新增可选 `camera.vision_mode`（bypass、standby、active）；不配置时不写新增帧率寄存器。PS 抓帧与 ZG330 ImageMake 均允许 1500 ms 等待，后者改用单调时钟。

这是参考通路回归和帧率控制配套程序，尚未集成新的人脸模型。

## 后续已完成结果

用户把公钥追加到服务配置指定的 `C:/Users/YiZhidi/sshserver/authorized_keys` 后，实际认证成功。随后所有工程文件上传到 `D:/yzd/tmp/wcis-fpga-20261013-62670b32`，未改动共享 kit、其他源码或全局 PATH。

复用 Arm GNU 10.3.1、CMake 4.4.4、Ninja 1.13.2、SDK 3.39.0 和 UAPI；编译/链接成功。修复了原 SDK BufferManager 漏写 `<shared_mutex>` 头文件的构建问题，补丁只在本工程副本及可重复的 staging 脚本中。

新程序 4,671,984 B，SHA256 `ea8135622061745f67dacae1e9bc5a0d46f8c0b7c86735ae16bff3bb5c4bb46d`。实际板端依赖解析和 `--help` 均通过；不等同摄像头/NPU业务运行通过。更多环境及编译证据见 `school-server-tools.md`。
