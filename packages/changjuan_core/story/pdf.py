from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfgen.canvas import Canvas

from changjuan_core.ai.narrative import NarrativeDraft


def render_story_pdf(draft: NarrativeDraft, title: str) -> bytes:
    registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 72
    canvas.setFont("STSong-Light", 18)
    canvas.drawString(72, y, title)
    y -= 40
    canvas.setFont("STSong-Light", 11)
    for chapter in draft.chapters:
        if y < 120:
            canvas.showPage()
            canvas.setFont("STSong-Light", 11)
            y = height - 72
        canvas.drawString(72, y, chapter.title)
        y -= 18
        for line in chapter.body.splitlines():
            canvas.drawString(86, y, line[:70])
            y -= 16
            if y < 72:
                canvas.showPage()
                canvas.setFont("STSong-Light", 11)
                y = height - 72
        y -= 12
    canvas.save()
    return buffer.getvalue()
