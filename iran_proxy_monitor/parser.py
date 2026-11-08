"""Subscription parsers; unknown/unsupported features are reported, never erased silently."""
from __future__ import annotations
import base64
import json
import re
from collections import Counter
from urllib.parse import urlsplit, parse_qs, unquote
from dataclasses import dataclass, field
from ._vendor import yaml
from .models import Node

PROTOCOLS = {'vless','vmess','trojan','shadowsocks','hysteria2','tuic','socks','http'}

def b64decode(value: str) -> str:
    data = re.sub(r'\s+', '', value)
    return base64.urlsafe_b64decode((data + '=' * (-len(data)%4)).encode('ascii')).decode('utf-8-sig')

def qs(url):
    return {k.lower():v[-1] for k,v in parse_qs(url.query, keep_blank_values=True).items()}

def on(v): return str(v).lower() in ('1','true','yes','on')

def integer(v, label):
    n = int(v)
    if not 1 <= n <= 65535: raise ValueError(f'invalid {label}')
    return n

def host_port(split):
    if not split.hostname: raise ValueError('missing server')
    return split.hostname, integer(split.port or 443, 'port')

def tls_settings(name='', insecure=False, fp='', alpn=None, reality=None):
    result = {'enabled':True}
    if name: result['server_name'] = str(name)
    if insecure: result['insecure'] = True
    if alpn:
        if isinstance(alpn,str): alpn = alpn.split(',')
        result['alpn'] = [str(x).strip() for x in alpn if str(x).strip()]
    if fp: result['utls'] = {'enabled':True,'fingerprint':str(fp)}
    if reality: result['reality'] = {'enabled':True,'public_key':reality[0], 'short_id':reality[1]}
    return result

def transport(kind, path='', host='', service='', headers=None, early=0, ed_header=''):
    kind = str(kind or 'tcp').lower()
    if kind in ('tcp','none',''): return None
    if kind in ('websocket','ws'):
        t = {'type':'ws','path':path or '/'}
        h = dict(headers or {})
        if host: h['Host'] = str(host)
        if h: t['headers'] = h
        if early: t['max_early_data'] = int(early)
        if ed_header: t['early_data_header_name'] = ed_header
        return t
    if kind in ('grpc',): return {'type':'grpc', 'service_name':service or path or ''}
    if kind in ('httpupgrade','http-upgrade'):
        t = {'type':'httpupgrade','path':path or '/'}
        if host: t['host'] = str(host)
        if headers: t['headers'] = dict(headers)
        return t
    if kind in ('http','h2'):
        t = {'type':'http','path':path or '/'}
        if host: t['host'] = [str(host)]
        if headers: t['headers'] = dict(headers)
        return t
    if kind == 'quic': return {'type':'quic'}
    raise ValueError(f'unsupported transport: {kind}')

