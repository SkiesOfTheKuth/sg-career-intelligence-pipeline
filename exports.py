"""Shared safe spreadsheet exports for web and offline use."""
import csv
import io
from fastapi.responses import Response

def safe_cell(value):
    text='' if value is None else str(value)
    return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text


JOB_HEADERS=['ID','Company','Title','Job family','Employment type','Advertised salary','Fit','Thai relevance','Status','Last verified','Source','Original URL','Description','Requirements','Preferred requirements','Why consider this','Requirements to check']
def job_row(j):
    return [j.get(k,'') for k in ('id','company','title','category','employment_type')]+[
        j.get('salary',{}).get('display','Not disclosed'),j.get('assessment',{}).get('fit'),j.get('thai_relevance'),j.get('status'),
        j.get('verification',{}).get('checked_at'),'; '.join(x['name'] for x in j.get('sources',[])),j.get('url'),j.get('description'),
        '\n'.join(j.get('requirements',{}).get('mandatory') or []),'\n'.join(j.get('requirements',{}).get('preferred') or []),'\n'.join(j.get('assessment',{}).get('reasons') or []),'\n'.join(j.get('assessment',{}).get('gaps') or [])]


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
