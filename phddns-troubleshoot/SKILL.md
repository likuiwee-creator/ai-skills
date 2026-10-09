---
name: phddns-troubleshoot
description: 花生壳(Oray/HSKDDNS) 内网穿透掉线、映射访问不通的排查与根治。当用户说"花生壳掉线""花生壳连不上""穿透域名打不开""hskddns 离线""vicp.fun 访问不了""内网穿透又断了"时使用。覆盖日志定位、keepalive 超时、自动升级打断、DNS 卡解析、映射目标未启动等常见根因。
agent_created: true
---

# 花生壳（HskDDNS）掉线排查

花生壳 6.x 的进程名**不是** `phddns.exe`，别找错：

| 进程 | 作用 |
|---|---|
| `HskDDNS.exe` | 主程序 / GUI（WebView2 外壳），跑在 Console 会话 |
| `HskDDNSMaint.exe` | 守护进程（两个实例：GUI 侧 + 服务侧），被 kill 后负责拉起 phtunnel |
| `orayfilesvr.exe` | 花生壳文件服务 |
| `phtunnel.exe` | **隧道内核**，真正干活的，掉线多半是它 |

## Step 1：定位路径

```
安装目录:  D:\Oray\HskDDNS\            （默认 C:\Program Files (x86)\Oray\HskDDNS）
配置:      D:\Oray\HskDDNS\phtunnel.json   ← 映射目标在这里
日志目录:  %LOCALAPPDATA%\HskDDNS\log\   ← 关键！不在安装目录里
  interface.YYYYMMDD-HHMMSS.log  主程序（token / RPC / 离线图标切换）
  phtunnel.log / phtunnel.YYYYMMDD-HHMMSS.log  隧道内核（login / online / map / upgrade）
  orayfilesvr.*.log              文件服务
```

> 日志被进程占用时 PowerShell `[IO.File]::ReadAllBytes` 会报 "being used by another process"，用 Python `io.open(path, encoding="utf-8", errors="replace")` 共享读即可。
> 编码：进度 `interface` 日志是 UTF-8；`tasklist` 输出是 GBK。

## Step 2：判类型（先看这三类日志）

```bash
# 掉线/保活/升级/登录事件
grep -E "keepalive|ORAY_ERROR|level0_offline|device status|upgrade|\[login\]|\[online\]" \
  "%LOCALAPPDATA%\HskDDNS\log\phtunnel.log" "%LOCALAPPDATA%\HskDDNS\log\interface"*.log
```

| 日志特征 | 含义 |
|---|---|
| `ORAY_ERROR_PHSTREAM_KEEPALIVE_TIMEOUT` + `X:443 disconnect by keepalive timeout` | 被动保活长连接被中间设备掐断（公司防火墙/NAT 空闲超时） |
| `[main] phtunnel upgrade try, ver: 1.x.x.x` | 隧道内核在自我升级/换二进制，此节点必然断流 |
| `[ora] device status 3(0:offline,1:online,2:logging,3:retry)` | 设备状态 3=retry |
| `SetUserTypePic ... level0_offline.png` | 客户端图标切到"离线" |
| 日志**长时间零增长**（进程在、无心跳） | 隧道内核**假死**，守护进程没发现（没退出码） |

## Step 3：验证"假死 vs 崩溃"

```powershell
taskkill /PID <phtunnelPID> /F   # 看守护 5 秒内是否拉起新实例
Get-Process phtunnel,HskDDNS,HskDDNSMaint,orayfilesvr | Select Id,ProcessName,StartTime
```

- 能自动拉起新实例 → 是**卡死**（需要治根因，重启只是续命）
- 拉不起来 → 二进制/权限/端口被占用问题

## Step 4：逐个排查根因（按命中率排序）

1. **自动升级打断**：`phtunnel upgrade try` 每 2 小时一次（免费版典型），每次都断流。
   处理：客户端"设置 → 高级 → 升级"关掉，或装固定版本不让它自动更新。
2. **keepalive 被掐**：`... timeout(xxx >= yyy + 30000)` / `+3000` 说明链路中间设备对 443 长连接空闲清理极快。
   处理：关"海外节点"（`phtunnel.json` 里 `oversea:true` → false）走国内 oray 节点；换 TCP 直连模式（`networkmode`）；加防火墙/杀软白名单。
3. **DNS 卡解析**：主 DNS 服务器不可达时 `getaddrinfo` 长时间阻塞 → 主线程卡死（日志刷 `get socket info ipv4 check failed, err = 11001`，11001 = WSAHOST_NOT_FOUND）。
   验证：Python 裸 UDP 53 探测各 DNS（绕过系统缓存）+ `nslookup` 看是否全 timed out。
   处理：主 DNS 换 `223.5.5.5` + `119.29.29.29`（域控环境可能被推回，需确认）。
