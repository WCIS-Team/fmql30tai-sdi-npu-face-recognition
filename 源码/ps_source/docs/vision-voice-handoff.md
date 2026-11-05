# 视觉与语音服务交接引导

适用于已安装本项目视觉服务的板卡。目标是让队友直接运行一个语音任务：先安全暂停视觉，语音任务结束后自动恢复视觉。**不需要本地记忆、以前聊天、Windows临时目录或学校服务器构建环境。** 工具只用板端Python标准库及systemd；不安装模型、不改BOOT或语音网关。

## 已安装板卡：日常操作

以下命令都在板卡root终端执行；非root用户需使用团队已有的sudo权限。板卡当前已安装，可先检查：

```sh
/usr/local/sbin/wcis-visionctl status
```

确认三个视觉服务正常，且不存在未处理的交接。将下面示例的 `your_voice_task.py` 替换为**你实际的前台语音程序**：

```sh
/usr/local/sbin/wcis-visionctl run --cwd /mnt/data/klar -- /usr/bin/python3 /mnt/data/klar/your_voice_task.py
```

这一条命令负责暂停、运行、恢复。语音程序应保持前台运行，完成后退出；不要加 `&`、`nohup` 或在程序内部转成守护进程。不要再另外执行三条视觉stop/start命令。需要特定Python环境时，把 `/usr/bin/python3` 换成该环境解释器的绝对路径；不要依赖登录终端里临时设置的环境变量。

程序的输出进入板端日志，不使用交互标准输入。新开终端查看：

```sh
journalctl -u wcis-vision-voice.service -b -f
```

SSH断开不会取消已经交给systemd管理的任务。需要主动结束本次任务并恢复视觉时：

```sh
/usr/local/sbin/wcis-visionctl stop
/usr/local/sbin/wcis-visionctl status
```

前台等待命令收到Ctrl+C也会请求停止本次任务。若希望立即返回终端，使用 `run --detach --cwd ... -- 程序 参数`；此时返回成功只表示已提交，最终结果必须看status中的事务状态。

**板上的 `klar-voice-gateway.service` 本来就常驻。** 不要重复启动第二份网关。可以把调用现有网关的一次测试脚本或完整语音工作会话包在run里；只在真实工作期间暂停视觉。由于恢复需要重新加载设备及模型，建议按一次工作会话交接，不要每句话都停启视觉。

## 没有安装时：从仓库交接

在队友电脑上获取本仓库 `WCIS-FPAI-repos` 的master分支，项目位于 `FPAI30TAI图像FPGA/`。如果从主库 `WCIS-FPAI` 获取，需同步repos子模块；本工具不需要初始化其他模型/语音子模块。

只需把这两个文件复制到板卡**同一个目录**：

- `FPAI30TAI图像FPGA/scripts/vision_handoff.py`
- `FPAI30TAI图像FPGA/scripts/install_vision_handoff.py`

使用团队既有SSH/SCP登录方式；若需要跳板则沿用跳板配置。仓库不包含密码、Cookie或SSH私钥。示例板端准备目录为 `/root/wcis-vision-handoff-install`，不要求队友有我们的Windows目录。

在板卡中执行：

```sh
cd /root/wcis-vision-handoff-install
python3 install_vision_handoff.py
python3 install_vision_handoff.py --check
/usr/local/sbin/wcis-visionctl status
```

安装器检查现有发布清单及三个服务；安装入口 `/usr/local/sbin/wcis-visionctl`、控制器 `/usr/local/lib/wcis-vision-handoff/vision_handoff.py`，给三个服务增加原生启动条件，并启用原服务的开机启动。**安装本身不停止或重启视觉owner。** `--check`只检查文件安装，运行健康另看status。

三个既有服务为：照片/模型 `wcis-face-photo.service`、预览 `wcis-sdi-vpu-view.service`、录像 `wcis-face-recording.service`。存储挂载服务不停止。首次安装后可用 `wcis-visionctl run -- /bin/sleep 2` 做不涉及真实语音模型的交接检查；这会真实暂停并恢复视觉，不能当作语音识别功能测试。

## 自动交接的具体行为

