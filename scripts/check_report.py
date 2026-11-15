"""Рендер DOCX, сверка/обновление кеша TOC, экспорт всех страниц для просмотра."""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from lxml import etree
from docx import Document
import pymupdf
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parent.parent
DOC=ROOT/'docs/Отчет_Шустов_ЗН251.docx';OUT=ROOT/'tmp/report-render';OUT.mkdir(parents=True,exist_ok=True)
PDF=OUT/(DOC.stem+'.pdf')


def render():
    result=subprocess.run(['libreoffice','-env:UserInstallation=file:///tmp/stroymarket-lo-report',
        '--headless','--convert-to','pdf','--outdir',str(OUT),str(DOC)],capture_output=True,text=True,check=True)
    (OUT/'convert.log').write_text(result.stdout+result.stderr)
    return pymupdf.open(PDF)


def norm(text):
    return re.sub(r'\s+','',text.replace('\u00ad',''))


def pages_for(pdf,doc):
    pages=[norm(x.get_text()) for x in pdf]
    mapping={}
    for p in doc.paragraphs:
        if p.style.name not in ['Heading 1','Heading 2']:continue
        hits=[i+1 for i,t in enumerate(pages) if i>=2 and norm(p.text) in t]
        if not hits:raise AssertionError('Не найден заголовок: '+p.text)
        mapping[p.text]=hits[0]
    return mapping

pdf=render();doc=Document(DOC);mapping=pages_for(pdf,doc)
# Кеш — уже существующее поле Word TOC, а не отдельное статическое содержание.
cache=[]
for p in doc.paragraphs:
    if '\t' not in p.text:continue
    heading=p.text.rsplit('\t',1)[0]
    if heading not in mapping:continue
    texts=p._p.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')
    assert texts[-1].text.isdigit()
    texts[-1].text=str(mapping[heading]);cache.append(heading)
assert len(cache)==len(mapping),(len(cache),len(mapping))
doc.save(DOC)
pdf.close();pdf=render();finalmap=pages_for(pdf,Document(DOC));assert finalmap==mapping
report={'pages':len(pdf),'toc_entries':len(cache),'headings':mapping,'sha256':hashlib.sha256(DOC.read_bytes()).hexdigest(),
        'figures':len(Document(DOC).inline_shapes),'tables':len(Document(DOC).tables),'page_numbers':[]}
for i,page in enumerate(pdf):
    text=page.get_text();blocks=page.get_text('blocks')
    footer=' '.join(b[4].strip() for b in blocks if b[1]>page.rect.height-60)
    if i>0:assert re.search(r'\b'+str(i+1)+r'\b',footer),(i+1,footer)
    report['page_numbers'].append({'page':i+1,'footer':footer})
    pix=page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5))
    pix.save(OUT/f'page-{i+1:02}.png')
# Проверка сохранности прежних разделов на уровне XML.
raw=subprocess.check_output(['git','show','c1e1e9b:docs/Отчет_Шустов_ЗН251.docx'],cwd=ROOT)
import io,zipfile
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
def sections(blob):
    tree=etree.fromstring(zipfile.ZipFile(io.BytesIO(blob)).read('word/document.xml'))
    elems=list(tree.find('w:body',ns));found={};current=None
    for element in elems:
        text=''.join(element.itertext())
        if text.startswith('1 Практическая работа № 1.') and element.find('w:pPr/w:pStyle',ns) is not None:
            # Заголовки в TOC имеют иной стиль и табуляцию; выбираем Heading 1 id=1.
            if element.find('w:pPr/w:pStyle',ns).get('{'+ns['w']+'}val')=='1':current=1
        if text.startswith('2 Практическая работа № 2.') and element.find('w:pPr/w:pStyle',ns) is not None:
            if element.find('w:pPr/w:pStyle',ns).get('{'+ns['w']+'}val')=='1':current=2
        if text.startswith('3 Практическая работа № 3.') and element.find('w:pPr/w:pStyle',ns) is not None:
            if element.find('w:pPr/w:pStyle',ns).get('{'+ns['w']+'}val')=='1':current=None
        if current:found.setdefault(current,[]).append(etree.tostring(element))
    return found
old,new=sections(raw),sections(DOC.read_bytes())
report['pr1_xml_unchanged']=old[1]==new[1];report['pr2_xml_unchanged']=old[2]==new[2]
assert report['pr1_xml_unchanged'] and report['pr2_xml_unchanged']
# Неизменность файлов исходных методичек и исторических снимков проверяется Git.
subprocess.run(['git','diff','--exit-code','c1e1e9b','--','data','docs/report-assets/pr2'],cwd=ROOT,check=True,capture_output=True)
report['source_materials_and_pr2_assets_unchanged']=True
(OUT/'report-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
# Контактные листы по 4 страницы; каждый лист затем просматривается визуально.
for start in range(0,len(pdf),4):
    sheet=Image.new('RGB',(1240,1810),'#d9dfda');draw=ImageDraw.Draw(sheet)
    for offset in range(4):
        n=start+offset
        if n>=len(pdf):break
        im=Image.open(OUT/f'page-{n+1:02}.png').convert('RGB');im.thumbnail((600,850))
        x=10+(offset%2)*620;y=30+(offset//2)*900
        draw.text((x,y-20),f'Page {n+1}',fill='black');sheet.paste(im,(x,y))
    sheet.save(OUT/f'sheet-{start+1:02}-{min(start+4,len(pdf)):02}.jpg',quality=92)
print(json.dumps({k:report[k] for k in ['pages','toc_entries','figures','tables','pr1_xml_unchanged','pr2_xml_unchanged']},ensure_ascii=False))
