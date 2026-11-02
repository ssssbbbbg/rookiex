#!/usr/bin/env python3
"""
build_sub.py —— 从 vless 原始链接直接生成 Clash 订阅。

不依赖 nodes.json，不猜字段。每条链接单独解析，缺什么补什么。
用法: python3 build_sub.py links.txt out_dir
"""
import json
import sys
import os
from urllib.parse import urlparse, parse_qs, unquote


def parse_vless(uri):
    u = urlparse(uri)
    if u.scheme != 'vless':
        return None
    q = {k: v[0] for k, v in parse_qs(u.query, keep_blank_values=True).items()}
    name = unquote(u.fragment) if u.fragment else f"{u.hostname}:{u.port}"
    name = name.rstrip(',').strip()

    security = q.get('security', '').lower()
    network = q.get('type', 'tcp').lower()

    p = {
        "name": name,
        "type": "vless",
        "server": u.hostname,
        "port": int(u.port or 443),
        "uuid": u.username,
        "network": network,
        "tls": security in ('tls', 'reality', 'xtls'),
        "udp": True,
    }

    # VLESS 必须显式 encryption: none
    p["encryption"] = q.get('encryption') or 'none'

    # SNI / servername
    sni = q.get('sni') or q.get('peer') or q.get('host')
    if sni:
        p["servername"] = sni

    # 流控
    if q.get('flow'):
        p["flow"] = q['flow']

    # REALITY
    if security == 'reality':
        p["reality-opts"] = {
            "public-key": q.get('pbk', ''),
            "short-id": q.get('sid', ''),
        }
        p["client-fingerprint"] = q.get('fp') or 'chrome'
        # REALITY 不要 skip-cert-verify，会干扰握手
    else:
        p["skip-cert-verify"] = True
        if q.get('fp'):
            p["client-fingerprint"] = q['fp']

    # WS
    if network == 'ws':
        opts = {"path": q.get('path') or '/'}
        if q.get('host'):
            opts["headers"] = {"Host": q['host']}
        p["ws-opts"] = opts
    elif network == 'grpc':
        p["grpc-opts"] = {"grpc-service-name": q.get('serviceName') or ''}
    elif network == 'h2':
        p["h2-opts"] = {"path": q.get('path') or '/', "host": [q.get('host')] if q.get('host') else []}

    return p


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else 'links.txt'
    outdir = sys.argv[2] if len(sys.argv) > 2 else '.'
    os.makedirs(outdir, exist_ok=True)

    raw = [l.strip() for l in open(src, encoding='utf-8') if l.strip()]
    proxies, seen = [], set()
    for uri in raw:
        p = parse_vless(uri)
        if not p:
            continue
        key = (p['server'], p['port'], p['uuid'], p.get('flow', ''),
               p.get('ws-opts', {}).get('path', ''))
        if key in seen:
            continue
        seen.add(key)
        proxies.append(p)

    names = [p['name'] for p in proxies]
    groups = [
        {"name": "PROXY", "type": "select",
         "proxies": ["自动选择", "故障转移"] + names},
        {"name": "自动选择", "type": "url-test", "proxies": names,
         "url": "http://www.gstatic.com/generate_204", "interval": 300, "tolerance": 50},
        {"name": "故障转移", "type": "fallback", "proxies": names,
         "url": "http://www.gstatic.com/generate_204", "interval": 300},
    ]

    out = [
        "# 菜鸟加速器节点 — rookiex 提取",
        f"# {len(proxies)} 条唯一节点",
        "",
        "mixed-port: 7890",
        "allow-lan: false",
        "mode: rule",
        "log-level: info",
        "external-controller: 127.0.0.1:9090",
        "",
        "proxies:",
    ]
    for p in proxies:
        out.append("  - " + json.dumps(p, ensure_ascii=False))
    out.append("")
    out.append("proxy-groups:")
    for g in groups:
        out.append("  - " + json.dumps(g, ensure_ascii=False))
    out += ["", "rules:", "  - MATCH,PROXY", ""]

    yaml_path = os.path.join(outdir, 'clash.yaml')
    open(yaml_path, 'w', encoding='utf-8').write("\n".join(out))

    print(f"生成 {len(proxies)} 条 -> {yaml_path}")
    for p in proxies:
        kind = 'REALITY' if 'reality-opts' in p else ('TLS-WS' if p['network'] == 'ws' else 'TLS')
        flow = p.get('flow', '-')
        print(f"  {p['name'][:26]:<28} {p['server']:<16}:{p['port']:<5} {kind:<8} flow={flow}")


if __name__ == '__main__':
    main()
