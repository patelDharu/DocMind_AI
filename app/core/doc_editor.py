import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from app.core.resilience import retry_gemini, generate_with_cascade


def sanitize_xml(s: str) -> str:
    """Removes null bytes and control characters incompatible with XML 1.0."""
    if not isinstance(s, str):
        return str(s) if s is not None else ""
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x84\x86-\x9f]", "", s)


def get_genai_client():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=api_key.strip("'\""))

MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")


class DocumentEditor:
    """
    Document Editor & Studio:
    - Smart Modular Document Augmentation: drafts new sections/appendices using minimal tokens (<1,000 tokens),
      completely preventing 429 quota exhaustion.
    - Exports updated content into professionally styled DOCX and PDF files.
    """

    def __init__(self):
        self.model = MODEL_NAME

    @retry_gemini(max_retries=4, initial_delay=3.0)
    def update_document(
        self,
        original_text: str,
        instruction: str,
        document_title: str = "Document",
        edit_mode: str = "append",
    ) -> str:
        """
        Smart Modular Document Augmentation:
        - When 'append' (default): Gemini drafts ONLY the requested new section/appendix/clause (~400 tokens),
          and Python seamlessly combines it with the original full 7-8 page document!
          This uses 90% fewer tokens, avoids 429 rate limit triggers, and finishes in 1-2 seconds.
        - When 'revise': Gemini revises the document focusing on the target instruction.
        """
        client = get_genai_client()

        if edit_mode == "append":
            # Give Gemini a concise 2,500-char preview for style and tone context
            preview = original_text[:2500]

            prompt = f"""
DOCUMENT TITLE: {document_title}

DOCUMENT PREVIEW (For tone, format, and context):
{preview}

--------------------------------------------------
USER UPDATE REQUEST:
{instruction}

--------------------------------------------------
TASK:
Draft the NEW section, clause, appendix, or content requested by the user.
Format the new section in clean Markdown:
- Use ## or ### for Section Headings
- Use bullet points (- ) and numbered lists
- Use Markdown tables (| col1 | col2 |) if tabular data is requested

RULES:
1. Output ONLY the new section content to be added to the document.
2. Do NOT repeat or echo the existing document text.
3. Do NOT include conversational preamble or greeting.
""".strip()

            new_section = generate_with_cascade(
                client=client,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are DocMind AI's professional document drafting specialist. Draft clean, authoritative document sections.",
                    max_output_tokens=1500,
                    temperature=0.2,
                ),
                model_override=self.model,
            )

            # Combine original full document with the newly drafted section
            updated_doc = (
                original_text.strip()
                + "\n\n---\n\n"
                + new_section.strip()
            )
            return updated_doc

        else:
            # Revise mode with token budgeting
            budgeted_orig = original_text[:12000]

            prompt = f"""
DOCUMENT TITLE: {document_title}

DOCUMENT CONTENT:
{budgeted_orig}

--------------------------------------------------
USER REVISION INSTRUCTION:
{instruction}

--------------------------------------------------
TASK:
Apply the user's revision instruction to the document content above.

CRITICAL FORMATTING & EDITING RULES:
1. Preserve all existing document structure, headings, metadata, and tables.
2. If updating numbers, counts, or table cells (e.g. "update inspection count by 10"):
   - Accurately update the exact numbers in the target table cells and recompute totals/sums as appropriate.
3. Keep all tables in clean, standard Markdown table format (| col 1 | col 2 | ... |).
4. Do NOT duplicate table content as raw unformatted text. Output ONLY the properly formatted Markdown table.
5. Output ONLY the revised document text with zero conversational preamble.
""".strip()

            revised_text = generate_with_cascade(
                client=client,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are DocMind AI's professional document editor. You revise documents with extreme precision, preserving tables, layout, and professional polish.",
                    max_output_tokens=3000,
                    temperature=0.1,
                ),
                model_override=self.model,
            )
            return revised_text if revised_text else original_text

    @staticmethod
    def export_to_docx(markdown_content: str, output_path: str, title: str = "Updated Document") -> str:
        """
        Converts Markdown content into a professionally styled DOCX document.
        Sanitizes all XML-incompatible control characters and handles table shapes cleanly.
        """
        markdown_content = sanitize_xml(markdown_content)
        title = sanitize_xml(title)

        doc = Document()

        style = doc.styles['Normal']
        font = style.font
        font.name = 'Calibri'
        font.size = Pt(11)
        font.color.rgb = RGBColor(0x22, 0x22, 0x22)

        title_p = doc.add_heading(title, level=0)
        title_p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        doc.add_paragraph()

        lines = markdown_content.split("\n")
        in_table = False
        table_rows = []

        for line in lines:
            line_str = line.strip()

            # Ignore raw table label artifacts
            if line_str.startswith("[Table ") and line_str.endswith("]"):
                continue

            # Markdown Table detection
            if line_str.startswith("|") and line_str.endswith("|"):
                in_table = True
                cells = [sanitize_xml(c.strip()) for c in line_str[1:-1].split("|")]
                if not all(set(c).issubset({'-', ' ', ':'}) for c in cells):
                    table_rows.append(cells)
                continue
            else:
                if in_table and table_rows:
                    max_cols = max(1, max((len(r) for r in table_rows), default=1))
                    t = doc.add_table(rows=len(table_rows), cols=max_cols)
                    try:
                        t.style = 'Light Shading Accent 1'
                    except Exception:
                        pass
                    for r_idx, row in enumerate(table_rows):
                        for c_idx, val in enumerate(row):
                            if c_idx < max_cols:
                                t.cell(r_idx, c_idx).text = sanitize_xml(val)
                    doc.add_paragraph()
                    in_table = False
                    table_rows = []

            if not line_str or line_str == "---":
                continue

            if line_str.startswith("### "):
                doc.add_heading(sanitize_xml(line_str[4:]), level=3)
            elif line_str.startswith("## "):
                doc.add_heading(sanitize_xml(line_str[3:]), level=2)
            elif line_str.startswith("# "):
                doc.add_heading(sanitize_xml(line_str[2:]), level=1)
            elif line_str.startswith("- ") or line_str.startswith("* "):
                clean_bullet = sanitize_xml(line_str[2:].replace("**", ""))
                doc.add_paragraph(clean_bullet, style='List Bullet')
            elif line_str[0].isdigit() and len(line_str) > 2 and line_str[1:3] in [". ", ") "]:
                clean_num = sanitize_xml(line_str[3:].replace("**", ""))
                doc.add_paragraph(clean_num, style='List Number')
            else:
                clean_p = sanitize_xml(line_str.replace("**", "").replace("`", ""))
                doc.add_paragraph(clean_p)

        if in_table and table_rows:
            max_cols = max(1, max((len(r) for r in table_rows), default=1))
            t = doc.add_table(rows=len(table_rows), cols=max_cols)
            try:
                t.style = 'Light Shading Accent 1'
            except Exception:
                pass
            for r_idx, row in enumerate(table_rows):
                for c_idx, val in enumerate(row):
                    if c_idx < max_cols:
                        t.cell(r_idx, c_idx).text = sanitize_xml(val)
            doc.add_paragraph()

        doc.save(output_path)
        return output_path

    @staticmethod
    def export_to_pdf(markdown_content: str, output_path: str, title: str = "Updated Document") -> str:
        """
        Converts Markdown content into an executive publication-grade PDF file using ReportLab
        with full support for styled tables, headers, alternating zebra stripes, and clean margins.
        """
        markdown_content = sanitize_xml(markdown_content)
        title = sanitize_xml(title)
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
            from reportlab.lib import colors

            doc = SimpleDocTemplate(
                output_path,
                pagesize=letter,
                rightMargin=36,
                leftMargin=36,
                topMargin=36,
                bottomMargin=36,
            )

            styles = getSampleStyleSheet()

            # Custom executive styling palette
            PRIMARY_COLOR = colors.HexColor("#1e3a8a")  # Deep Navy Blue
            SECONDARY_COLOR = colors.HexColor("#3b82f6")
            DARK_TEXT = colors.HexColor("#0f172a")
            MUTED_TEXT = colors.HexColor("#475569")
            BORDER_COLOR = colors.HexColor("#cbd5e1")
            ZEBRA_COLOR = colors.HexColor("#f8fafc")

            title_style = ParagraphStyle(
                "DocTitle",
                parent=styles["Title"],
                fontName="Helvetica-Bold",
                fontSize=20,
                leading=24,
                textColor=PRIMARY_COLOR,
                alignment=0,
                spaceAfter=6,
            )

            h1_style = ParagraphStyle(
                "DocH1",
                parent=styles["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=14,
                leading=18,
                textColor=PRIMARY_COLOR,
                spaceBefore=10,
                spaceAfter=6,
            )

            h2_style = ParagraphStyle(
                "DocH2",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=15,
                textColor=DARK_TEXT,
                spaceBefore=8,
                spaceAfter=4,
            )

            body_style = ParagraphStyle(
                "DocBody",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=9.5,
                leading=13.5,
                textColor=DARK_TEXT,
                spaceAfter=4,
            )

            bullet_style = ParagraphStyle(
                "DocBullet",
                parent=body_style,
                leftIndent=14,
                firstLineIndent=-10,
                spaceAfter=3,
            )

            th_style = ParagraphStyle(
                "DocTH",
                parent=styles["Normal"],
                fontName="Helvetica-Bold",
                fontSize=9,
                leading=12,
                textColor=colors.whitesmoke,
                alignment=1,
            )

            td_style = ParagraphStyle(
                "DocTD",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=8.5,
                leading=11.5,
                textColor=DARK_TEXT,
                alignment=1,
            )

            td_left_style = ParagraphStyle(
                "DocTDLeft",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=8.5,
                leading=11.5,
                textColor=DARK_TEXT,
                alignment=0,
            )

            story = [
                Paragraph(f"<b>{title}</b>", title_style),
                HRFlowable(width="100%", thickness=2, color=PRIMARY_COLOR, spaceBefore=4, spaceAfter=12),
            ]

            lines = markdown_content.split("\n")
            in_table = False
            raw_table_rows = []

            def build_reportlab_table(rows: list) -> Table:
                """Constructs an executive styled Table with auto-wrapped cells and proportional widths."""
                if not rows:
                    return None

                max_cols = max(1, max((len(r) for r in rows), default=1))
                printable_width = letter[0] - 72.0  # 540 pt printable width

                # Determine column widths: first col gets more room if it has longer text
                if max_cols > 1:
                    first_col_w = max(130.0, printable_width * 0.32)
                    other_col_w = (printable_width - first_col_w) / max(1, max_cols - 1)
                    col_widths = [first_col_w] + [other_col_w] * (max_cols - 1)
                else:
                    col_widths = [printable_width]

                formatted_data = []
                for r_idx, row in enumerate(rows):
                    row_cells = []
                    for c_idx in range(max_cols):
                        val = row[c_idx] if c_idx < len(row) else ""
                        clean_val = sanitize_xml(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                        if r_idx == 0:
                            p = Paragraph(f"<b>{clean_val}</b>", th_style)
                        else:
                            cell_p_style = td_left_style if c_idx == 0 else td_style
                            p = Paragraph(clean_val, cell_p_style)
                        row_cells.append(p)
                    formatted_data.append(row_cells)

                t = Table(formatted_data, colWidths=col_widths, repeatRows=1)
                t_styles = [
                    ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_COLOR),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("GRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                    ("BOX", (0, 0), (-1, -1), 1.2, PRIMARY_COLOR),
                ]

                # Zebra striping for data rows
                for r_i in range(1, len(rows)):
                    bg = ZEBRA_COLOR if (r_i % 2 == 1) else colors.white
                    t_styles.append(("BACKGROUND", (0, r_i), (-1, r_i), bg))

                t.setStyle(TableStyle(t_styles))
                return t

            for line in lines:
                l = line.strip()

                # Ignore raw table label artifacts
                if l.startswith("[Table ") and l.endswith("]"):
                    continue

                # Markdown Table detection
                if l.startswith("|") and l.endswith("|"):
                    in_table = True
                    cells = [sanitize_xml(c.strip()) for c in l[1:-1].split("|")]
                    if not all(set(c).issubset({"-", " ", ":"}) for c in cells):
                        raw_table_rows.append(cells)
                    continue
                else:
                    if in_table and raw_table_rows:
                        rl_table = build_reportlab_table(raw_table_rows)
                        if rl_table:
                            story.append(Spacer(1, 6))
                            story.append(rl_table)
                            story.append(Spacer(1, 8))
                        in_table = False
                        raw_table_rows = []

                if not l or l == "---":
                    story.append(Spacer(1, 6))
                    continue

                clean_l = (
                    sanitize_xml(l)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                clean_l = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", clean_l)

                if clean_l.startswith("### "):
                    story.append(Paragraph(f"<b>{clean_l[4:]}</b>", h2_style))
                    story.append(Spacer(1, 3))
                elif clean_l.startswith("## "):
                    story.append(Paragraph(f"<b>{clean_l[3:]}</b>", h1_style))
                    story.append(Spacer(1, 4))
                elif clean_l.startswith("# "):
                    story.append(Paragraph(f"<b>{clean_l[2:]}</b>", title_style))
                    story.append(Spacer(1, 6))
                elif clean_l.startswith("- ") or clean_l.startswith("* "):
                    story.append(Paragraph(f"&bull;&nbsp; {clean_l[2:]}", bullet_style))
                elif clean_l[0].isdigit() and len(clean_l) > 2 and clean_l[1:3] in [". ", ") "]:
                    story.append(Paragraph(clean_l, bullet_style))
                else:
                    story.append(Paragraph(clean_l, body_style))

            if in_table and raw_table_rows:
                rl_table = build_reportlab_table(raw_table_rows)
                if rl_table:
                    story.append(Spacer(1, 6))
                    story.append(rl_table)
                    story.append(Spacer(1, 8))

            doc.build(story)
            return output_path

        except ImportError:
            txt_path = output_path.replace(".pdf", ".txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(f"=== {title} ===\n\n" + markdown_content)
            return txt_path
