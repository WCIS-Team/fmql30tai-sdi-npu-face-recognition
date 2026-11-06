# FMQL30TAI 视觉工程复现

> **仅适用于资源齐全的完整运行包。** 本 GitHub 公开版不包含下文的 `reference_release/` 模型/启动载荷或 `board/sdk/*.deb`，不能直接按此安装。根目录 [models/](../../models/README.md) 的三份原始权重不能直接代替板端 JSON/RAW。缺失资源、模型下载与版权边界见 [模型说明](../../docs/MODELS.md)；不要删去哈希校验来绕过缺文件错误。

**环境** FMQL30TAI 完整版、厂商 AArch64 Linux、iCraft/CustomOp 3.39.0；重新打包 BOOT 用 Vivado 2018.3、Procise 2025.1.1 temp 和 Python 3。

## 一、准备 BOOT

1. 使用 [reference_release/boot](reference_release/boot) 中配套的 `BOOT.bin`、`Image`、`fmqlmp-verify.dtb` 和 `uEnv.txt`。板卡需先有厂商 Linux 系统。
2. 关机后用读卡器备份 SD 卡的 FAT 启动分区，将这套启动文件放入该分区。装回 SD 卡、接好 SDI 摄像头，再上电启动。板上已经使用同一套文件时，直接进入下一节。

如果使用本包 DCP 恢复生成的 BOOT，先按 [总说明](../README.md) 完成恢复与 Procise 打包，再把 `build-restored/BOOT.bin` 上传到板端 `~/submission/BOOT.bin`。第三节生成安装目录时，在板端 `~/submission` 中改用：

```sh
python3 board/render_install.py --config board.json --out install-tree --boot-bin BOOT.bin
```

脚本将本次启动文件集中放在 `install-tree/boot/`，并为安装目录生成对应的 BOOT 校验配置。关机后将这个 `boot/` 中的配套文件复制到 SD 卡启动分区，再启动并安装本次 `rootfs/`。原始提交清单不需要手改；`boot-input.json` 只记录选用了哪些文件，不代表新硬件已经验收。安装后仍须完成第三节的功能验收。

## 二、准备 PS 程序

1. 板端运行用 `reference_release/` 中的配套文件。`app/` 放识别程序和网页，`identity/` 和 `pad/` 放模型，`recorder/` 放录像服务。
2. 需要重新编译时，在带 AArch64 工具链和配套 SDK 的构建环境中运行 CMake。`ps_app` 开启 `WCIS_BUILD_CAMERA_OWNER`，构建 `wcis_camera_owner`。`npu_photo` 构建 `wcis_face_cached`、`wcis_face_pl_retained` 和 `wcis_face_pad`。使用包内程序可直接进行第三节。 [采集工程](../ps_source/ps_app/CMakeLists.txt) · [模型后端工程](../ps_source/npu_photo/CMakeLists.txt)
3. 比特级复现边界：历史记录中 `npu_photo` 的三个程序（`wcis_face_cached`、`wcis_face_pl_retained`、`wcis_face_pad`）换路径重编 SHA256 不变；`wcis_camera_owner`（源码 `../ps_source/ps_app/src/wcis_camera_owner.cpp`）的二进制依赖源码绝对路径（GCC 默认以源文件路径派生 `-frandom-seed`），换路径重编功能等价但字节不同。板端服务用 SHA-256 校验 owner（systemd 单元里的 `--camera-owner-sha256`），重编替换后需重跑 `render_install.py` 渲染新单元。构建收据中的 `source_archive_sha256` 是源码归档包（tar.gz）哈希，不是 .cpp 哈希。重编后的五个 ELF 无需更新 `filelist.json`：`render_install.py` 对它们只做「存在且为 aarch64 ELF」检查（模型、boot 文件与 SDK deb 仍按清单哈希逐字节校验）。板端调试提示：photo 服务一次失败后会在 `wcis-face/hardware-review-required.json` 写入本 boot 隔离标记，不要直接删除当前启动的保护标记。capture_dma 故障的检查与正常重启步骤见提交根目录的网站访问指南。

## 三、上板运行

1. **上传运行文件。** 将 `board/`、`reference_release/` 和 `filelist.json` 放在板上 root 用户家目录的 `submission/` 下，也可以上传自行打包的 `submission` 目录，在板上 root 家目录解开。以下命令在板端 root 终端运行。

   ```sh
   cd ~/submission
   apt-get install python3 python3-numpy python3-opencv ffmpeg curl util-linux e2fsprogs procps ./board/sdk/*.deb
   lsblk -o NAME,SIZE,FSTYPE,UUID,MOUNTPOINT
   cp -n board/board.example.json board.json
   ```

2. **配置并安装。** 按 `lsblk` 的结果在 `board.json` 填本板的 SD 启动分区、ext4 eMMC 数据分区、挂载点及 UUID。在新装板执行下列命令，安装目录为 `/root/wcis-face`。

   ```sh
   set -e
   test ! -e /root/wcis-face
   python3 board/render_install.py --config board.json --out install-tree
   for unit in install-tree/rootfs/etc/systemd/system/*.service; do
     if systemctl cat "${unit##*/}" >/dev/null 2>&1; then
       echo "已有服务 ${unit##*/}，请走原工程的升级流程"
       exit 1
     fi
   done
   cp -a install-tree/rootfs/root/wcis-face /root/
   mkdir -p /root/wcis-camera-preview
   touch /root/live.disabled
   cp -a install-tree/rootfs/etc/systemd/system/*.service /etc/systemd/system/
   systemctl daemon-reload
   systemctl start wcis-face-storage.service
   ```

3. **启动识别。** 确认厂商演示进程已退出。如果 `lsblk` 显示 SD 的 FAT 启动分区已挂载，先确认它的挂载点（例如 `/root/bits`）并卸载该启动分区。识别服务启动时会重新只读挂载它做校验。导入空人员库后，查看健康状态和相机帧号。

   ```sh
   set -e
   mount_dir=$(python3 -c 'import json; print(json.load(open("board.json"))["data_mount"])')
   findmnt -rn -M "$mount_dir"
   test ! -e "$mount_dir/wcis-face"
   cp -a install-tree/data/wcis-face "$mount_dir/"
   systemctl start wcis-face-photo.service
   curl --fail http://127.0.0.1:8091/api/health
   curl --fail http://127.0.0.1:8091/api/camera/status
   ```

4. **验收。** 健康接口显示模型就绪且相机帧号持续增加后，执行 `systemctl start wcis-sdi-vpu-view.service wcis-face-recording.service`。在同一局域网的电脑浏览器打开 `http://板卡IP:8091/`，例如当前板卡为 `http://192.168.1.113:8091/`。登记一张测试人脸，再检查识别结果。`http://板卡IP:8092/` 用于实时预览，`http://板卡IP:8093/` 用于录像与回放。

   验收后启用开机启动：

   ```sh
   systemctl enable wcis-face-photo.service wcis-sdi-vpu-view.service wcis-face-recording.service
   ```

   获取 IP、访问地址和无画面排查见 [网站访问指南](../网站访问指南.md)。


FPGA 复现统一按 [总说明](../README.md) 使用原上板 DCP；本说明不提供从 FPGA 源码重新综合实现的流程。
