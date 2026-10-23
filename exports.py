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
        full_text = None
        for row in rows:
            cells = []
            for index, value in enumerate(row):
                original = '' if value is None else str(value)
                safe = safe_cell(original)
                if len(safe) > 32767:
                    # Excel's native cell limit is 32,767 characters. openpyxl
                    # silently truncates longer values, so retain full content
                    # in ordered, identified parts on a separate worksheet.
                    if full_text is None:
                        full_text = book.create_sheet('Full text')
                        full_text.append(['Record ID', 'Field', 'Part', 'Text', 'Formula prefix added'])
                        full_text.freeze_panes = 'A2'
                    chunks = [original[start:start + 30000] for start in range(0, len(original), 30000)]
                    for part, chunk in enumerate(chunks, 1):
                        escaped = safe_cell(chunk)
                        full_text.append([safe_cell(row[0]), headers[index], part, escaped, 'Yes' if escaped != chunk else 'No'])
                    safe = safe_cell(original[:120] + f'… [Complete text: Full text worksheet; {len(chunks)} parts; field: {headers[index]}]')
                cells.append(safe)
            sheet.append(cells)
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for cell in sheet[1]:cell.font=Font(bold=True)
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width=28
        for row in sheet.iter_rows(min_row=2):
            for cell in row: cell.alignment=Alignment(vertical='top')
        if full_text is not None:
            for cell in full_text[1]: cell.font = Font(bold=True)
            for column in full_text.columns:
                full_text.column_dimensions[column[0].column_letter].width = 28
            full_text.column_dimensions['D'].width = 80
        data=io.BytesIO();book.save(data)
        return Response(data.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':f'attachment; filename="{name}.xlsx"'})
    data=io.StringIO();writer=csv.writer(data);writer.writerow(headers)
    writer.writerows([[safe_cell(v) for v in row] for row in rows])
    return Response(data.getvalue().encode('utf-8-sig'),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{name}.csv"'})
