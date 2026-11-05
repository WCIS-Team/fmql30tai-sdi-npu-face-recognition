# 板端运行证据（2026-11-04 实测，官方包 + 14 件补件部署）

## 采集时间: 2026-11-04T01:01:30+00:00
## 主机: U.FMSH  内核: 5.4.52

### BOOT 与设备
FAT 启动分区 BOOT.bin SHA-256（自产，应为 f6da96ab…）:
f6da96abbc0144ce5a48f4fa85aed6dab65067211b8932e8f4e4db87d5110297  /root/bits/BOOT.bin
e7edf0bc5eb31485962c9bfbefff60c250c9ec14363ccdd41a695173a127d3af  /root/bits/fmqlmp-verify.dtb

块设备与 eMMC:
NAME          SIZE FSTYPE UUID MOUNTPOINT
mtdblock0       4M             
mtdblock1      16M             
mmcblk0      58.4G             
|-mmcblk0p1     1G             
`-mmcblk0p2  26.1G             /
mmcblk1      29.1G             
`-mmcblk1p1  29.1G             /mnt/wcis-data
mmcblk1boot0    4M             
mmcblk1boot1    4M             

/dev/mmcblk1p1: LABEL="WCIS_FACE" UUID="67104a06-74a6-4268-a124-269d1b232a28" TYPE="ext4" PARTUUID="708d89b5-f488-854c-a9b7-3759b937bdf1"

rootfs 与出厂版本:
NAME="Ubuntu"
VERSION="20.04.4 LTS (Focal Fossa)"
ID=ubuntu

### 服务状态
--- wcis-face-storage ---
● wcis-face-storage.service - Verified vision data mount
     Loaded: loaded (/etc/systemd/system/wcis-face-storage.service; static; vendor preset: enabled)
     Active: active (exited) since Wed 2026-11-04 00:41:08 UTC; 20min ago
   Main PID: 454 (code=exited, status=0/SUCCESS)
     CGroup: /system.slice/wcis-face-storage.service

--- wcis-face-photo ---
● wcis-face-photo.service - Vision identity and PAD backend
     Loaded: loaded (/etc/systemd/system/wcis-face-photo.service; disabled; vendor preset: enabled)
     Active: active (running) since Wed 2026-11-04 00:55:02 UTC; 6min ago
    Process: 1074 ExecStartPre=/usr/bin/python3 /root/wcis-face/candidates/face-camera-ready-20261020/boot_prepare.py (code=exited, status=0/SUCCESS)
   Main PID: 1078 (python3)
     CGroup: /system.slice/wcis-face-photo.service
--- wcis-sdi-vpu-view ---
● wcis-sdi-vpu-view.service - Vision preview
     Loaded: loaded (/etc/systemd/system/wcis-sdi-vpu-view.service; disabled; vendor preset: enabled)
     Active: active (running) since Wed 2026-11-04 00:55:27 UTC; 6min ago
   Main PID: 1117 (python3)
     CGroup: /system.slice/wcis-sdi-vpu-view.service
             └─1117 /usr/bin/python3 /root/wcis-face/apps/vision-20261103/vpu_live_server.py --control /root/wcis-face/candidates/pad-owner-20261026/owner-current.json --host 0.0.0.0 --port 8092
--- wcis-face-recording ---
● wcis-face-recording.service - Vision MP4 recorder
     Loaded: loaded (/etc/systemd/system/wcis-face-recording.service; disabled; vendor preset: enabled)
     Active: active (running) since Wed 2026-11-04 00:55:27 UTC; 6min ago
   Main PID: 1118 (python3)
     CGroup: /system.slice/wcis-face-recording.service
             └─1118 /usr/bin/python3 /root/wcis-face/recorder/recording_service.py --control /root/wcis-face/candidates/pad-owner-20261026/owner-current.json --storage /mnt/wcis-data/wcis-face/recordings --mount /mnt/wcis-data --uuid 67104a06-74a6-4268-a124-269d1b232a28 --mode off --segment-seconds 60 --quota-mib 4096 --host 0.0.0.0 --backend http://127.0.0.1:8091

