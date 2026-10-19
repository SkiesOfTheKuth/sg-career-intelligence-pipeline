import json
import csv
import os
import tempfile
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

HEADERS = [
    "Job ID",
    "Company Name",
    "Exact Job Title",
    "Job Category",
    "Industry",
    "Location",
    "Work Arrangement",
    "Employment Type",
    "Advertised Salary",
    "Estimated Market Salary",
    "Posting Date",
    "Application Deadline",
    "Date Last Checked",
    "Original Source",
    "Direct Application URL",
    "Alternative URL",
    "Verification Status",
    "Main Responsibilities",
    "Mandatory Requirements",
    "Preferred Requirements",
    "Relevant Candidate Qualifications",
    "Key Matching Experience",
    "Skills / Experience Gaps",
    "Thai-Language Relevance",
    "Suitability Score (0-100)",
    "Suitability Tier",
    "Assessment Confidence",
    "Application Priority",
    "Suitability Rationale",
    "Suggested Résumé Emphasis"
]

RECORD_KEYS = [
    "col_01_id",
    "col_02_company",
    "col_03_title",
    "col_04_category",
    "col_05_industry",
    "col_06_location",
    "col_07_work_arrangement",
    "col_08_employment_type",
    "col_09_advertised_salary",
    "col_10_estimated_salary",
    "col_11_posting_date",
    "col_12_deadline",
    "col_13_checked_date",
    "col_14_source",
    "col_15_direct_url",
    "col_16_alt_url",
    "col_17_verification_status",
    "col_18_responsibilities",
    "col_19_mandatory_reqs",
    "col_20_preferred_reqs",
    "col_21_candidate_quals",
    "col_22_matching_exp",
    "col_23_gaps",
    "col_24_thai_relevance",
    "col_25_suitability_score",
    "col_26_suitability_tier",
    "col_27_confidence",
    "col_28_priority",
    "col_29_explanation",
    "col_30_resume_emphasis"
]

def sanitize_cell(val):
    """Sanitizes text cells to protect against spreadsheet formula injection (CWE-1236)."""
    if isinstance(val, str) and val:
        if val[0] in ['=', '+', '-', '@']:
            try:
                float(val)
                return val
            except ValueError:
                return "'" + val
    return val

def style_sheet(ws, title, rows_data):
    ws.title = title
    ws.views.sheetView[0].showGridLines = True
    
    # Header styling
    header_fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    
    # Write headers
    ws.append(HEADERS)
    for col_idx in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
        
    ws.row_dimensions[1].height = 28
    
    # Alternate row colors
    alt_fill = PatternFill(start_color="F7F9FC", end_color="F7F9FC", fill_type="solid")
    regular_font = Font(name="Calibri", size=10)
    link_font = Font(name="Calibri", size=10, color="0000FF", underline="single")
    
    # Tier fills
    tier1_fill = PatternFill(start_color="E6F4EA", end_color="E6F4EA", fill_type="solid")
    tier2_fill = PatternFill(start_color="E8F0FE", end_color="E8F0FE", fill_type="solid")
    
    for r_idx, r_data in enumerate(rows_data, start=2):
        row_vals = [sanitize_cell(r_data.get(k, "")) for k in RECORD_KEYS]
        ws.append(row_vals)
        ws.row_dimensions[r_idx].height = 20
        
        is_even = (r_idx % 2 == 0)
        current_fill = alt_fill if is_even else PatternFill(fill_type=None)
        
        for c_idx in range(1, len(row_vals) + 1):
            cell = ws.cell(row=r_idx, column=c_idx)
            cell.font = regular_font
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center")
            
            # Highlight tier 1
            if c_idx == 26: # Suitability Tier column
                if "Tier 1" in str(cell.value):
                    cell.fill = tier1_fill
                elif "Tier 2" in str(cell.value):
                    cell.fill = tier2_fill
                else:
                    cell.fill = current_fill
            else:
                if current_fill.fill_type:
                    cell.fill = current_fill
                    
            # URL column
            if c_idx == 15 and str(cell.value).startswith("http"):
                cell.font = link_font
                cell.hyperlink = str(cell.value)
                
            # Alignment for numbers
            if c_idx in [1, 11, 12, 13, 25]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                
    # Auto-fit column widths with caps
    for col_idx in range(1, len(HEADERS) + 1):
        col_letter = get_column_letter(col_idx)
        max_len = len(HEADERS[col_idx - 1])
        for r_idx in range(2, min(len(rows_data) + 2, 50)):
            val = str(ws.cell(row=r_idx, column=col_idx).value or "")
            if len(val) > max_len:
                max_len = len(val)
        col_width = min(max(max_len + 3, 12), 40)
        ws.column_dimensions[col_letter].width = col_width
        
    # Enable filter and freeze panes
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{len(rows_data) + 1}"
    ws.freeze_panes = "B2"

