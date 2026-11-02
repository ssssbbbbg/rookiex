#!/usr/bin/env python3
"""
rookiex_parse.py —— 把 RookieX 模块 dump 出来的文件转成可导入的节点清单。

用法:
    python3 rookiex_parse.py <dump目录> [-o out.yaml]

输入文件（任意存在即可）:
    node_uris.txt      XRayProxyClient.setCurrentProxyUri 抓到的链接
    proxies.list.txt   NodeConfig.getProxyList
    proxies.save.txt   NodeConfig.saveProxyList
    nodes.txt          Nodes.getNode
    mmkv_raw.txt       MMKV 裸串

输出:
    nodes.json         统一结构
    clash.yaml         Clash/Mihomo 可直接用
    share_links.txt    vmess/vless/trojan/ss 标准分享链接

不发起任何网络请求。
"""
import base64
import json
import os
import re
import sys
from urllib.parse import urlparse, parse_qs, unquote

SCHEMES = ("vmess://", "vless://", "trojan://", "ss://", "ssr://", "hysteria2://",
           "hy2://", "tuic://", "wireguard://", "socks://")

URI_RE = re.compile(r'(?:' + "|".join(re.escape(s) for s in SCHEMES) + r')[^\s"\'<>\\]+')


def b64d(s):
    s = s.strip().replace('-', '+').replace('_', '/')
    s += '=' * (-len(s) % 4)
    try:
        return base64.b64decode(s)
    except Exception:
        return b''


def safe_b64(s):
    s = s.strip().rstrip('#').rstrip(',')
    s = s.replace('-', '+').replace('_', '/')
    s += '=' * (-len(s) % 4)
    try:
        raw = base64.b64decode(s, validate=False)
        return raw.decode('utf-8', 'ignore')
    except Exception:
        return ''


def parse_vmess(uri):
    payload = uri[len("vmess://"):].split('#')[0]
    text = safe_b64(payload)
    if not text:
        return None
    try:
        j = json.loads(text[text.find('{'):text.rfind('}') + 1])
    except Exception:
        return None
    host = j.get('add') or j.get('host')
    if not host:
        return None
    return {
        "type": "vmess",
        "name": j.get('ps') or f"{host}:{j.get('port')}",
        "server": host,
        "port": int(j.get('port') or 443),
        "uuid": j.get('id'),
        "alterId": int(j.get('aid') or 0),
        "cipher": j.get('scy') or "auto",
        "network": j.get('net') or "tcp",
        "tls": bool(j.get('tls')),
        "servername": j.get('sni') or j.get('host') or '',
        "ws_path": j.get('path') or '/',
        "ws_host": j.get('host') or '',
        "raw": uri,
    }


def parse_url_scheme(uri):
    try:
        u = urlparse(uri)
    except Exception:
        return None
    scheme = u.scheme
    if scheme not in ("vless", "trojan", "hysteria2", "hy2", "tuic", "socks"):
        return None
    q = parse_qs(u.query)
    g = lambda k, d='': (q.get(k, [d]) or [d])[0]
    host = u.hostname
    if not host:
        return None
    name = unquote(u.fragment) if u.fragment else f"{host}:{u.port}"
    d = {
        "type": "hy2" if scheme in ("hysteria2", "hy2") else scheme,
        "name": name,
        "server": host,
        "port": u.port or 443,
        "network": g('type', 'tcp'),
        "tls": g('security', '') in ('tls', 'reality'),
        "servername": g('sni') or g('host') or '',
        "ws_path": g('path', '/'),
        "ws_host": g('host'),
        "flow": g('flow'),
        "pbk": g('pbk'),
        "sid": g('sid'),
        "fp": g('fp'),
        "raw": uri,
    }
    if scheme == "vless":
        d["uuid"] = u.username
    elif scheme == "trojan":
        d["password"] = u.username
    elif scheme in ("hysteria2", "hy2"):
        d["password"] = u.username
    return d


def parse_ss(uri):
    body = uri[len("ss://"):]
    name = ''
    if '#' in body:
        body, name = body.split('#', 1)
        name = unquote(name)
    body = body.split('?')[0]
    if '@' in body:
        head, tail = body.rsplit('@', 1)
        dec = safe_b64(head)
        if ':' in dec:
            method, pwd = dec.split(':', 1)
        elif ':' in head:
            method, pwd = head.split(':', 1)
        else:
            return None
        host, _, port = tail.rpartition(':')
    else:
        dec = safe_b64(body)
        if not dec or '@' not in dec:
            return None
        cred, _, hp = dec.rpartition('@')
        method, _, pwd = cred.partition(':')
        host, _, port = hp.rpartition(':')
    try:
        port = int(re.sub(r'\D', '', port) or 0)
    except Exception:
        return None
    return {
        "type": "ss", "name": name or f"{host}:{port}",
        "server": host, "port": port,
        "cipher": method, "password": pwd, "raw": uri,
    }