--- 端口 ---
LISTEN   0        5                0.0.0.0:8091          0.0.0.0:*              
LISTEN   0        5                0.0.0.0:8092          0.0.0.0:*              
LISTEN   0        5                0.0.0.0:8093          0.0.0.0:*              
### API 原始输出
GET /api/health
{"status": "ready", "backend": "zg330_npu_pl_and_host", "preprocessing_backend": "FAC1_customop_PL", "release": "/root/wcis-face/releases/20261014-b5a454c11d22", "frame_transport": "single_upload_retained_PL_DDR", "model_lifecycle": "single_owner_cached_sessions", "model_cache_ready": true, "npu_session_cache_enabled": true, "hardware_admission_ready": true, "validation_passed": true, "photo_input": true, "camera_input": true, "camera_input_mode": "single_owner_raw_sdi", "camera_capture_scheduler": "continuous", "camera_preview_transport": "PS_VPU_H264", "presentation_attack_detection": "same_frame_model_evidence", "pad_security_calibrated": false, "pad_face_limit": 4, "pad_result_scope": "per_face", "camera_request_policy": "share_inflight_only", "gallery_management": true, "gallery_storage": "emmc", "gallery_storage_ready": true, "gallery_storage_policy": "one_original_per_person", "boot_id": "b91311c6-a27e-4bca-a807-90cb3407e0b6"}

GET /api/camera/status
{"ready": true, "source": "camera", "state": "ready", "session": "i9zo0o_v", "boot_id": "b91311c6-a27e-4bca-a807-90cb3407e0b6", "camera_buffers": 2, "camera_drained": 0, "camera_mapping_verified": true, "camera_pending": true, "camera_requests": 11488, "capture_completion_observed_at": 2442.464309567, "capture_mode": "preallocated_ping_pong", "capture_scheduler": "independent_worker", "captured": 11487, "captured_at": 2442.430851671, "codec": "h264", "commands": 0, "encoded": 11490, "fps_limit": 30, "frame_id": 11491, "h264_bytes": 0, "h264_encoded_at": 2442.5984196773334, "h264_origin": 2057.597828646, "height": 540, "native_h264_encoding": false, "owner_protocol": 1, "pid": 1091, "preview_mode": "continuous_vpu", "raw_frames_submitted": 11485, "sdk_calls_on_capture_thread": false, "source_view": "full_view_960x540", "timestamp_basis": "capture_request_lower_bound", "updated_at": 2442.889923068, "vpu_enabled": true, "width": 960, "external_h264": true, "encoder_pid": 1085, "muxer_pid": 1086, "frame_age_s": 0.5074825216665886}

首页响应码:
  8091 -> 200
  8092 -> 200
  8093 -> 200
