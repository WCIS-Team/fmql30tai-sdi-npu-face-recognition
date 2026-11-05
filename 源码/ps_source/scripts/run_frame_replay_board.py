"""Start bounded board DDR replay without uploading an image per request."""
import argparse
from pathlib import Path
import shlex
import sys
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames',type=int,default=30)
    parser.add_argument('--period-ms',type=int,default=0)
    parser.add_argument('--seed',choices=('face-bgrx','face-rgb565','no-face','two-faces'),default='face-bgrx')
    args=parser.parse_args()
    if not 1<=args.frames<=300 or not 0<=args.period_ms<=5000:
        parser.error('Use 1..300 iterations and a period of 0..5000 ms')
    sys.stdout.reconfigure(encoding='utf-8')
    out=Path('D:/yzd/tmp')/('face-replay-run-'+uuid.uuid4().hex[:8]);out.mkdir()
    sys.pycache_prefix=str(out/'pycache')
    from ssh_transport import board_connection
    command=shlex.join(['python3','-u','/root/wcis-face/run-replay.py','--frames',str(args.frames),
                        '--period-ms',str(args.period_ms),'--seed',args.seed])
    with board_connection() as client:
        stdin,stdout,stderr=client.exec_command(command,get_pty=True)
        stdout.channel.set_combine_stderr(True)
        with (out/'replay.log').open('w',encoding='utf-8') as log:
            while True:
                try:
                    line=stdout.readline()
                    if not line:break
                    print(line.rstrip(),flush=True);log.write(line);log.flush()
                except KeyboardInterrupt:
                    # PTY VINTR reaches the board launcher and child, whose
                    # handlers drain the in-flight frame and restore service.
                    stdin.write('\x03');stdin.flush()
                    print('正在结束当前帧并恢复服务，请稍候。',flush=True)
        code=stdout.channel.recv_exit_status()
    print('运行记录：'+str(out/'replay.log'))
    return code


if __name__=='__main__':
    raise SystemExit(main())