def link_node(line: str) -> Node:
    protocol = line.split(':',1)[0].lower()
    if protocol == 'hy2': protocol = 'hysteria2'
    if protocol == 'ss': protocol = 'shadowsocks'
    if protocol == 'socks5': protocol = 'socks'
    if protocol == 'https': protocol = 'http'
    if protocol not in PROTOCOLS: raise ValueError(f'unsupported link scheme: {protocol}')
    issues = []
    if protocol == 'vmess':
        body = line.split('://',1)[1].split('#',1)[0].split('?',1)[0]
        obj = json.loads(b64decode(body))
        name = str(obj.get('ps') or 'VMess')
        outbound = {'type':'vmess','server':obj.get('add',''),'server_port':integer(obj.get('port',443),'port'),
                    'uuid':obj.get('id',''),'security':obj.get('scy') or 'auto','alter_id':int(obj.get('aid') or 0)}
        if not outbound['server'] or not outbound['uuid']: issues.append('missing server/uuid')
        if str(obj.get('tls','')).lower() in ('tls','1','true'):
            outbound['tls'] = tls_settings(obj.get('sni') or obj.get('host') or obj.get('add'),
                                           fp=obj.get('fp',''), alpn=obj.get('alpn'))
        try:
            t=transport(obj.get('net'),obj.get('path',''),obj.get('host',''),obj.get('path',''))
            if t: outbound['transport']=t
        except ValueError as e: issues.append(str(e))
        return Node(name,protocol,outbound,'link',line,issues,locals().get('warnings',[]))
    s = urlsplit(line)
    name = unquote(s.fragment or protocol.upper())
    server, port = host_port(s)
    q = qs(s)
    outbound = {'type':protocol,'server':server,'server_port':port}
    if protocol == 'vless':
        outbound['uuid'] = unquote(s.username or '')
        if not outbound['uuid']: issues.append('missing UUID')
        encryption=q.get('encryption','none')
        if encryption not in ('none',''): issues.append('unsupported VLESS encryption')
        if q.get('flow'): outbound['flow'] = q['flow']
        security=q.get('security','none').lower()
        if security in ('tls','reality'):
            reality = (q.get('pbk',''),q.get('sid','')) if security=='reality' else None
            if security=='reality' and not q.get('pbk'): issues.append('REALITY public key missing')
            outbound['tls']=tls_settings(q.get('sni',''),on(q.get('allowinsecure','')),
                                        q.get('fp',''),q.get('alpn'),reality)
        elif security not in ('none',''):
            issues.append(f'unsupported security: {security}')
        try:
            t=transport(q.get('type','tcp'),q.get('path',''),q.get('host',''),q.get('servicename',''),
                        early=q.get('ed','0') or 0,ed_header=q.get('eh',''))
            if t: outbound['transport']=t
        except (ValueError,TypeError) as e: issues.append(str(e))
        for k in ('packetencoding',):
            if q.get(k): outbound['packet_encoding']=q[k]
        # spiderX is an Xray crawler hint, not a sing-box outbound setting. Preserve URI, warn.
        warnings=['spx (Xray spiderX hint not reproduced in sing-box)'] if q.get('spx') else []
        unknown=set(q)-{'encryption','flow','security','pbk','sid','sni','allowinsecure','fp','alpn','type','path','host','servicename','ed','eh','packetencoding','spx'}
        if unknown: issues.append('unmapped URI options: '+','.join(sorted(unknown)))
    elif protocol == 'trojan':
        outbound['password']=unquote(s.username or '')
        if not outbound['password']: issues.append('missing password')
        outbound['tls']=tls_settings(q.get('sni') or q.get('peer') or server, on(q.get('allowinsecure','')),q.get('fp',''),q.get('alpn'))
        try:
            t=transport(q.get('type','tcp'),q.get('path',''),q.get('host',''),q.get('servicename',''))
            if t: outbound['transport']=t
        except ValueError as e: issues.append(str(e))
        unknown=set(q)-{'sni','peer','allowinsecure','fp','alpn','type','path','host','servicename'}
        if unknown: issues.append('unmapped URI options: '+','.join(sorted(unknown)))
    elif protocol == 'shadowsocks':
        # SIP002: ss://base64(method:password)@host:port, legacy full payload, or plain method:pass@host
        split = line.split('://',1)[1].split('#',1)[0].split('?',1)[0]
        if '@' not in split:
            decoded=b64decode(split)
            cred, at, address=decoded.rpartition('@')
            if not at: raise ValueError('invalid legacy shadowsocks URI')
            s=urlsplit('ss://'+cred+'@'+address);server,port=host_port(s)
            auth=cred
        else:
            auth=split.rsplit('@',1)[0]
            if ':' not in auth:
                auth=b64decode(auth)
            else:
                auth=unquote(auth)
        if ':' not in auth: raise ValueError('Shadowsocks credentials missing')
        method,password=auth.split(':',1)
        outbound.update({'method':method,'password':password})
        if q.get('plugin'):
            plugin=unquote(q['plugin'])
            name_part,_,opts=plugin.partition(';')
            if name_part not in ('obfs-local','v2ray-plugin'): issues.append('unsupported plugin')
            else: outbound.update({'plugin':name_part,'plugin_opts':opts})
        unknown=set(q)-{'plugin'}
        if unknown: issues.append('unmapped URI options: '+','.join(sorted(unknown)))
    elif protocol == 'hysteria2':
        outbound['password'] = unquote(s.username or '')
        if not outbound['password']: issues.append('missing password')
        outbound['tls'] = tls_settings(q.get('sni') or server,on(q.get('insecure','')),q.get('fp',''),q.get('alpn'))
        if q.get('obfs'):
            if q['obfs']!='salamander': issues.append('unsupported hysteria2 obfs type')
            else: outbound['obfs']={'type':'salamander','password':q.get('obfs-password','')}
        if q.get('upmbps'): outbound['up_mbps']=int(q['upmbps'])
        if q.get('downmbps'): outbound['down_mbps']=int(q['downmbps'])
        unknown=set(q)-{'sni','insecure','fp','alpn','obfs','obfs-password','upmbps','downmbps'}
        if unknown: issues.append('unmapped URI options: '+','.join(sorted(unknown)))
    elif protocol == 'tuic':
        outbound['uuid']=unquote(s.username or '')
        outbound['password']=unquote(s.password or '')
        if not outbound['uuid'] or not outbound['password']: issues.append('TUIC credentials missing')
        outbound['tls']=tls_settings(q.get('sni') or server,on(q.get('allow_insecure','')),q.get('fp',''),q.get('alpn'))
        if q.get('congestion_control'): outbound['congestion_control']=q['congestion_control']
        if q.get('udp_relay_mode'): outbound['udp_relay_mode']=q['udp_relay_mode']
        unknown=set(q)-{'sni','allow_insecure','fp','alpn','congestion_control','udp_relay_mode'}
        if unknown: issues.append('unmapped URI options: '+','.join(sorted(unknown)))
    elif protocol in ('socks','http'):
        if s.username: outbound['username']=unquote(s.username)
        if s.password: outbound['password']=unquote(s.password)
        if protocol == 'socks': outbound['version']='5'
        if line.startswith('https://'):outbound['tls']={'enabled':True}
        if q: issues.append('unmapped proxy options')
    return Node(name,protocol,outbound,'link',line,issues,locals().get('warnings',[]))

