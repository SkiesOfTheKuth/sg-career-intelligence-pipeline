"""Shared safe spreadsheet exports for web and offline use."""
import csv
import io
import json
from fastapi.responses import Response

def safe_cell(value):
    text='' if value is None else str(value)
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text


JOB_HEADERS=['ID','Company','Title','Job family','Employment type','Advertised salary','Fit','Thai relevance','Status','Last verified','Source','Original URL','Description','Requirements','Preferred requirements','Why consider this','Requirements to check','Documented fit score /100','Score provisional','Score limits','Score version','Assessment summary','Description evidence date','Requirement evidence date','Field provenance','Clause evidence']
def job_row(j):
    provenance=j.get('field_provenance') or {}
    evidence_date=lambda field: (provenance.get(field) or {}).get('checked_at') or (provenance.get(field) or {}).get('source_record_date')
    return [j.get(k,'') for k in ('id','company','title','category')]+['; '.join(j.get('employment_types') or [j.get('employment_type') or 'Not stated'])]+[
        j.get('salary',{}).get('display','Not disclosed'),j.get('assessment',{}).get('fit'),j.get('thai_relevance'),j.get('status'),
        j.get('verification',{}).get('last_success_at'),'; '.join(x['name'] for x in j.get('sources',[])),j.get('url'),j.get('description'),
        '\n'.join(j.get('requirements',{}).get('mandatory') or []),'\n'.join(j.get('requirements',{}).get('preferred') or []),'\n'.join(j.get('assessment',{}).get('reasons') or []),'\n'.join(j.get('assessment',{}).get('gaps') or []),
        j.get('assessment',{}).get('score',{}).get('value'),j.get('assessment',{}).get('score',{}).get('provisional'),
        '\n'.join(x['reason'] for x in j.get('assessment',{}).get('score',{}).get('limits',[])), j.get('assessment',{}).get('score',{}).get('version'),
        j.get('assessment_summary'), evidence_date('description'), evidence_date('requirements'), json.dumps(provenance,ensure_ascii=False),
        json.dumps(j.get('assessment',{}).get('score',{}).get('duties',[]),ensure_ascii=False)]


def export_response(headers,rows,name,format='csv'):
    if format=='xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
        book=Workbook();sheet=book.active;sheet.title='Roles'
        sheet.append(headers)
        for row in rows: sheet.append([safe_cell(v) for v in row])
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for cell in sheet[1]:cell.font=Font(bold=True)
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width=28
        for row in sheet.iter_rows(min_row=2):
            for cell in row: cell.alignment=Alignment(vertical='top')
        data=io.BytesIO();book.save(data)
        return Response(data.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{name}.xlsx"'})
    data=io.StringIO();writer=csv.writer(data);writer.writerow(headers)
    writer.writerows([[safe_cell(v) for v in row] for row in rows])
    return Response(data.getvalue().encode('utf-8-sig'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{name}.csv"'})
