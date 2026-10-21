"""Generate the same source-grounded exports as the authenticated workspace."""
import json
from pathlib import Path
from evidence import repair_jobs, sort_key
from exports import safe_cell as sanitize_cell, JOB_HEADERS as HEADERS, job_row, export_response


def build_full_workbook(data_path='processed_master_jobs.json',
                        output_filename='Singapore_Career_Intelligence_Database_2026.xlsx',
                        csv_filename='Singapore_Career_Intelligence_Database_2026.csv'):
    jobs=repair_jobs(json.loads(Path(data_path).read_text(encoding='utf-8-sig')))
    jobs=[j for j in jobs if j['status'] not in ('expired','closed','unavailable')]
    jobs.sort(key=sort_key)
    rows=[job_row(job) for job in jobs]
    Path(output_filename).write_bytes(export_response(HEADERS,rows,'Singapore_roles','xlsx').body)
    Path(csv_filename).write_bytes(export_response(HEADERS,rows,'Singapore_roles').body)
    return len(jobs)


if __name__=='__main__':
    print(f'Exported {build_full_workbook()} available source-grounded roles.')