def to_clash(n):
    t = n["type"]
    if t == "vmess":
        o = {"name": n["name"], "type": "vmess", "server": n["server"], "port": n["port"],
             "uuid": n["uuid"], "alterId": n["alterId"], "cipher": n["cipher"],
             "network": n["network"], "tls": n["tls"],
             "servername": n["servername"], "skip-cert-verify": True}
        if n["network"] == "ws":
            o["ws-opts"] = {"path": n["ws_path"], "headers": {"Host": n["ws_host"]} if n["ws_host"] else {}}
        return o
    if t == "vless":
        o = {"name": n["name"], "type": "vless", "server": n["server"], "port": n["port"],
             "uuid": n["uuid"], "network": n["network"], "tls": n["tls"],
             "servername": n["servername"], "skip-cert-verify": True}
        if n.get("flow"):
            o["flow"] = n["flow"]
        if n.get("pbk"):
            o["reality-opts"] = {"public-key": n["pbk"], "short-id": n.get("sid", "")}
        if n.get("fp"):
            o["client-fingerprint"] = n["fp"]
        if n["network"] == "ws":
            o["ws-opts"] = {"path": n["ws_path"], "headers": {"Host": n["ws_host"]} if n["ws_host"] else {}}
        return o
    if t == "trojan":
        return {"name": n["name"], "type": "trojan", "server": n["server"], "port": n["port"],
                "password": n["password"], "sni": n["servername"], "skip-cert-verify": True}
    if t == "ss":
        return {"name": n["name"], "type": "ss", "server": n["server"], "port": n["port"],
                "cipher": n["cipher"], "password": n["password"]}
    if t == "hy2":
        return {"name": n["name"], "type": "hysteria2", "server": n["server"],
                "port": n["port"], "password": n["password"], "sni": n["servername"],
                "skip-cert-verify": True}
    return None


def collect(dump_dir):
    found, seen = [], set()
    files = ["node_uris.txt", "proxies.list.txt", "proxies.save.txt",
             "nodes.txt", "mmkv_raw.txt", "rookiex.log"]
    blobs = []
    for fn in files:
        p = os.path.join(dump_dir, fn)
        if os.path.exists(p):
            blobs.append(open(p, 'r', encoding='utf-8', errors='ignore').read())
    text = "\n".join(blobs)
    # 分享链接
    for m in URI_RE.finditer(text):
        uri = m.group(0)
        if uri in seen:
            continue
        seen.add(uri)
        low = uri.lower()
        n = None
        if low.startswith("vmess://"):
            n = parse_vmess(uri)
        elif low.startswith("ss://"):
            n = parse_ss(uri)
        elif low.startswith(("vless://", "trojan://", "hysteria2://", "hy2://", "tuic://")):
            n = parse_url_scheme(uri)
        if n:
            found.append(n)
    # 内嵌 JSON 的节点对象（Proxy.toString / Gson 输出）
    for m in re.finditer(r'\{[^{}]*"(?:url|address)"\s*:\s*"[^"]*"[^{}]*\}', text):
        try:
            j = json.loads(m.group(0))
        except Exception:
            continue
        url = j.get('url') or ''
        if not any(url.lower().startswith(s) for s in SCHEMES):
            # 只有 host/port 也能成一条 socks 记录
            if j.get('address') and j.get('port'):
                key = (j.get('address'), j.get('port'))
                if key in seen:
                    continue
                seen.add(key)
                found.append({"type": "addr", "name": j.get('name') or f"{key[0]}:{key[1]}",
                              "server": key[0], "port": int(key[1]),
                              "group": j.get('groupName'), "desc": j.get('desc'),
                              "raw": json.dumps(j, ensure_ascii=False)})
            continue
        if url in seen:
            continue
        seen.add(url)
        low = url.lower()
        if low.startswith("vmess://"):
            n = parse_vmess(url)
        elif low.startswith("ss://"):
            n = parse_ss(url)
        else:
            n = parse_url_scheme(url)
        if n:
            n["name"] = j.get('name') or n["name"]
            found.append(n)
    return found


def write_outputs(nodes, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "nodes.json"), 'w', encoding='utf-8') as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)

    links = [n["raw"] for n in nodes if n.get("raw", "").startswith(SCHEMES)]
    with open(os.path.join(out_dir, "share_links.txt"), 'w', encoding='utf-8') as f:
        f.write("\n".join(dict.fromkeys(links)))

    proxies = [p for p in (to_clash(n) for n in nodes) if p]
    lines = ["# 由 rookiex_parse.py 生成", "proxies:"]
    for p in proxies:
        lines.append("  - " + json.dumps(p, ensure_ascii=False))
    lines.append("")
    lines.append("proxy-groups:")
    lines.append("  - name: NODES")
    lines.append("    type: select")
    lines.append("    proxies: [" + ", ".join(p['name'] for p in proxies) + "]" if proxies else "    proxies: []")
    with open(os.path.join(out_dir, "clash.yaml"), 'w', encoding='utf-8') as f:
        f.write("\n".join(lines) + "\n")
    return len(proxies)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    dump = sys.argv[1]
    out = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "-o" else os.path.join(dump, "parsed")
    if not os.path.isdir(dump):
        print(f"目录不存在: {dump}")
        sys.exit(1)
    nodes = collect(dump)
    n = write_outputs(nodes, out)
    print(f"抓到 {len(nodes)} 条节点，其中 {n} 条可转 Clash")
    print(f"输出目录: {out}")
    if not nodes:
        print("没抓到。检查：App 是否登录过 / 是否连过一次节点 / 模块是否生效")


if __name__ == "__main__":
    main()
