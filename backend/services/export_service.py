import re
import tempfile
from xml.sax.saxutils import escape as xml_escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib import colors


# ── Padrões markdown comuns nos laudos ───────────────────────────────────────
_RE_SIG       = re.compile(r"^\s*_{5,}\s*$")
_RE_HR        = re.compile(r"^\s*(?:-{3,}|={3,})\s*$")
_RE_H1        = re.compile(r"^\s*#\s+(.*)$")
_RE_H2        = re.compile(r"^\s*##\s+(.*)$")
_RE_H3        = re.compile(r"^\s*###\s+(.*)$")
_RE_BULLET    = re.compile(r"^\s*[-*]\s+(.*)$")
_RE_ORDERED   = re.compile(r"^\s*\d+\.\s+(.*)$")
_RE_BOLD      = re.compile(r"\*\*([^*]+)\*\*")
_RE_ITALIC    = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_RE_CODE      = re.compile(r"`([^`]+)`")


def _inline_md_to_html(linha: str) -> str:
    """Escapa XML e converte inline markdown (**bold**, *italic*, `code`) para tags reportlab."""
    s = xml_escape(linha)
    s = _RE_BOLD.sub(r"<b>\1</b>", s)
    s = _RE_ITALIC.sub(r"<i>\1</i>", s)
    s = _RE_CODE.sub(r'<font face="Courier">\1</font>', s)
    return s


def _strip_markdown_inline(linha: str) -> str:
    """Remove marcadores inline mantendo apenas texto puro (uso em DOCX runs)."""
    s = _RE_BOLD.sub(r"\1", linha)
    s = _RE_ITALIC.sub(r"\1", s)
    s = _RE_CODE.sub(r"\1", s)
    return s