### 相机帧率连续采样（30 秒）
frame_id encoded 采样，每 5 秒一次，30 秒：
t= 0s  frame_id=11491 encoded=11490 captured=11487 fps_limit=30
t= 5s  frame_id=11641 encoded=11640 captured=11636 fps_limit=30
t=10s  frame_id=11791 encoded=11790 captured=11787 fps_limit=30
t=15s  frame_id=11941 encoded=11940 captured=11938 fps_limit=30
t=20s  frame_id=12091 encoded=12090 captured=12090 fps_limit=30
t=25s  frame_id=12241 encoded=12240 captured=12271 fps_limit=30
t=30s  frame_id=12391 encoded=12390 captured=12422 fps_limit=30
### 关键日志
--- wcis-face-photo 最近 40 行 ---
-- Logs begin at Thu 2023-03-02 12:58:02 UTC, end at Wed 2026-11-04 01:02:07 UTC. --
Nov 04 00:46:17 U.FMSH python3[773]: 127.0.0.1 - - [04/Nov/2026 00:46:17] "GET /api/camera/status HTTP/1.1" 200 -
Nov 04 00:46:17 U.FMSH python3[773]: 127.0.0.1 - - [04/Nov/2026 00:46:17] "GET / HTTP/1.1" 200 -
Nov 04 00:46:17 U.FMSH python3[773]: 127.0.0.1 - - [04/Nov/2026 00:46:17] "GET /api/health HTTP/1.1" 200 -
Nov 04 00:52:26 U.FMSH systemd[1]: Stopping Vision identity and PAD backend...
Nov 04 00:52:27 U.FMSH systemd[1]: wcis-face-photo.service: Succeeded.
Nov 04 00:52:27 U.FMSH systemd[1]: Stopped Vision identity and PAD backend.
Nov 04 00:52:29 U.FMSH systemd[1]: Starting Vision identity and PAD backend...
Nov 04 00:52:31 U.FMSH python3[994]: Boot-medium and app integrity passed; hardware function still requires acceptance
Nov 04 00:52:31 U.FMSH systemd[1]: Started Vision identity and PAD backend.
Nov 04 00:52:36 U.FMSH python3[998]: Traceback (most recent call last):
Nov 04 00:52:36 U.FMSH python3[998]:   File "/root/wcis-face/apps/vision-20261103/serve_photos.py", line 67, in <module>
Nov 04 00:52:36 U.FMSH python3[998]:     model_backend=CameraOwner(args.root,args.camera_owner_executable,args.camera_owner_sha256,Path(owner_workspace.name),seconds=0,fps=args.camera_owner_fps,native_inputs=args.camera_native_inputs,preview_mode='pl' if external_preview else 'vpu',pad_bundle=args.camera_pad_bundle)
Nov 04 00:52:36 U.FMSH python3[998]:   File "/root/wcis-face/apps/vision-20261103/camera_owner_runtime.py", line 115, in __init__
Nov 04 00:52:36 U.FMSH python3[998]:     self.guard()
Nov 04 00:52:36 U.FMSH python3[998]:   File "/root/wcis-face/apps/vision-20261103/camera_owner_runtime.py", line 122, in guard
Nov 04 00:52:36 U.FMSH python3[998]:     if self.admission.guard()!=self.boot:raise RuntimeError('Owner boot proof changed')
Nov 04 00:52:36 U.FMSH python3[998]:   File "/root/wcis-face/apps/vision-20261103/camera_interlock.py", line 33, in guard
Nov 04 00:52:36 U.FMSH python3[998]:     raise RuntimeError('Hardware review required; no automatic SDK reuse')
Nov 04 00:52:36 U.FMSH python3[998]: RuntimeError: Hardware review required; no automatic SDK reuse
Nov 04 00:52:36 U.FMSH systemd[1]: wcis-face-photo.service: Main process exited, code=exited, status=1/FAILURE
Nov 04 00:52:36 U.FMSH systemd[1]: wcis-face-photo.service: Failed with result 'exit-code'.
Nov 04 00:55:00 U.FMSH systemd[1]: Starting Vision identity and PAD backend...
Nov 04 00:55:02 U.FMSH python3[1074]: Boot-medium and app integrity passed; hardware function still requires acceptance
Nov 04 00:55:02 U.FMSH systemd[1]: Started Vision identity and PAD backend.
Nov 04 00:55:09 U.FMSH python3[1078]: Photo face service ready 0.0.0.0 8091
Nov 04 00:55:09 U.FMSH python3[1078]: H264 media: No fresh camera-backed H264 segment
Nov 04 00:55:10 U.FMSH python3[1078]: H264 media: ready
Nov 04 00:55:27 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 00:55:27] "GET /api/health HTTP/1.1" 200 -
Nov 04 00:55:30 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 00:55:30] "GET /api/camera/status HTTP/1.1" 200 -
Nov 04 00:55:36 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 00:55:36] "GET /api/camera/status HTTP/1.1" 200 -
Nov 04 01:01:36 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 01:01:36] "GET /api/health HTTP/1.1" 200 -
Nov 04 01:01:36 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 01:01:36] "GET /api/camera/status HTTP/1.1" 200 -
Nov 04 01:01:36 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 01:01:36] "GET / HTTP/1.1" 200 -
Nov 04 01:01:36 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 01:01:36] "GET /api/camera/status HTTP/1.1" 200 -
Nov 04 01:01:41 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 01:01:41] "GET /api/camera/status HTTP/1.1" 200 -
Nov 04 01:01:46 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 01:01:46] "GET /api/camera/status HTTP/1.1" 200 -
Nov 04 01:01:52 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 01:01:52] "GET /api/camera/status HTTP/1.1" 200 -
Nov 04 01:01:57 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 01:01:57] "GET /api/camera/status HTTP/1.1" 200 -
Nov 04 01:02:02 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 01:02:02] "GET /api/camera/status HTTP/1.1" 200 -
Nov 04 01:02:07 U.FMSH python3[1078]: 127.0.0.1 - - [04/Nov/2026 01:02:07] "GET /api/camera/status HTTP/1.1" 200 -

--- wcis-face-storage ---
-- Logs begin at Thu 2023-03-02 12:58:02 UTC, end at Wed 2026-11-04 01:02:07 UTC. --
Nov 04 00:41:08 U.FMSH systemd[1]: Starting Verified vision data mount...
Nov 04 00:41:08 U.FMSH python3[454]: Personnel eMMC filesystem mounted and verified
Nov 04 00:41:08 U.FMSH systemd[1]: Finished Verified vision data mount.

