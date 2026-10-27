"""Locate scalar Corosync keys without discarding comments or custom sections."""
import re

TOKEN=re.compile(r'#[^\n]*|"(?:[^"\\]|\\.)*"|[{}:]|[^\s{}:#]+')


def scalar(text,path,replacement=None,*,optional=False):
    tokens=[m for m in TOKEN.finditer(text) if not m.group().startswith('#')]
    stack=[];found=[];index=0
    while index<len(tokens):
        token=tokens[index].group()
        if token=='}':
            if not stack:raise ValueError('Unbalanced Corosync configuration')
            stack.pop();index+=1;continue
        if index+1<len(tokens) and tokens[index+1].group()=='{':
            stack.append(token);index+=2;continue
        if index+2<len(tokens) and tokens[index+1].group()==':':
            value=tokens[index+2]
            if value.group() in ('{','}',':'):raise ValueError('Invalid Corosync scalar')
            end=index+3
            while end<len(tokens) and tokens[end].start()==tokens[end-1].end() and tokens[end].group() not in ('{','}'):
                end+=1
            if tuple(stack)+(token,)==tuple(path):found.append((value.start(),tokens[end-1].end()))
            index=end;continue
        raise ValueError('Unsupported Corosync syntax; review its configuration')
    if stack:raise ValueError('Unbalanced Corosync configuration')
    if not found and optional:return None
    if len(found)!=1:raise ValueError('Expected exactly one '+'.'.join(path))
    start,end=found[0];current=text[start:end].strip('"')
    if replacement is None:return current
    if not re.fullmatch(r'[A-Za-z0-9_.:\-]+',replacement):raise ValueError('Invalid scalar replacement')
    return text[:start]+replacement+text[end:]