def clash_node(p: dict) -> Node:
    ptype = str(p.get('type','')).lower()
    protocol = {'ss':'shadowsocks','socks5':'socks','hy2':'hysteria2'}.get(ptype,ptype)
    name = str(p.get('name') or protocol)
    problems = []
    if protocol not in PROTOCOLS:
        return Node(name, protocol, {}, 'clash', json.dumps(p,ensure_ascii=False),['unsupported Clash protocol'])
    o={'type':protocol,'server':str(p.get('server','')), 'server_port':integer(p.get('port',0),'port')}
    direct_fields = {
      'vless':{'uuid':'uuid','flow':'flow'},
      'vmess':{'uuid':'uuid','cipher':'security','alterId':'alter_id'},
      'trojan':{'password':'password'},
      'shadowsocks':{'cipher':'method','password':'password','plugin':'plugin'},
      'hysteria2':{'password':'password','up':'up_mbps','down':'down_mbps'},
      'tuic':{'uuid':'uuid','password':'password','congestion-controller':'congestion_control','udp-relay-mode':'udp_relay_mode'},
      'socks':{'username':'username','password':'password'},
      'http':{'username':'username','password':'password'},
    }
    for a,b in direct_fields.get(protocol,{}).items():
        if p.get(a) is not None:o[b]=p[a]
    if protocol=='socks':o['version']='5'
    if protocol=='vmess':
        o.setdefault('security','auto');o.setdefault('alter_id',0)
    if protocol=='shadowsocks' and p.get('plugin-opts'):
        opts=p['plugin-opts']
        if o.get('plugin') in ('obfs','obfs-local'):
            o['plugin']='obfs-local'
            o['plugin_opts']=';'.join(f'{k}={v}' for k,v in opts.items()) if isinstance(opts,dict) else str(opts)
        elif o.get('plugin')=='v2ray-plugin':
            o['plugin_opts']=';'.join(f'{k}={v}' for k,v in opts.items()) if isinstance(opts,dict) else str(opts)
        else:problems.append('unsupported Shadowsocks plugin')
    if protocol=='hysteria2' and p.get('obfs'):
        if p['obfs']!='salamander':problems.append('unsupported hy2 obfs')
        else:o['obfs']={'type':'salamander','password':p.get('obfs-password','')}
    tls_enabled=on(p.get('tls',False)) or protocol in ('trojan','hysteria2','tuic') or p.get('reality-opts') or p.get('client-fingerprint') and protocol=='vless'
    if tls_enabled:
        r=p.get('reality-opts')
        reality=(r.get('public-key',''),r.get('short-id','')) if isinstance(r,dict) else None
        if reality and not reality[0]:problems.append('REALITY key missing')
        o['tls']=tls_settings(p.get('servername') or p.get('sni') or p.get('server',''),
                              on(p.get('skip-cert-verify',False)),p.get('client-fingerprint',''),p.get('alpn'),reality)
    if protocol in ('vless','vmess','trojan'):
        typ=p.get('network','tcp')
        opts=p.get('ws-opts',{}) or {}
        if typ == 'grpc':opts=p.get('grpc-opts',{}) or {}
        if typ in ('httpupgrade','http-upgrade'):opts=p.get('httpupgrade-opts',{}) or {}
        if typ in ('http','h2'):opts=p.get('http-opts',{}) or {}
        try:
            t=transport(typ,opts.get('path',''),opts.get('headers',{}).get('Host','') if isinstance(opts.get('headers'),dict) else '',
                        opts.get('grpc-service-name','') or opts.get('serviceName',''),opts.get('headers'))
            if t:o['transport']=t
        except ValueError as e:problems.append(str(e))
    # Explicit allowlist: unknown params should not disappear when testing/exporting.
    known={'type','name','server','port','uuid','password','flow','cipher','alterId','tls',
           'servername','sni','skip-cert-verify','client-fingerprint','alpn','reality-opts',
           'network','ws-opts','grpc-opts','httpupgrade-opts','http-opts',
           'plugin','plugin-opts','obfs','obfs-password','up','down','username',
           'congestion-controller','udp-relay-mode','udp','tfo','interface-name','ip-version'}
    extra=set(p)-known
    if extra:problems.append('unmapped Clash options: '+','.join(sorted(map(str,extra))))
    for key in ('interface-name',):
        if p.get(key):problems.append(f'{key} affects routing and is not mapped')
    return Node(name,protocol,o,'clash',json.dumps(p,ensure_ascii=False),problems)