--- 本次开机的 DHCP 过程 ---
Nov 04 00:20:48 U.FMSH dhclient[155]: DHCPREQUEST for 192.168.1.113 on eth0 to 255.255.255.255 port 67 (xid=0x3c38f043)
Nov 04 00:20:51 U.FMSH dhclient[155]: DHCPREQUEST for 192.168.1.113 on eth0 to 255.255.255.255 port 67 (xid=0x3c38f043)
Nov 04 00:20:51 U.FMSH dhclient[155]: DHCPACK of 192.168.1.113 from 192.168.1.1 (xid=0x43f0383c)
Nov 04 00:20:52 U.FMSH dhclient[155]: Timeout too large reducing to: 2147483646 (TIME_MAX - 1)
Nov 04 00:20:52 U.FMSH dhclient[155]: bound to 192.168.1.113 -- renewal in 2147483647 seconds.
Nov 04 00:39:00 U.FMSH dhclient[247]: Killed old client process
Nov 04 00:39:01 U.FMSH dhclient[247]: DHCPRELEASE of 192.168.1.113 on eth0 to 192.168.1.1 port 67 (xid=0x137ac9eb)
Nov 04 00:39:01 U.FMSH dhclient[247]: send_packet: Network is unreachable
Nov 04 00:39:01 U.FMSH dhclient[247]: send_packet: please consult README file regarding broadcast address.
Nov 04 00:39:01 U.FMSH dhclient[247]: dhclient.c:3010: Failed to send 300 byte long packet over fallback interface.
Nov 04 00:39:01 U.FMSH dhclient[263]: DHCPDISCOVER on eth0 to 255.255.255.255 port 67 interval 3 (xid=0x403ffe30)
Nov 04 00:39:01 U.FMSH dhclient[263]: DHCPOFFER of 192.168.1.113 from 192.168.1.1

--- dmesg 中 NPU/eMMC/SDI 相关 ---
[    2.471058] mmc_host mmc1: card is non-removable.
[    2.485869] mmc_host mmc1: Bus speed (slot 0) = 100000000Hz (slot req 400000Hz, actual 400000HZ div = 125)
[    2.681035] mmc_host mmc1: Bus speed (slot 0) = 100000000Hz (slot req 25000000Hz, actual 25000000HZ div = 2)
[    2.693230] mmc1: new high speed MMC card at address 0001
[    2.703594] mmcblk1: mmc1:0001 Y2P032 29.1 GiB 
[    2.713444] mmcblk1boot0: mmc1:0001 Y2P032 partition 1 4.00 MiB
[    2.723665] mmcblk1boot1: mmc1:0001 Y2P032 partition 2 4.00 MiB
[    2.743856]  mmcblk1: p1
[ 1215.231490] EXT4-fs (mmcblk1p1): mounted filesystem with ordered data mode. Opts: errors=remount-ro
### 运行时目录快照
--- /root/wcis-face 顶层 ---
total 36
drwxr-xr-x  7 root root 4096 Nov  4 00:55 .
drwxr-xr-x 17 root root 4096 Nov  4 01:01 ..
drwxr-xr-x  3 root root 4096 Nov  4 00:52 apps
drwxr-xr-x  5 root root 4096 Nov  4 00:52 candidates
drwxr-xr-x  3 root root 4096 Nov  3 23:59 recorder
drwxr-xr-x  3 root root 4096 Nov  4 00:52 releases
drwxr-xr-x  2 root root 4096 Nov  4 00:52 tools
-rw-r--r--  1 root root 5921 Nov  4 00:55 video-stream-current.json
--- 服务单元实际内容（owner 校验值） ---
ExecStartPre=/usr/bin/python3 /root/wcis-face/candidates/face-camera-ready-20261020/boot_prepare.py
ExecStart=/usr/bin/python3 -u /root/wcis-face/apps/vision-20261103/serve_photos.py --root /root/wcis-face/releases/20261014-b5a454c11d22 --site /root/wcis-face/apps/vision-20261103/site --host 0.0.0.0 --port 8091 --pl-executable /root/wcis-face/apps/vision-20261103/wcis_face_pl_retained --npu-cache-executable /root/wcis-face/apps/vision-20261103/wcis_face_cached --gallery-store /mnt/wcis-data/wcis-face/galleries --gallery-mount /mnt/wcis-data --gallery-uuid 67104a06-74a6-4268-a124-269d1b232a28 --camera-owner-executable /root/wcis-face/apps/vision-20261103/wcis_camera_owner --camera-owner-sha256 cc47df41fe2d2911c6d49021d523d12b79640a2d0dcb86358ae370c7c2057813 --camera-owner-control /root/wcis-face/candidates/pad-owner-20261026/owner-current.json --camera-owner-fps 30 --camera-native-inputs --camera-pad-bundle /root/wcis-face/candidates/pad-20261018-7d22c90e30
--- 人员库（仅目录与计数，不导出内容） ---
/mnt/wcis-data/wcis-face/galleries
/mnt/wcis-data/wcis-face/galleries/a49114c2174ff0b1
/mnt/wcis-data/wcis-face/galleries/a49114c2174ff0b1/originals
1