class ExportService:
    async def exportar(self, laudo: dict, formato: str) -> str:
        texto = laudo.get("laudo_editado") or laudo.get("laudo", "")
        if formato == "pdf":
            return self._to_pdf(texto, laudo)
        elif formato == "docx":
            return self._to_docx(texto, laudo)
        else:
            return self._to_txt(texto, laudo)

    # ── PDF ─────────────────────────────────────────────────────────────────
    def _to_pdf(self, texto: str, laudo: dict) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        doc = SimpleDocTemplate(
            tmp.name, pagesize=A4,
            leftMargin=2.5*cm, rightMargin=2.5*cm,
            topMargin=2.5*cm, bottomMargin=2.5*cm,
        )
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "titulo", parent=styles["Heading1"],
            fontSize=14, textColor=colors.HexColor("#1a56db"),
        )
        h2_style = ParagraphStyle(
            "h2", parent=styles["Heading2"],
            fontSize=12, textColor=colors.HexColor("#1a56db"), spaceBefore=8, spaceAfter=4,
        )
        h3_style = ParagraphStyle(
            "h3", parent=styles["Heading3"],
            fontSize=11, textColor=colors.HexColor("#1a56db"), spaceBefore=6, spaceAfter=3,
        )
        body_style = ParagraphStyle(
            "corpo", parent=styles["Normal"], fontSize=11, leading=16,
        )
        bullet_style = ParagraphStyle(
            "bullet", parent=body_style, leftIndent=14, bulletIndent=4,
        )
        # Largura útil A4 com margens 2.5cm = 16cm; assinatura ocupa 8cm à esquerda
        SIG_WIDTH = 8 * cm
        TEXT_WIDTH = 16 * cm
        sig_text_style = ParagraphStyle(
            "sig_text", parent=body_style,
            alignment=4,  # TA_JUSTIFY
            leftIndent=0,
            rightIndent=TEXT_WIDTH - SIG_WIDTH,
        )

        elements = [
            Paragraph(
                xml_escape(f"Data: {laudo.get('created_at','')[:10]}"),
                styles["Normal"],
            ),
            Spacer(1, 0.3*cm),
        ]

        linhas = texto.split("\n")
        i = 0
        while i < len(linhas):
            raw = linhas[i].rstrip()
            if not raw.strip():
                elements.append(Spacer(1, 0.15*cm))
                i += 1
                continue

            # Linha de assinatura (_____+) — bloco: espaço carimbo + linha pontilhada
            # alinhada à margem esquerda + nome/CRM justificados dentro da largura.
            if _RE_SIG.match(raw):
                elements.append(Spacer(1, 1.6*cm))  # espaço para carimbo
                elements.append(HRFlowable(
                    width=SIG_WIDTH, thickness=0.8, color=colors.black,
                    dash=[2, 2], hAlign="LEFT",
                    spaceBefore=0, spaceAfter=2,
                ))
                # Consome até 3 linhas seguintes (nome, CRM, especialidade) como bloco
                consumidas = 0
                j = i + 1
                while j < len(linhas) and consumidas < 3:
                    sub = linhas[j].rstrip()
                    if not sub.strip():
                        if consumidas > 0:
                            break  # blank após início do bloco encerra
                        j += 1
                        continue
                    elements.append(Paragraph(_inline_md_to_html(sub), sig_text_style))
                    consumidas += 1
                    j += 1
                i = j
                continue

            # Separadores horizontais (--- / ===)
            if _RE_HR.match(raw):
                elements.append(HRFlowable(width="100%", thickness=0.5,
                                           color=colors.HexColor("#cbd5e1"),
                                           spaceBefore=6, spaceAfter=6))
                i += 1
                continue

            # Headings markdown
            if (m := _RE_H3.match(raw)):
                elements.append(Paragraph(_inline_md_to_html(m.group(1)), h3_style))
                i += 1
                continue
            if (m := _RE_H2.match(raw)):
                elements.append(Paragraph(_inline_md_to_html(m.group(1)), h2_style))
                i += 1
                continue
            if (m := _RE_H1.match(raw)):
                elements.append(Paragraph(_inline_md_to_html(m.group(1)), title_style))
                i += 1
                continue

            # Listas — renderizadas como prosa (sem marcador), conforme padrão do laudo
            if (m := _RE_BULLET.match(raw)):
                elements.append(Paragraph(_inline_md_to_html(m.group(1)), body_style))
                i += 1
                continue
            if (m := _RE_ORDERED.match(raw)):
                elements.append(Paragraph(_inline_md_to_html(m.group(1)), body_style))
                i += 1
                continue

            # Linha all-uppercase curta vira H2 (legado: laudos com seções "ACHADOS")
            stripped = raw.strip()
            # Heurística legado: linha curta all-UPPERCASE composta apenas por letras/espaços
            # vira H2 (ex: "ACHADOS"). Exclui rótulos com ":" e linhas com números (ex: "CRM: 12345").
            _is_section_heading = (
                stripped.isupper()
                and len(stripped) < 60
                and ":" not in stripped
                and not any(c.isdigit() for c in stripped)
            )
            if _is_section_heading:
                elements.append(Paragraph(_inline_md_to_html(stripped), h2_style))
                i += 1
                continue

            # Corpo
            elements.append(Paragraph(_inline_md_to_html(raw), body_style))
            i += 1

        doc.build(elements)
        return tmp.name

    # ── DOCX ────────────────────────────────────────────────────────────────
    def _to_docx(self, texto: str, laudo: dict) -> str:
        from docx import Document as DocxDoc
        from docx.shared import Cm, Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        doc = DocxDoc()

        # Margens A4 alinhadas ao PDF (2.5cm em todos os lados)
        for section in doc.sections:
            section.top_margin    = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin   = Cm(2.5)
            section.right_margin  = Cm(2.5)

        # Compactar estilo Normal: sem space_after, line spacing single
        normal = doc.styles["Normal"]
        normal.paragraph_format.space_before = Pt(0)
        normal.paragraph_format.space_after  = Pt(0)
        normal.paragraph_format.line_spacing = 1.15
        # Reduzir espaçamento dos headings
        for nome_h in ("Heading 1", "Heading 2", "Heading 3"):
            try:
                h = doc.styles[nome_h]
                h.paragraph_format.space_before = Pt(6)
                h.paragraph_format.space_after  = Pt(2)
            except KeyError:
                pass

        doc.add_paragraph(f"Data: {laudo.get('created_at','')[:10]}")
        doc.add_paragraph("")

        # Largura útil ~16cm (A4, margens default); assinatura ocupa 8cm à esquerda.
        SIG_RIGHT_INDENT = Cm(8)

        ultimo_em_branco = True  # estado p/ coalescer linhas em branco consecutivas
        linhas = texto.split("\n")
        i = 0
        while i < len(linhas):
            raw = linhas[i].rstrip()
            if not raw.strip():
                if not ultimo_em_branco:
                    doc.add_paragraph("")
                    ultimo_em_branco = True
                i += 1
                continue

            # Linha de assinatura — espaço para carimbo via space_before;
            # paragraph com borda dotted limitada à SIG_RIGHT_INDENT;
            # nome/CRM justificados dentro da mesma largura.
            if _RE_SIG.match(raw):
                linha_p = doc.add_paragraph()
                linha_p.paragraph_format.right_indent = SIG_RIGHT_INDENT
                linha_p.paragraph_format.space_before = Cm(1.5)
                self._aplicar_borda_pontilhada(linha_p)
                consumidas = 0
                j = i + 1
                while j < len(linhas) and consumidas < 3:
                    sub = linhas[j].rstrip()
                    if not sub.strip():
                        if consumidas > 0:
                            break
                        j += 1
                        continue
                    p = doc.add_paragraph()
                    p.paragraph_format.right_indent = SIG_RIGHT_INDENT
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    self._add_runs_with_bold(p, sub)
                    consumidas += 1
                    j += 1
                i = j
                ultimo_em_branco = False
                continue

            # HR markdown não tem equivalente direto em DOCX; pulamos
            # (o espaçamento dos headings já separa seções)
            if _RE_HR.match(raw):
                i += 1
                continue

            ultimo_em_branco = False

            if (m := _RE_H3.match(raw)):
                doc.add_heading(_strip_markdown_inline(m.group(1)), level=3)
                i += 1
                continue
            if (m := _RE_H2.match(raw)):
                doc.add_heading(_strip_markdown_inline(m.group(1)), level=2)
                i += 1
                continue
            if (m := _RE_H1.match(raw)):
                doc.add_heading(_strip_markdown_inline(m.group(1)), level=1)
                i += 1
                continue

            if (m := _RE_BULLET.match(raw)):
                p = doc.add_paragraph()
                self._add_runs_with_bold(p, m.group(1))
                i += 1
                continue
            if (m := _RE_ORDERED.match(raw)):
                p = doc.add_paragraph()
                self._add_runs_with_bold(p, m.group(1))
                i += 1
                continue

            stripped = raw.strip()
            _is_section_heading = (
                stripped.isupper()
                and len(stripped) < 60
                and ":" not in stripped
                and not any(c.isdigit() for c in stripped)
            )
            if _is_section_heading:
                doc.add_heading(_strip_markdown_inline(stripped), level=2)
                i += 1
                continue

            p = doc.add_paragraph()
            self._add_runs_with_bold(p, raw)
            i += 1

        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        doc.save(tmp.name)
        return tmp.name

    @staticmethod
    def _aplicar_borda_pontilhada(paragraph) -> None:
        """Aplica borda inferior pontilhada via XML (linha de assinatura DOCX)."""
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        pPr = paragraph._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "dotted")
        bottom.set(qn("w:sz"), "12")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "000000")
        pBdr.append(bottom)
        pPr.append(pBdr)

    @staticmethod
    def _add_runs_with_bold(paragraph, texto: str) -> None:
        """Divide texto por **bold** e adiciona runs com formatação."""
        partes = re.split(r"(\*\*[^*]+\*\*)", texto)
        for parte in partes:
            if not parte:
                continue
            if parte.startswith("**") and parte.endswith("**"):
                run = paragraph.add_run(parte[2:-2])
                run.bold = True
            else:
                # remove italic/code marks restantes
                paragraph.add_run(_strip_markdown_inline(parte))

    # ── TXT ─────────────────────────────────────────────────────────────────
    def _to_txt(self, texto: str, laudo: dict) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w", encoding="utf-8")
        tmp.write(f"LAUDO MÉDICO — {laudo.get('especialidade','').upper()}\n")
        tmp.write(f"Data: {laudo.get('created_at','')[:10]}\n\n")
        tmp.write(texto)
        tmp.close()
        return tmp.name
