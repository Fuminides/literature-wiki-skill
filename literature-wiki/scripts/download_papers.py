#!/usr/bin/env python3
"""Download open-access copies of the papers listed in papers.csv.

Usage:
  python download_papers.py
  python download_papers.py --category 'Core'
  python download_papers.py --retry-failed

The script tries the curated direct URL first, then Semantic Scholar's public API
(openAccessPdf / arXiv identifier) as a fallback. It verifies the PDF magic bytes
before keeping the file. No paywall circumvention is attempted.
"""
import argparse, csv, difflib, json, os, re, sys, time
from pathlib import Path
from urllib.parse import quote
import urllib.request, urllib.error

HERE = Path(__file__).resolve().parent.parent
CSV = HERE / 'papers.csv'
OUT = HERE / 'pdfs'
REPORT = HERE / 'download_report.csv'
UA = 'Mozilla/5.0 (LiteratureWiki/1.0; academic-use)'
S2 = 'https://api.semanticscholar.org/graph/v1/paper/search'

def slug(s, n=110):
    s = s.replace('∂','d').replace('–','-').replace('—','-').replace('“','').replace('”','').replace('’',"'")
    s = re.sub(r'[^A-Za-z0-9._+ -]+','',s)
    s = re.sub(r'\s+','_',s.strip())
    return s[:n].rstrip('_')

def get(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent':UA, 'Accept':'application/pdf,*/*;q=0.8'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.geturl(), r.headers.get('Content-Type','')

def valid_pdf(data):
    return len(data) > 1000 and data[:1024].lstrip().startswith(b'%PDF')

def s2_candidate(title, year):
    fields='title,year,openAccessPdf,externalIds,url,venue'
    url = f'{S2}?query={quote(title)}&limit=5&fields={quote(fields)}'
    headers={'User-Agent':UA}
    key=os.environ.get('S2_API_KEY')
    if key: headers['x-api-key']=key
    req=urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            obj=json.loads(r.read().decode('utf-8'))
    except Exception:
        return None
    best=None; bestscore=-1
    for p in obj.get('data',[]):
        t=p.get('title') or ''
        score=difflib.SequenceMatcher(None,title.lower(),t.lower()).ratio()
        py=p.get('year')
        if py and year and abs(int(py)-int(year))<=1: score += 0.12
        if score>bestscore:
            bestscore=score; best=p
    if not best or bestscore < 0.73:
        return None
    oa=(best.get('openAccessPdf') or {}).get('url')
    if oa: return oa
    ar=(best.get('externalIds') or {}).get('ArXiv')
    if ar: return f'https://arxiv.org/pdf/{ar}'
    return None

def attempt(url):
    if not url: return None, None
    # normalize common arXiv abstract URLs if an API returns one
    url=url.replace('http://','https://')
    if 'arxiv.org/abs/' in url: url=url.replace('/abs/','/pdf/')
    try:
        data, final, ctype=get(url)
        if valid_pdf(data): return data, final
    except Exception:
        pass
    return None, None

def load_previous():
    if not REPORT.exists(): return {}
    with open(REPORT,encoding='utf-8') as f:
        return {r['index']:r for r in csv.DictReader(f)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--category', help='download only rows with this category')
    ap.add_argument('--retry-failed',action='store_true', help='skip PDFs already present and retry the rest')
    args=ap.parse_args()
    OUT.mkdir(exist_ok=True)
    with open(CSV,encoding='utf-8') as f: papers=list(csv.DictReader(f))
    if args.category: papers=[p for p in papers if p['category']==args.category]
    results=[]
    for k,p in enumerate(papers,1):
        idx=int(p['index']); title=p['title']; year=int(p['year'])
        filename=f'{idx:02d}_{year}_{slug(title)}.pdf'
        dest=OUT/filename
        if dest.exists() and valid_pdf(dest.read_bytes()[:2048]):
            print(f'[{k}/{len(papers)}] exists: {filename}')
            results.append([idx,title,'ok-existing',str(dest.relative_to(HERE)),''])
            continue
        print(f'[{k}/{len(papers)}] {title}')
        data, final = attempt(p['direct_pdf_url'].strip())
        source='curated-direct'
        if data is None:
            # Be gentle with the public endpoint.
            time.sleep(1.05)
            u=s2_candidate(title, year)
            data, final=attempt(u)
            source='semantic-scholar-oa'
        if data is not None:
            dest.write_bytes(data)
            print(f'  OK {len(data)/1024/1024:.2f} MB <- {final}')
            results.append([idx,title,'ok',str(dest.relative_to(HERE)),final or source])
        else:
            print('  MISSING - no downloadable OA PDF found automatically')
            results.append([idx,title,'missing','',''])
    with open(REPORT,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['index','title','status','file','source_url']); w.writerows(results)
    ok=sum(r[2].startswith('ok') for r in results)
    print(f'\nDone: {ok}/{len(results)} PDFs. See {REPORT.name} for details.')
    print('For missing papers, re-run later or add an open-access direct_pdf_url to papers.csv.')

if __name__=='__main__': main()