def singbox_node(o: dict) -> Node:
    protocol=o.get('type','')
    name=o.get('tag',protocol)
    if protocol not in PROTOCOLS:
        return Node(str(name),str(protocol),{},'sing-box',json.dumps(o,ensure_ascii=False), ['unsupported sing-box outbound'])
    known={'type','tag','server','server_port','uuid','password','flow','network','tls','transport',
           'method','plugin','plugin_opts','udp_over_tcp','security','alter_id','packet_encoding',
           'multiplex','up_mbps','down_mbps','obfs','server_ports','hop_interval',
           'congestion_control','udp_relay_mode','zero_rtt_handshake','heartbeat',
           'username','version','path','headers','domain_resolver','detour','bind_interface',
           'routing_mark','tcp_fast_open','tcp_multi_path','udp_fragment','connect_timeout',
           'tls_fragment','tls_record_fragment','ip_version','domain_strategy','fallback_delay'}
    extra=set(o)-known
    problems=['unmapped sing-box fields: '+','.join(sorted(extra))] if extra else []
    outbound={k:v for k,v in o.items() if k!='tag'}
    return Node(str(name),str(protocol),outbound,'sing-box',json.dumps(o,ensure_ascii=False),problems)

def xray_node(entry:dict) -> Node:
    """Limited Xray JSON: one remote endpoint/user per outbound; unhandled fields are fatal."""
    protocol=str(entry.get('protocol','')).lower()
    if protocol=='ss':protocol='shadowsocks'
    name=str(entry.get('tag') or protocol)
    raw=json.dumps(entry,ensure_ascii=False)
    if protocol not in PROTOCOLS:return Node(name,protocol,{},'xray',raw,['unsupported Xray protocol'])
    settings=entry.get('settings',{}) or {}
    stream=entry.get('streamSettings',{}) or {}
    issues=[]
    if protocol in ('vless','vmess'):
        upstream=settings.get('vnext') or []
        if len(upstream)!=1 or len(upstream[0].get('users',[]))!=1:
            return Node(name,protocol,{},'xray',raw,['Xray multi-server/multi-user outbound unsupported'])
        server=upstream[0];user=server['users'][0]
        o={'type':protocol,'server':server.get('address'),'server_port':integer(server.get('port'),'port'),
           'uuid':user.get('id','')}
        if protocol=='vless':
            if user.get('flow'):o['flow']=user['flow']
        else:
            o['security']=user.get('security','auto')
            o['alter_id']=int(user.get('alterId',0))
    elif protocol in ('trojan','shadowsocks'):
        upstream=settings.get('servers') or []
        if len(upstream)!=1:
            return Node(name,protocol,{},'xray',raw,['Xray multi-server outbound unsupported'])
        server=upstream[0]
        o={'type':protocol,'server':server.get('address'),'server_port':integer(server.get('port'),'port'),
           'password':server.get('password','')}
        if protocol=='shadowsocks':o['method']=server.get('method','')
    else:
        return Node(name,protocol,{},'xray',raw,['Xray conversion unimplemented for protocol'])
    sec=stream.get('security','none')
    if sec in ('tls','reality'):
        t=stream.get('tlsSettings',{}) if sec=='tls' else stream.get('realitySettings',{})
        reality=(t.get('publicKey',''),t.get('shortId','')) if sec=='reality' else None
        o['tls']=tls_settings(t.get('serverName',''),t.get('allowInsecure',False),t.get('fingerprint',''),t.get('alpn'),reality)
    elif sec not in ('none',''):issues.append('unmapped Xray security')
    typ=stream.get('network','tcp')
    opts={'ws':stream.get('wsSettings',{}),'grpc':stream.get('grpcSettings',{}),
          'httpupgrade':stream.get('httpupgradeSettings',{}),'http':stream.get('httpSettings',{})}.get(typ,{}) or {}
    try:
        t=transport(typ,opts.get('path',''),opts.get('host',''),opts.get('serviceName',''),opts.get('headers'),
                    opts.get('maxEarlyData',0),opts.get('earlyDataHeaderName',''))
        if t:o['transport']=t
    except ValueError as e:issues.append(str(e))
    top_extra=set(entry)-{'protocol','tag','settings','streamSettings'}
    if top_extra:issues.append('unmapped Xray top-level fields: '+','.join(sorted(top_extra)))
    opts_extra=set(stream)-{'network','security','tlsSettings','realitySettings','wsSettings','grpcSettings','httpupgradeSettings','httpSettings'}
    if opts_extra:issues.append('unmapped Xray stream fields: '+','.join(sorted(opts_extra)))
    return Node(name,protocol,o,'xray',raw,issues)


