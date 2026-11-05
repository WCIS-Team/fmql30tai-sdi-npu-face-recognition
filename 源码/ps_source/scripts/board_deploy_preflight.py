from ssh_transport import board_connection, ROOT
import json
checks={
'identity':'hostname; uname -a; uptime; free -m',
'processes':"ps -eo pid,comm,args | grep -E 'PLin|wcis|[y]olo|[p]ython|[a]udio|[i]craft'",
'reference':"find '/root/plin_demo/PLin+SingleNet+HDMI' -maxdepth 3 -type f -printf '%p %s bytes\\n' | head -100",
'storage':"findmnt -rn -o TARGET,SOURCE,FSTYPE,OPTIONS; cat /proc/cmdline; ls -la /boot; df -h /root /tmp",
'config_files':"find '/root/plin_demo/PLin+SingleNet+HDMI' -maxdepth 3 -type f \\( -iname '*.yaml' -o -iname '*.yml' \\) -print -exec cat {} \\;"
}
result={}
with board_connection() as client:
 for name,cmd in checks.items():
  _,out,err=client.exec_command(cmd,timeout=30)
  data=out.read().decode(errors='replace')+err.read().decode(errors='replace')
  code=out.channel.recv_exit_status()
  result[name]={'output':data,'exit_code':code}
  print(name+'\n'+data)
(ROOT/'outputs/ps_app/board_deploy_preflight.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