4. **映射目标端口错**：`phtunnel.json` 里 `"forward":"127.0.0.1:80"` 但服务实际在 `8766` → 域名 TCP 能连上但零数据。
   验证：`netstat -ano -p tcp | findstr LISTENING` + 影子日志看实际转到的端口。
   **改法**：先备份 `phtunnel.json.bak`，**先改配置再 kill phtunnel**（守护会自动重拉，否则它用旧配置重启覆盖回去）。
   ⚠️ 守护/客户端重启时可能把 `forward` 写回旧值 —— **要真正持久化必须改花生壳客户端 GUI 的映射设置**，json 只是 phtunnel 启动时的读源。
5. **免费版限制**：vicp.fun 免费版本就限流/定时掉线，长期要稳就付费，或换 cpolar / frp / Cloudflare Tunnel。

## Step 4.5：映射"打不开"的假象（最容易误判，务必先读）

**花生壳映射有类型（HTTP / HTTPS / TCP）。类型=HTTPS 时，用明文 HTTP 打 443/80 一定是"连上即关、零字节"，看起来像掉线，实际链路是好的。**

判定顺序（按此顺序，别跳过）：

1. **先看影子日志的权威映射行**（每次启动都会打）：
   ```
   [maps] 我的映射, via: phfwba-pro-g7.oray.net(), hh1214778pb3.vicp.fun:443(127.0.0.1:8766)
   ```
   格式：`公网域名:公网端口(内网IP:内网端口)`。这行是 phtunnel 自己认定的映射，比 json 可靠。

2. **用 TLS 握手判链路死活**（不是发 HTTP）：
   ```python
   s=socket.create_connection(('映射域名',443),12)
   ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
   ss=ctx.wrap_socket(s, server_hostname='映射域名')   # 握手成功=链路活着（subject 可能 None）
   ```
   握手成功但明文 HTTP 返回 0 字节 → **映射是 HTTPS 类型**，用 https 测：
   `https://hh1214778pb3.vicp.fun/` → 200 + 后端页面即正常。

3. **别用 urllib 测**（本机 502 假象）：Windows 下 `urllib.request.getproxies()` 读的是**注册表代理设置**，不是环境变量。
   公司系统代理会把请求发到网关，网关返回 **502 Bad Gateway** —— 看起来像隧道坏，其实是代理拦的。
   要么 `urllib.request.urlopen(url, context=ctx)` 后比对，要么直接用裸 socket/TLS 手打请求。

4. **区分"隧道没送到本机"还是"服务不兼容"**：临时起一个最小 echo 服务（监听 9099，收到连接就回 `HELLO-9099`），把 `forward` 指过去，观察 echo 日志有没有新连接：
   - echo 有连接 → 隧道链路 OK，问题在你自己的服务；
   - echo 零连接但 `[maps]` 显示 8766 → json 的 `forward` 被客户端覆盖了，改 GUI；
   - 两者都零 → 隧道/中继真的断了，回到 Step 2。

> 实测结论：本机 8766（`Server: BaseHTTP/0.6 Python/3.12.0`）本地 0.2s 返回 1041010 字节；映射改指 8766 后 `https://hh1214778pb3.vicp.fun:443/` 返回 200 前端 HTML —— 说明**隧道是好的，之前打不开纯粹是类型/端口错 + 用错协议测**。

## Step 5：交付结论

按「已完成 / 卡在哪 / 下一步」结构给结论，并明确区分两类问题：
- **掉线本身**（隧道层）
- **映射打不开**（应用层，跟掉线无关，容易误判）

## 常用命令

```bash
# 进程
tasklist /FO CSV | findstr /i "phtunnel hskddns orayfile"
powershell "Get-Process phtunnel,HskDDNS | Select Id,ProcessName,StartTime | Format-Table -AutoSize | Out-String"

# 监听（确认映射目标活着）
netstat -ano -p tcp | findstr LISTENING

# 穿透实测（从本机连映射域名，看是否返回数据）
python -c "import socket;s=socket.create_connection(('映射域名',443),8);s.sendall(b'GET / HTTP/1.1\r\nHost: 映射域名\r\nConnection: close\r\n\r\n');print(s.recv(512))"
```

## 环境坑（本机）

- Bash 缺 coreutils（无 mkdir/ls/head/sleep），长管道会被截断
- Python 用 managed 版 `C:\Users\Administrator\.workbuddy\binaries\python\versions\3.13.12\python.exe`
- `Get-ChildItem -Recurse` 扫 `C:\Program Files` 极慢会超时，别乱扫
- PowerShell 输出必须 `| Out-String` 才会返回 stdout；`if(...)'a' else 'b'` 要写成 `if (...) { 'a' } else { 'b' }`
- PowerShell 里 `Format-Table` 的 `X` 后缀是 Out-String 换行造成的，不是真的字符
