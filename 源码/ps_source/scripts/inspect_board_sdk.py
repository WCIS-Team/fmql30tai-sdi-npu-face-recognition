from ssh_transport import board_connection, ROOT
with board_connection() as client:
    cmd = "g++ --version | head -1; cmake --version | head -1; ls -l /usr/include/icraft*; ls /ModelzooDeps/aarch64/Static; cat /root/plin_demo/PLin+SingleNet+HDMI/CMakeLists.txt; ps -eo pid,comm,args | grep -E 'icraft|yolo|audio|speaker|vscode' | head -30"
    _, out, err = client.exec_command(cmd, timeout=15)
    result = out.read().decode(errors='replace') + err.read().decode(errors='replace')
    (ROOT / 'outputs/board_sdk_inspect.txt').write_text(result, encoding='utf-8')
    print(result[:14000])