1. 读取板上当前发布配置、受管文件散列、当前boot/owner/session和原录像模式，不使用历史PID或固定候选版本。必须从三个健康且active的视觉服务开始。
2. 建立本次暂停条件，把录像设为off并等待当前段收尾，再停止录像、预览、照片服务。检查本次owner的 `sdk_closed=true`、`camera_pending=false`、`sessions_released=true`、exit0回执；旧owner/编码/封装进程必须退出，硬件锁必须空闲。
3. 条件满足才运行指定的语音程序。语音期间手动start/restart视觉会被systemd原生条件跳过，**systemctl返回0也不表示已启动**，应看ActiveState。再次执行run会被拒绝，不会叠加第二个交接。
4. 程序正常退出、非零退出、被stop或控制进程异常结束后，由systemd的ExecStopPost检查语音子进程已结束，再恢复照片/模型、预览和录像服务。等待同一新owner中的真实视频帧推进、模型就绪及录像源就绪，再恢复原先off/auto/manual模式。手动录像会开启新的段，暂停期间没有画面可录。
5. 硬件隔离、缺正常关闭回执、残留任务/硬件锁、配置中途变化或恢复失败时停止自动重试，保留blocked状态。不会清硬件隔离标记，也不会强杀相机/VPU。

本次任务由固定临时unit `wcis-vision-voice.service` 管理。暂停条件位于 `/run/wcis-vision-handoff/hold.json`，重启后按原开机准入流程恢复；不从旧boot重复使用关闭回执。关机过程中不强行重新启动视觉。开机启动已启用，本次没有做整板重启验收。

## 耗时及结果在哪里

```sh
/usr/local/sbin/wcis-visionctl status
cat /var/lib/wcis-vision-handoff/state.json
ls /var/lib/wcis-vision-handoff/runs
```

`transaction.phase=restored` 表示本次交接恢复完成。`voice_exit_code`保留程序退出码；语音报错不代表视觉一定没恢复，需同时看phase。SIGKILL场景可能没有语音退出码，仍检查最终phase。每次事务有独立token收据，不覆盖此前其他事务。

`timing`中的 `models_seconds`、`picture_seconds`、`restore_seconds` 分别从**恢复动作开始**计到模型就绪、视频源推进、全部服务/录像模式恢复。`pause_seconds`是暂停耗时。不要拿systemd显示的整个Service runtime当启动耗时，它还包含语音程序本身的运行时间。

11-03有限实测：正常结束后恢复动作约 **12.15秒**（从语音退出开始约 **12.95秒**），模拟交接控制进程SIGKILL后恢复动作约 **12.14秒**。此前一次修正后的手动恢复为19.59秒，耗时会受现场负载/缓存等影响；不是保证值，不是整板开机或浏览器首帧耗时。原始分项与验证范围见[本次实测](vision-voice-handoff-validation-20261103.md)。

## 出问题时按这个顺序处理

1. 先保存status和日志，不要重复run、删hold/state文件或强制启动视觉：

```sh
/usr/local/sbin/wcis-visionctl status
journalctl -u wcis-vision-voice.service -b --no-pager -n 100
journalctl -u wcis-face-photo.service -b --no-pager -n 80
```

2. 若任务仍运行，用 `wcis-visionctl stop` 请求正常结束。若监督unit已结束而事务仍未完成，可执行一次 `wcis-visionctl recover`；它仍执行相同安全检查，不会绕过blocked或当前boot隔离。
3. 若phase为blocked，查看error及该token的收据。硬件故障、缺关闭回执或配置变化需要现场复核，不能靠删除状态“解锁”。交接控制器不自动重启板卡；团队确认维护窗口后按原恢复规程处理。
4. 开机后若视觉仍未恢复，检查原服务、现役配置和boot准入；不要使用上一boot的PID/回执。工具只保证正常路径自动恢复，不把异常硬件重试变成循环。

需移除本工具时，先确认没有活动/未解决交接，再在安装文件目录运行 `python3 install_vision_handoff.py --uninstall`。它移除本工具拥有的启动条件和CLI入口，保留收据、库文件及既有服务开机启用状态供复核；不删除模型、人员库或录像。

## 实现与验证入口

[控制器](../scripts/vision_handoff.py)、[安装器](../scripts/install_vision_handoff.py)、[软件测试](../tests/test_vision_handoff.py)、[实板结果](vision-voice-handoff-validation-20261103.md)。

选用板上已有systemd的生命周期机制，依照[v245服务文档](https://github.com/systemd/systemd/blob/v245/man/systemd.service.xml)中ExecStopPost的异常退出清理契约；实际暂停条件以本板验证过的ConditionPathExists为准，不依赖仅在新版systemd存在的功能。