@dataclass
class ParseReport:
    nodes: list[Node] = field(default_factory=list)
    total: int = 0
    duplicates: int = 0
    unsupported: int = 0
    format: str = ''
    errors: Counter = field(default_factory=Counter)

    @property
    def usable(self):return sum(n.supported for n in self.nodes)


def parse_subscription(content: bytes | str, _depth: int=0) -> ParseReport:
    if isinstance(content,bytes): content=content.decode('utf-8-sig',errors='replace')
    if len(content) > 25_000_000: raise ValueError('Subscription exceeds 25 MB safety limit')
    r=ParseReport()
    raw=content.strip()
    if not raw:raise ValueError('Empty subscription')
    if re.match(r'(?is)^\s*(?:<!doctype\s+html|<html\b|<head\b|<body\b)',raw):
        raise ValueError('Subscription returned an HTML page, not a node list; check the link, login, or client format')
    doc=None
    if raw[:1] in '[{':
        try:doc=json.loads(raw)
        except json.JSONDecodeError:pass
    if doc is None and (re.search(r'^\s*(?:proxies|outbounds|nodes|data|links)\s*:',raw,re.M)):
        try:doc=yaml.safe_load(raw)
        except yaml.YAMLError:pass
    if doc is None and (re.search(r'^\s*proxies\s*:',raw,re.M) or re.search(r'^\s*outbounds\s*:',raw,re.M)):
        try:doc=yaml.safe_load(raw)
        except yaml.YAMLError:pass
    # Some panels wrap proxy lists in `data`, `result` or `payload` or return
    # JSON lists of share strings. Unwrap ONLY recognized shapes, up to 2 levels.
    if isinstance(doc,dict) and _depth<2:
        for key in ('data','result','payload','config','links','nodes'):
            inner=doc.get(key)
            if isinstance(inner,(dict,list)) or (isinstance(inner,str) and '://' in inner):
                try:
                    nested=parse_subscription(json.dumps(inner) if isinstance(inner,(dict,list)) else inner,_depth+1)
                    if nested.usable>0:return nested
                except ValueError:pass
    raw_items=[]
    if isinstance(doc,dict) and isinstance(doc.get('proxies'),list):
        r.format='Clash YAML/JSON';raw_items=[('clash',p) for p in doc['proxies']]
    elif isinstance(doc,dict) and isinstance(doc.get('outbounds'),list):
        r.format='sing-box / Xray JSON';raw_items=[('xray' if isinstance(p,dict) and 'protocol' in p else 'sing-box',p) for p in doc['outbounds']]
    elif isinstance(doc,dict) and isinstance(doc.get('proxy'),list):
        r.format='Xray JSON (unrecognized proxy key)';raw_items=[('unsupported',p) for p in doc['proxy']]
    elif isinstance(doc,list):
        r.format='JSON list';raw_items=[('link' if isinstance(p,str) else 'sing-box',p) for p in doc]
    elif isinstance(doc,dict):
        r.format='Unrecognized JSON';raw_items=[('unsupported',doc)]
    else:
        if not re.search(r'\b(?:vless|vmess|trojan|ss|hy2|hysteria2|tuic|socks5?|https?)://',raw,flags=re.I):
            try:
                decoded=b64decode(raw)
                if '://' in decoded:raw=decoded
            except (ValueError,UnicodeError):pass
        r.format='URI list / Base64'
        raw_items=[('link',line.strip()) for line in raw.splitlines() if line.strip() and not line.lstrip().startswith('#')]
        if len(raw_items)==1 and raw_items[0][1].count('://')>1:
            raw_items=[('link',item.strip()) for item in re.split(r'(?=(?:vless|vmess|trojan|ss|hy2|hysteria2|tuic)://)',raw_items[0][1]) if '://' in item]
    seen=set()
    for kind,item in raw_items:
        r.total+=1
        try:
            if kind=='link': n=link_node(item)
            elif kind=='clash': n=clash_node(item)
            elif kind=='sing-box': n=singbox_node(item)
            elif kind=='xray': n=xray_node(item)
            else: n=Node('Unsupported','unknown',{},'unknown',str(item),['unsupported subscription item'])
        except (ValueError,TypeError,KeyError,OverflowError,UnicodeError,AttributeError) as e:
            # Keep a minimal record and redact any authentication token in report.
            n=Node('Parse error','unknown',{},kind,str(item),['invalid configuration data'])
            r.errors[type(e).__name__]+=1
        if n.id in seen:
            r.duplicates+=1
            continue
        seen.add(n.id)
        if not n.supported:
            r.unsupported+=1
            for p in n.problems:r.errors[p.split(':',1)[0]]+=1
        r.nodes.append(n)
    return r
