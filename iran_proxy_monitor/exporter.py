"""Non-destructive local shortlists for Karing. Never modifies source subscription."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
from .models import Node
from .engine import check_core
from .settings import DATA_DIR
from .bpf import create_bpf, decode_bpf

OUT=DATA_DIR/'exports'
OUT.mkdir(parents=True,exist_ok=True)


def shortlist_config(nodes:list[Node]):
    # Karing's sing-box profile importer discovers proxy outbounds in this JSON.
    # A selector is included for generic sing-box users; no tun/system proxy is created.
    out=[]
    tags=[]
    for i,n in enumerate(nodes):
        tag=f'{i+1:02d} {n.name}'[:95]
        if tag in tags:tag=f'{tag} {n.id[:6]}'
        tags.append(tag)
        out.append(n.labeled_outbound(tag))
    out.append({'type':'selector','tag':'Best Selection','outbounds':tags,'default':tags[0]})
    return {'log':{'level':'warn'},'dns':{'servers':[{'type':'local','tag':'local'}],'final':'local'},
            'outbounds':out,'route':{'final':'Best Selection','default_domain_resolver':'local'}}


def android_profile_config(cfg: dict) -> dict:
    """The same proxy outbounds, plus an Android VPN TUN inbound.

    This does not change the desktop/Karing JSON profile. Android's VpnService
    handles tunnel creation; the selected node is chosen using the selector.
    """
    import copy
    mobile = copy.deepcopy(cfg)
    mobile['inbounds'] = [{
        'type': 'tun', 'tag': 'android-tun',
        'address': ['172.19.0.1/30'], 'auto_route': True,
    }]
    return mobile


def atomic_bytes(path: Path, content: bytes):
    fd,tmp=tempfile.mkstemp(prefix='export-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(content)
        try:os.chmod(tmp,0o600)
        except OSError:pass
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def atomic_text(path:Path,content:str):
    fd,tmp=tempfile.mkstemp(prefix='export-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(content)
        try:os.chmod(tmp,0o600)
        except OSError:pass
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def export_shortlist(nodes:list[Node],kind:str,binary:str,validate=True) -> dict:
    if not nodes:raise ValueError('Refusing empty export')
    if kind not in ('best-download-speed','best-ping','best-overall','best-reliable'):raise ValueError('Invalid shortlist')
    cfg=shortlist_config(nodes)
    if validate and not check_core(binary,cfg):
        raise RuntimeError('sing-box rejected shortlist; previous export left intact')
    cfgpath=OUT / f'{kind}-latest.json'
    # Sing-box Android's local .bpf profile is a binary wrapper around a full
    # config. One profile can contain the same N nodes and a selector. Do not
    # modify/remove a prior working BPF if mobile configuration is invalid.
    bpfpath = OUT / f'{kind}-latest.bpf'
    mobile = android_profile_config(cfg)
    if validate and not check_core(binary, mobile):
        raise RuntimeError('sing-box rejected Android TUN profile; previous BPF retained')
    bpfdata = create_bpf(kind.replace('-', ' ').title(), mobile)
    _, decoded = decode_bpf(bpfdata)
    if [o for o in decoded['outbounds'] if o['type'] != 'selector'] != [
            o for o in cfg['outbounds'] if o['type'] != 'selector']:
        raise RuntimeError('Android BPF outbound mismatch')
    # Check both profiles before writing any part of a new shortlist.
    atomic_text(cfgpath,json.dumps(cfg,ensure_ascii=False,indent=2))
    atomic_bytes(bpfpath, bpfdata)
    # A second, URI-list format works for entries originally supplied as share URIs.
    links=[n.source_text for n in nodes if n.source_kind=='link' and '://' in n.source_text]
    uripath=None
    if links:
        uripath=OUT/f'{kind}-share-links.txt'
        atomic_text(uripath,'\n'.join(links)+'\n')
    return {'json':str(cfgpath),'bpf':str(bpfpath),'links':str(uripath) if uripath else '',
            'nodes':len(nodes),'uri_count':len(links)}


def rebuild_android_bpf_from_saved_json(binary: str) -> dict[str, str]:
    """Convert previously validated shortlist JSONs without retesting nodes.

    Retains exactly the saved selected outbounds (not a new ranking). Each BPF
    is replaced only after its new Android config passes core validation.
    """
    result = {}
    for kind in ('best-download-speed','best-ping','best-overall','best-reliable'):
        source = OUT / f'{kind}-latest.json'
        if not source.is_file():
            continue
        cfg = json.loads(source.read_text('utf-8'))
        if not isinstance(cfg, dict) or not isinstance(cfg.get('outbounds'),list) or not cfg['outbounds']:
            raise ValueError('Saved shortlist has invalid outbounds')
        mobile = android_profile_config(cfg)
        if not check_core(binary, mobile):
            raise RuntimeError('sing-box rejected Android profile; previous BPF preserved')
        payload = create_bpf(kind.replace('-', ' ').title(), mobile)
        _,verified = decode_bpf(payload)
        if verified['outbounds'] != cfg['outbounds']:
            raise RuntimeError('Saved Android profile outbounds differ')
        path = OUT / f'{kind}-latest.bpf'
        atomic_bytes(path,payload)
        result[kind] = str(path)
    if not result:
        raise FileNotFoundError('No existing shortlist JSON files found. Run a completed cycle first.')
    return result



def export_all_working(nodes: list[Node], binary: str, validate=True) -> dict:
    """Export every HTTPS-passing node, including nodes without speed verification.

    TXT contains original share links wherever possible; for nodes imported
    from YAML/JSON, include a one-line outbound JSON record rather than
    inventing broken share URIs. Import JSON/BPF for complete machine profiles.
    """
    if not nodes:
        raise ValueError('Cannot export an empty working-node list')
    cfg=shortlist_config(nodes)
    mobile=android_profile_config(cfg)
    if validate and (not check_core(binary,cfg) or not check_core(binary,mobile)):
        raise RuntimeError('Working-node profile failed sing-box validation; previous files retained')
    bpf=create_bpf('All working HTTPS nodes',mobile)
    _,verified=decode_bpf(bpf)
    if verified.get('outbounds') != cfg['outbounds']:
        raise ValueError('Working-node BPF contents mismatch')
    text_lines=[]
    uri_count=0
    for n in nodes:
        if n.source_kind == 'link' and '://' in n.source_text:
            text_lines.append(n.source_text.strip());uri_count+=1
        else:
            text_lines.append(json.dumps({'outbounds':[n.outbound]},ensure_ascii=False,separators=(',',':')))
    base=OUT/'all-working-nodes-latest'
    atomic_text(base.with_suffix('.json'),json.dumps(cfg,ensure_ascii=False,indent=2))
    atomic_bytes(base.with_suffix('.bpf'),bpf)
    atomic_text(base.with_suffix('.txt'),'\n'.join(text_lines)+'\n')
    # A second text file is purely share URIs and thus importable by clients
    # that cannot understand the inline JSON used to represent YAML-only nodes.
    share_path=OUT/'all-working-nodes-share-links.txt'
    share_lines=[n.source_text.strip() for n in nodes if n.source_kind=='link' and '://' in n.source_text]
    if share_lines:
        atomic_text(share_path,'\n'.join(share_lines)+'\n')
    return {'json':str(base.with_suffix('.json')),'bpf':str(base.with_suffix('.bpf')),
            'txt':str(base.with_suffix('.txt')),'share_links':str(share_path) if share_lines else '',
            'nodes':len(nodes),'uri_count':uri_count}
