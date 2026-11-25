"""Candidate-only materials and bounded tools for the offline writing workflow.

No inference or external network. Software tool checks are not an OS sandbox.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from decimal import Decimal, localcontext
from fractions import Fraction

CASE_DIR = Path('tasks/workflow-drafts/offline-writing-v0.1')
TOOL_NAMES = ('list_documents','read_document','search_documents','calculate','write_note','read_note','submit_article')


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def regular_below(base: Path, relative: str) -> Path:
    if not isinstance(relative,str) or not relative or Path(relative).is_absolute() or any(p in ('..','.') for p in relative.split('/')):
        raise ValueError('Invalid candidate-relative path')
    base=base.resolve();p=base
    for part in relative.split('/'):
        p=p/part
        if p.is_symlink():raise ValueError('Symbolic links are not candidate artifacts')
    if not p.resolve().is_relative_to(base) or not p.is_file():raise ValueError('Candidate artifact is absent')
    return p


def candidate_bundle(root: Path, case_dir: Path=CASE_DIR) -> dict:
    """Read only declared candidate documents; never open a judge artifact."""
    root=root.resolve();base=(root/case_dir).resolve()
    if not base.is_relative_to(root):raise ValueError('Case escapes repository')
    case=json.loads((base/'material-case.draft.json').read_text())
    manifest=json.loads((base/'source-manifest.json').read_text())
    if case.get('case_id')!='workflow.draft.offline-writing.four-day-service' or manifest.get('synthetic') is not True:
        raise ValueError('Unexpected writing case identity')
    files={};documents=[];seen=set()
    for item in manifest['sources']:
        sid=item['source_id'];relative=item['path']
        if sid in seen or not relative.startswith('candidate/sources/'):
            raise ValueError('Invalid document manifest')
        seen.add(sid);p=regular_below(base,relative);raw=p.read_bytes()
        if digest(raw)!=item['sha256']:raise ValueError('Source hash drift')
        target=relative.removeprefix('candidate/');files[target]=raw.decode('utf-8')
        documents.append({'source_id':sid,'path':target,'title':item['title'],'status':item['status'],'sha256':item['sha256']})
    if seen!=set(case['source_ids']):raise ValueError('Document identities differ')
    for name in ('system.txt','brief.md','source-packet.md','INDEX.md'):
        files[name]=regular_below(base,'candidate/'+name).read_text()
    # Rebuild exactly, so appended hidden hints or duplicated sources fail too.
    packet=files['source-packet.md']
    expected=['# Quellenarchiv: Servicezentrum Mitte, Stand 01.10.2026','','Alle Einrichtungen, Personen, Daten, Zitate und Beträge sind für diesen Benchmarkentwurf erfunden. Die Unterlagen sind keine realen Studien oder Beobachtungen. Es folgen die vollständigen Quelldateien; sie sind nicht zu einer Argumentation vorverdichtet.','']
    for item in documents:
        expected+=['## ['+item['source_id']+'] '+item['title'],'','Datei: `'+item['path']+'`','',files[item['path']].rstrip(),'']
    if packet!='\n'.join(expected).strip()+'\n':raise ValueError('Common packet differs from raw sources')
    messages=[{'role':'system','content':files['system.txt']},{'role':'user','content':files['brief.md']+'\n\n'+packet}]
    return {'case_id':case['case_id'],'files':files,'documents':documents,'messages':messages,
            'sha256':{name:digest(text.encode()) for name,text in files.items()}}


def prepare_workspace(directory: Path,bundle: dict) -> dict:
    """Create a fresh candidate view; no repository, references or case controls."""
    directory=directory.resolve();directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    for relative,text in bundle['files'].items():
        path=directory/relative;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x') as out:out.write(text)
    (directory/'notes').mkdir();(directory/'output').mkdir()
    return {'workspace':str(directory),'documents':bundle['documents'],'sha256':bundle['sha256']}


def calculate(expression: str,values: dict) -> dict:
    if not isinstance(expression,str) or not 0<len(expression)<=256 or not isinstance(values,dict) or len(values)>16:
        raise ValueError('Invalid arithmetic input')
    if any(not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,31}',k) or type(v) is not int or abs(v)>10**12 for k,v in values.items()):
        raise ValueError('Arithmetic variables must be small named integers')
    tree=ast.parse(expression,mode='eval')
    if len(list(ast.walk(tree)))>100:raise ValueError('Arithmetic expression too large')
    def visit(n):
        if isinstance(n,ast.Constant) and type(n.value) is int and abs(n.value)<=10**12:return Fraction(n.value)
        if isinstance(n,ast.Name) and n.id in values:return Fraction(values[n.id])
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
            v=visit(n.operand);return -v if isinstance(n.op,ast.USub) else v
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a,b=visit(n.left),visit(n.right)
            if isinstance(n.op,ast.Add):return a+b
            if isinstance(n.op,ast.Sub):return a-b
            if isinstance(n.op,ast.Mult):return a*b
            return a/b
        raise ValueError('Only integer arithmetic and supplied variables are supported')
    result=visit(tree.body)
    if max(result.numerator.bit_length(),result.denominator.bit_length())>4096:raise ValueError('Arithmetic result too large')
    with localcontext() as ctx:
        ctx.prec=18;decimal=str(Decimal(result.numerator)/Decimal(result.denominator))
    return {'exact':str(result),'decimal':decimal,'inputs_supplied_by_candidate':True,
            'source_values_verified':False}


class ToolBackend:
    def __init__(self,view:dict,audit_path:Path,*,maximum_calls:int,deadline:float,
                 maximum_note_bytes:int=65536,maximum_total_note_bytes:int=262144,
                 maximum_article_bytes:int=131072):
        if type(maximum_calls) is not int or maximum_calls<1:raise ValueError('Explicit positive tool cap required')
        self.view=view;self.root=Path(view['workspace']).resolve();self.documents={d['source_id']:d for d in view['documents']}
        self.audit_path=audit_path;self.maximum_calls=maximum_calls;self.deadline=deadline
        self.maximum_note_bytes=maximum_note_bytes;self.maximum_total_note_bytes=maximum_total_note_bytes
        self.maximum_article_bytes=maximum_article_bytes;self.calls=0;self.failed_calls=0;self.submitted=False;self.delivery_kind=None
        self.lock=threading.RLock();self.notes={}
        for relative,sha in view['sha256'].items():
            if digest(regular_below(self.root,relative).read_bytes())!=sha:raise ValueError('Candidate view drift')

    @staticmethod
    def _keys(params,required=(),optional=()):
        if not isinstance(params,dict) or set(params)-set(required)-set(optional) or set(required)-set(params):
            raise ValueError('Invalid tool arguments')

    @staticmethod
    def _page(text,offset=0,max_chars=4096):
        if type(offset) is not int or not 0<=offset<=len(text) or type(max_chars) is not int or not 1<=max_chars<=4096:
            raise ValueError('Invalid text page')
        end=min(len(text),offset+max_chars)
        return {'text':text[offset:end],'offset':offset,'next_offset':end if end<len(text) else None,'complete':end==len(text),'total_characters':len(text)}

    def _document(self,sid):
        if sid not in self.documents:raise ValueError('Unknown source ID')
        item=self.documents[sid];p=regular_below(self.root,item['path']);raw=p.read_bytes()
        if digest(raw)!=item['sha256']:raise ValueError('Source hash drift')
        return raw.decode('utf-8')

    def _name(self,name):
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}\.md',name):raise ValueError('Invalid note name')
        return 'notes/'+name

    def _write(self,relative,text,*,exclusive):
        if not isinstance(text,str):raise ValueError('Text must be a string')
        parent=regular_below(self.root,'brief.md').parent/Path(relative).parent
        if parent.is_symlink() or parent.resolve()!=self.root/Path(relative).parent:raise ValueError('Invalid output directory')
        target=self.root/relative
        flags=os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|(os.O_EXCL if exclusive else 0)
        fd=os.open(target,flags,0o600)
        with os.fdopen(fd,'w') as out:
            if os.fstat(out.fileno()).st_nlink!=1:raise ValueError('Hard-linked output is forbidden')
            if not exclusive:
                current=regular_below(self.root,relative).read_text()
                if current!=self.notes[relative]:raise ValueError('Existing note changed outside tools')
                os.ftruncate(out.fileno(),0)
            out.write(text);out.flush();os.fsync(out.fileno())

    def execute(self,name,params):
        with self.lock:
            self.calls+=1;started=time.monotonic();record={'sequence':self.calls,'tool':name,'arguments':params,'started_monotonic':started}
            try:
                if self.submitted:raise ValueError('Final article already submitted')
                if started>=self.deadline:raise ValueError('Trial deadline exhausted')
                if self.calls>self.maximum_calls:raise ValueError('Tool-call budget exhausted')
                if name not in TOOL_NAMES:raise ValueError('Tool is not allowed')
                result=self._execute(name,params)
                record.update(ok=True,result=result);return result
            except Exception as exc:
                self.failed_calls+=1;record.update(ok=False,error_type=type(exc).__name__)
                # No private filenames or uncontrolled OS error strings reach the model.
                raise ValueError('Bounded tool request rejected') from exc
            finally:
                record['finished_monotonic']=time.monotonic();record['seconds']=record['finished_monotonic']-started
                with self.audit_path.open('a') as out:out.write(json.dumps(record,ensure_ascii=False)+'\n')

    def accept_final(self,text,*,kind):
        """Controller delivery is not a model tool attempt; preserve exact text."""
        with self.lock:
            if kind not in ('submit_article','assistant_final_text'):raise ValueError('Unknown delivery kind')
            if self.submitted or time.monotonic()>=self.deadline:raise ValueError('Final delivery closed')
            if not isinstance(text,str) or not text.strip() or len(text.encode())>self.maximum_article_bytes:raise ValueError('Invalid final article')
            self._write('output/article.md',text,exclusive=True);self.submitted=True;self.delivery_kind=kind
            return {'accepted':True,'delivery_kind':kind,'sha256':digest(text.encode()),'bytes':len(text.encode())}

    def _execute(self,name,p):
        if name=='list_documents':
            self._keys(p);return {'documents':list(self.documents.values())}
        if name=='read_document':
            self._keys(p,('source_id',),('offset','max_chars'))
            return {'source_id':p['source_id'],**self._page(self._document(p['source_id']),p.get('offset',0),p.get('max_chars',4096))}
        if name=='search_documents':
            self._keys(p,('query',),('source_id','offset','max_hits'))
            query=p['query'];offset=p.get('offset',0);cap=p.get('max_hits',20)
            if not isinstance(query,str) or not 1<=len(query)<=256 or type(offset) is not int or offset<0 or type(cap) is not int or not 1<=cap<=20:raise ValueError('Invalid literal search')
            ids=[p['source_id']] if 'source_id'in p else self.documents
            hits=[]
            for sid in ids:
                for line_no,line in enumerate(self._document(sid).splitlines(),1):
                    if query.casefold() in line.casefold():hits.append({'source_id':sid,'line':line_no,'excerpt':line[:300],'excerpt_complete':len(line)<=300})
            if offset>len(hits):raise ValueError('Search offset exceeds matches')
            end=min(len(hits),offset+cap)
            return {'hits':hits[offset:end],'total_matches':len(hits),'next_offset':end if end<len(hits) else None}
        if name=='calculate':
            self._keys(p,('expression',),('values',));return calculate(p['expression'],p.get('values',{}))
        if name=='write_note':
            self._keys(p,('name','text'));relative=self._name(p['name']);raw=p['text'].encode('utf-8')
            if len(raw)>self.maximum_note_bytes or sum(len(v.encode()) for k,v in self.notes.items() if k!=relative)+len(raw)>self.maximum_total_note_bytes:raise ValueError('Note storage budget exhausted')
            self._write(relative,p['text'],exclusive=relative not in self.notes);self.notes[relative]=p['text']
            return {'name':p['name'],'bytes':len(raw),'sha256':digest(raw)}
        if name=='read_note':
            self._keys(p,('name',),('offset','max_chars'));relative=self._name(p['name'])
            if relative not in self.notes:raise ValueError('Note not created in this trial')
            text=regular_below(self.root,relative).read_text()
            if text!=self.notes[relative]:raise ValueError('Note drift')
            return {'name':p['name'],**self._page(text,p.get('offset',0),p.get('max_chars',4096))}
        if name=='submit_article':
            self._keys(p,('article',));return self.accept_final(p['article'],kind='submit_article')
        raise ValueError('Unknown operation')