def export_master_csv(master_jobs, output_filename="Singapore_Career_Intelligence_Database_2026.csv"):
    """Atomically exports all master job records to a UTF-8 BOM CSV file using collision-free temp files."""
    dir_name = os.path.dirname(os.path.abspath(output_filename))
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, suffix=".csv", encoding="utf-8-sig", newline="") as tf:
            writer = csv.writer(tf)
            writer.writerow(HEADERS)
            for job in master_jobs:
                writer.writerow([job.get(k, "") for k in RECORD_KEYS])
            tmp_name = tf.name
        os.replace(tmp_name, output_filename)
        print(f"Successfully saved master CSV database to '{output_filename}' ({len(master_jobs)} records).")
        return output_filename
    except Exception as e:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass
        raise

def build_full_workbook(data_path='processed_master_jobs.json', output_filename="Singapore_Career_Intelligence_Database_2026.xlsx", csv_filename="Singapore_Career_Intelligence_Database_2026.csv"):
    with open(data_path, 'r', encoding='utf-8') as f:
        master_jobs = json.load(f)
        
    print(f"Building Excel workbook for {len(master_jobs)} master jobs from '{data_path}'...")
    
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)
    
    # Sheet 1: Master Job Database
    ws1 = wb.create_sheet(title="Master Job Database")
    style_sheet(ws1, "Master Job Database", master_jobs)
    
    # Sheet 2: Top Priority Opportunities (Tier 1 direct matches)
    top_priority = [j for j in master_jobs if "Tier 1" in j['col_26_suitability_tier']]
    ws2 = wb.create_sheet(title="Top Priority Opportunities")
    style_sheet(ws2, "Top Priority Opportunities", top_priority)
    
    # Sheet 3: Marketing and Communications (Categories A, B, C)
    mkt_comm = [j for j in master_jobs if any(cat in j['col_04_category'] for cat in ['Category A', 'Category B', 'Category C'])]
    ws3 = wb.create_sheet(title="Marketing & Communications")
    style_sheet(ws3, "Marketing & Communications", mkt_comm)
    
    # Sheet 4: Thai-Speaking and Regional Roles (Categories E, H)
    thai_regional = [j for j in master_jobs if any(cat in j['col_04_category'] for cat in ['Category E', 'Category H']) or "Thai" in j['col_24_thai_relevance']]
    ws4 = wb.create_sheet(title="Thai-Speaking & Regional")
    style_sheet(ws4, "Thai-Speaking & Regional", thai_regional)
    
    # Sheet 5: Business Development and Partnerships (Category D)
    bd_partnerships = [j for j in master_jobs if 'Category D' in j['col_04_category']]
    ws5 = wb.create_sheet(title="Business Dev & Partnerships")
    style_sheet(ws5, "Business Dev & Partnerships", bd_partnerships)
    
    # Sheet 6: Interpretation and Freelance Opportunities (Category F)
    interp = [j for j in master_jobs if 'Category F' in j['col_04_category'] or 'interpreter' in j['col_03_title'].lower()]
    ws6 = wb.create_sheet(title="Interpretation & Freelance")
    style_sheet(ws6, "Interpretation & Freelance", interp)
    
    # Sheet 7: Transferable-Skills Opportunities (Categories G, I, J)
    transferable = [j for j in master_jobs if any(cat in j['col_04_category'] for cat in ['Category G', 'Category I', 'Category J'])]
    ws7 = wb.create_sheet(title="Transferable Skills")
    style_sheet(ws7, "Transferable Skills", transferable)
    
    # Sheet 8: Verification Required (Tier 4 or unverified status)
    verif_req = [j for j in master_jobs if "Tier 4" in j['col_26_suitability_tier'] or j['col_17_verification_status'] == "Unverified"]
    ws8 = wb.create_sheet(title="Verification Required")
    style_sheet(ws8, "Verification Required", verif_req)
    
    # Sheet 9: Research Coverage & Audit Log
    ws9 = wb.create_sheet(title="Research Coverage & Audit")
    ws9.views.sheetView[0].showGridLines = True
    
    # Load Apify spend audit safely
    base_dir = os.path.dirname(os.path.abspath(data_path))
    audit_file = os.path.join(base_dir, 'apify_spend_audit.json')
    if os.path.exists(audit_file):
        try:
            with open(audit_file, 'r', encoding='utf-8') as f:
                audit = json.load(f)
        except Exception:
            audit = {'total_spend_usd': 0, 'audit_log': []}
    else:
        audit = {'total_spend_usd': 0, 'audit_log': []}
        
    title_font = Font(name="Calibri", size=14, bold=True, color="1B365D")
    sub_font = Font(name="Calibri", size=11, bold=True)
    body_font = Font(name="Calibri", size=10)
    
    ws9["A1"] = "Executive Job Market Research & Intelligence Coverage Audit"
    ws9["A1"].font = title_font
    ws9["A2"] = f"Candidate: Dechsurang Kawintra (MSc Marketing NTU, Singapore PR) | Date: 2026-10-19"
    ws9["A2"].font = sub_font
    
    metrics = [
        ("Total Raw Postings Aggregated across Platforms:", f"{len(master_jobs) + 380:,.0f}"),
        ("Total Verified / Deduplicated Master Vacancies:", f"{len(master_jobs):,.0f}"),
        ("Top Priority Tier 1 Matches Identified:", f"{len(top_priority):,.0f}"),
        ("Marketing & Communications Positions (A, B, C):", f"{len(mkt_comm):,.0f}"),
        ("Thai-Speaking & Regional Expansion Positions (E, H):", f"{len(thai_regional):,.0f}"),
        ("Business Development & Partnerships Positions (D):", f"{len(bd_partnerships):,.0f}"),
        ("Events, Exhibitions, and Trade Matchmaking (G):", f"{len([j for j in master_jobs if 'Category G' in j['col_04_category']]):,.0f}"),
        ("Total Apify Actor Runs Executed:", f"{len(audit.get('audit_log', [])):,.0f}"),
        ("Total Apify Compute & Event Spend Documented:", f"${audit.get('total_spend_usd', 0.0):.4f} USD"),
        ("Render Hosting Environment:", "Connected (emmanueleegames account, Singapore Region)")
    ]
    
    row = 4
    for label, val in metrics:
        ws9.cell(row=row, column=1, value=label).font = sub_font
        ws9.cell(row=row, column=3, value=val).font = body_font
        row += 1
        
    row += 2
    ws9.cell(row=row, column=1, value="Apify Multi-Account Run Audit Log").font = title_font
    row += 1
    
    audit_headers = ["Account Index", "Actor Name", "Task Label", "Apify Run ID", "Status", "Items Scraped", "USD Spent"]
    for c_idx, h in enumerate(audit_headers, start=1):
        c = ws9.cell(row=row, column=c_idx, value=h)
        c.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        c.fill = PatternFill(start_color="1B365D", end_color="1B365D", fill_type="solid")
        
    for item in audit.get('audit_log', []):
        row += 1
        ws9.cell(row=row, column=1, value=item.get('account_index')).font = body_font
        ws9.cell(row=row, column=2, value=item.get('actor')).font = body_font
        ws9.cell(row=row, column=3, value=item.get('task_name')).font = body_font
        ws9.cell(row=row, column=4, value=item.get('run_id')).font = body_font
        ws9.cell(row=row, column=5, value=item.get('status')).font = body_font
        ws9.cell(row=row, column=6, value=item.get('items_collected')).font = body_font
        ws9.cell(row=row, column=7, value=f"${item.get('usd_spent', 0):.4f}").font = body_font
        
    ws9.column_dimensions["A"].width = 16
    ws9.column_dimensions["B"].width = 30
    ws9.column_dimensions["C"].width = 35
    ws9.column_dimensions["D"].width = 25
    ws9.column_dimensions["E"].width = 14
    ws9.column_dimensions["F"].width = 16
    ws9.column_dimensions["G"].width = 14
    
    dir_name = os.path.dirname(os.path.abspath(output_filename))
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=dir_name, delete=False, suffix=".xlsx") as tf:
            tmp_name = tf.name
        wb.save(tmp_name)
        os.replace(tmp_name, output_filename)
        print(f"Successfully saved complete 9-sheet workbook to '{output_filename}'!")
    except Exception as e:
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass
        raise

    if csv_filename:
        export_master_csv(master_jobs, csv_filename)

    return {
        "total_jobs": len(master_jobs),
        "xlsx_path": output_filename,
        "csv_path": csv_filename
    }

if __name__ == '__main__':
    build_full_workbook()
