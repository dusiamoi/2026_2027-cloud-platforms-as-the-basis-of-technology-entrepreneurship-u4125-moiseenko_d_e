#!/usr/bin/env python3
"""Генерирует схемы инфраструктуры «ЧекСкан» для трёх этапов:
- chekscan-infrastructure.drawio — один файл draw.io, три страницы (редактируемый);
- 01-pilot.svg, 02-partners.svg, 03-production.svg — те же схемы в SVG.
Запуск: python3 lab4/diagrams/make_diagrams.py
"""
import html
import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))

COLORS = {  # fill, stroke
    "user": ("#F5F5F5", "#666666"),
    "net": ("#FDECEA", "#C0392B"),
    "sec": ("#FFF4E5", "#D68910"),
    "compute": ("#E8F1FD", "#1A73E8"),
    "db": ("#E6F4EA", "#188038"),
    "storage": ("#E6F4EA", "#188038"),
    "int": ("#F3E8FD", "#8E24AA"),
    "ai": ("#FCE8F3", "#C2185B"),
    "ops": ("#EEEEEE", "#5F6368"),
    "env": ("#FFFDE7", "#B7950B"),
}

STAGES = [
    {
        "key": "pilot", "file": "01-pilot.svg", "page": "1. Пилот",
        "title": "Этап 1. Начальное состояние (пилот): 300 MAU, 3 600 чеков/мес, бюджет ≈ $21/мес",
    },
    {
        "key": "partners", "file": "02-partners.svg", "page": "2. Партнёры",
        "title": "Этап 2. Тестирование партнёрами: 5 000 MAU, 60 000 чеков/мес, бюджет ≈ $252/мес",
    },
    {
        "key": "prod", "file": "03-production.svg", "page": "3. Прод",
        "title": "Этап 3. Продовое решение: 60 000 MAU, 720 000 чеков/мес, бюджет ≈ $2 536/мес",
    },
]


def nodes(stage):
    p, pa, pr = stage == "pilot", stage == "partners", stage == "prod"
    n = {
        "user": ("Пользователь\nбраузер / PWA на телефоне", 30, 330, 150, 70, "user"),
        "idp": ("Identity Platform\nвход: email / Google", 440, 135, 170, 60, "sec"),
        "api": ("Cloud Run «api»\nSPA + REST API\n1 vCPU, 512 MiB\n"
                + ("min 0 / max 3" if p else "min 0 / max 20" if pa else "min 1 / max 50"),
                440, 300, 170, 110, "compute"),
        "sql": ("Cloud SQL PostgreSQL\n"
                + ("db-f1-micro, 10 GB SSD\nбез SLA" if p else
                   "1 vCPU, 3.75 GiB, 20 GB\nзональный" if pa else
                   "2 vCPU, 7.5 GiB, 100 GB\nHA: primary + standby"),
                440, 520, 170, 85, "db"),
        "gcs": ("Cloud Storage (приватный)\nфото чеков + миниатюры\n"
                + "Standard → Nearline через 30 дн.\nхранение 12 мес.",
                720, 300, 200, 100, "storage"),
        "eventarc": ("Eventarc (Pub/Sub)\nсобытие object.finalize", 720, 470, 200, 65, "int"),
        "worker": ("Cloud Run «worker»\nприватный, вызов по OIDC\n1 vCPU, 1 GiB, concurrency 1\n"
                   + ("max 5" if p else "max 30" if pa else "max 250"),
                   1000, 455, 190, 105, "compute"),
        "gemini": ("Vertex AI\nGemini 3.1 Flash-Lite\nфото → JSON по схеме чека", 1270, 460, 190, 90, "ai"),
        "scheduler": ("Cloud Scheduler\n1-го числа месяца", 1000, 135, 190, 55, "int"),
        "job": ("Cloud Run Job «insights»\nAI-отчёт о тратах за месяц", 1000, 245, 190, 70, "compute"),
        "ops": ("Cloud Logging + Monitoring\n" + ("базовые метрики" if p else "алерты, бюджеты, SLO"),
                1270, 640, 190, 65, "ops"),
        "cicd": ("Cloud Build → Artifact Registry\n" + ("сборка образов, деплой" if p else "деплой: staging → prod"), 1000, 640, 190, 65, "ops"),
    }
    if not p:
        n["dlq"] = ("Pub/Sub dead-letter\nпосле 5 попыток → «ввести вручную»", 720, 600, 200, 65, "int")
        n["staging"] = ("Проект staging\nтот же стек, db-f1-micro,\nсинтетические чеки", 1270, 135, 190, 75, "env")
    if pa:
        n["quota"] = ("Квоты партнёров\nлимит чеков/день, tenant ID\nбюджет-алерты", 440, 640, 170, 70, "sec")
    if pr:
        n["lb"] = ("External HTTPS\nLoad Balancer", 225, 330, 150, 70, "net")
        n["armor"] = ("Cloud Armor\nWAF, rate limit", 225, 210, 150, 60, "net")
        n["backup"] = ("PITR + 7 ежедневных\nбэкапов, тест восстановления", 440, 640, 170, 70, "db")
    return n


def edges(stage):
    """(откуда, куда, подпись, точки излома или None, позиция подписи или None)"""
    e = []
    if stage == "prod":
        e += [("user", "lb", "HTTPS", None, (202, 322)), ("lb", "api", "", None, None),
              ("armor", "lb", "", None, None)]
    else:
        e += [("user", "api", "HTTPS", None, None)]
    e += [
        ("user", "idp", "вход", [(105, 165)], (250, 165)),
        ("api", "idp", "проверка JWT", None, None),
        ("api", "sql", "чеки, категории,\nстатистика", None, None),
        ("user", "gcs", "загрузка фото напрямую по signed URL", [(105, 445), (760, 445)], (330, 445)),
        ("gcs", "eventarc", "новый объект", None, None),
        ("eventarc", "worker", "push", None, None),
        ("worker", "gcs", "читает фото,\nпишет миниатюру", None, (960, 420)),
        ("worker", "gemini", "фото +\nпромпт", None, (1230, 482)),
        ("worker", "sql", "позиции, сумма, категория", [(1095, 580)], (965, 580)),
        ("scheduler", "job", "", None, None),
        ("job", "gemini", "сводка трат", None, None),
        ("job", "sql", "агрегаты\nза месяц", [(665, 280), (665, 545)], (665, 470)),
    ]
    if stage != "pilot":
        e.append(("eventarc", "dlq", "сбой", None, (790, 560)))
    if stage == "prod":
        e.append(("sql", "backup", "", None, None))
    return e, None


def snap(b, px, py):
    """Точка на границе b, ортогональная к точке излома (px, py), если это возможно."""
    _, x, y, w, h, _ = b
    if x <= px <= x + w:
        return px, (y if py < y else y + h)
    if y <= py <= y + h:
        return (x if px < x else x + w), py
    return border_point(b, px, py)


def center(b):
    _, x, y, w, h, _ = b
    return x + w / 2, y + h / 2


def border_point(b, tx, ty):
    """Точка на границе прямоугольника b в направлении (tx, ty)."""
    _, x, y, w, h, _ = b
    cx, cy = x + w / 2, y + h / 2
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    sx = (w / 2) / abs(dx) if dx else float("inf")
    sy = (h / 2) / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


# ------------------------------------------------------------------ SVG
def svg_page(stage):
    n = nodes(stage["key"])
    es, _ = edges(stage["key"])
    W, H = 1500, 760
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           'font-family="Arial, Helvetica, sans-serif">',
           '<defs><marker id="arr" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">'
           '<path d="M0,0 L10,4 L0,8 z" fill="#444"/></marker></defs>',
           f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>',
           f'<text x="20" y="34" font-size="20" font-weight="bold" fill="#202124">{escape(stage["title"])}</text>']
    gx = 205 if stage["key"] == "prod" else 415
    out.append(f'<rect x="{gx}" y="95" width="{1485 - gx}" height="635" rx="10" fill="#F8FBFF" '
               'stroke="#1A73E8" stroke-dasharray="8,5" stroke-width="1.5"/>')
    out.append(f'<text x="{gx + 12}" y="118" font-size="14" fill="#1A73E8">Google Cloud · проект chekscan-'
               f'{stage["key"]} · регион us-central1 (Gemini — global endpoint)</text>')
    for a, b, label, pts, lp in es:
        A, B = n[a], n[b]
        if pts:
            x1, y1 = snap(A, *pts[0])
            x2, y2 = snap(B, *pts[-1])
            chain = [(x1, y1)] + pts + [(x2, y2)]
        else:
            bx, by = center(B)
            ax, ay = center(A)
            x1, y1 = border_point(A, bx, by)
            x2, y2 = border_point(B, ax, ay)
            chain = [(x1, y1), (x2, y2)]
        dash = ' stroke-dasharray="6,4"' if (a, b) in [("api", "idp"), ("armor", "lb"), ("eventarc", "dlq")] else ""
        ptxt = " ".join(f"{px:.1f},{py:.1f}" for px, py in chain)
        out.append(f'<polyline points="{ptxt}" fill="none" stroke="#444" '
                   f'stroke-width="1.6"{dash} marker-end="url(#arr)"/>')
        if label:
            mx, my = lp if lp else ((x1 + x2) / 2, (y1 + y2) / 2)
            lines = label.split("\n")
            wbox = max(len(s) for s in lines) * 6.4 + 8
            hbox = 15 * len(lines) + 4
            out.append(f'<rect x="{mx - wbox / 2:.1f}" y="{my - hbox / 2:.1f}" width="{wbox:.1f}" height="{hbox}" '
                       'fill="#FFFFFF" fill-opacity="0.92" rx="3"/>')
            for i, s in enumerate(lines):
                yy = my - hbox / 2 + 14 + i * 15
                out.append(f'<text x="{mx:.1f}" y="{yy:.1f}" font-size="12" fill="#333" text-anchor="middle">'
                           f'{escape(s)}</text>')
    for key, (label, x, y, w, h, kind) in n.items():
        fill, stroke = COLORS[kind]
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" '
                   'stroke-width="1.8"/>')
        lines = label.split("\n")
        top = y + h / 2 - (len(lines) - 1) * 8
        for i, s in enumerate(lines):
            weight = ' font-weight="bold"' if i == 0 else ""
            out.append(f'<text x="{x + w / 2}" y="{top + i * 16 + 4:.1f}" font-size="{13 if i == 0 else 12}"'
                       f'{weight} fill="#202124" text-anchor="middle">{escape(s)}</text>')
    out.append("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------ draw.io
def drawio_page(stage, pid):
    n = nodes(stage["key"])
    es, _ = edges(stage["key"])
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    gx = 205 if stage["key"] == "prod" else 415
    cells.append(f'<mxCell id="title" value="{html.escape(stage["title"], quote=True)}" '
                 'style="text;html=1;fontSize=20;fontStyle=1;align=left;verticalAlign=middle;" vertex="1" parent="1">'
                 '<mxGeometry x="20" y="15" width="1200" height="35" as="geometry"/></mxCell>')
    cells.append(f'<mxCell id="grp" value="Google Cloud · проект chekscan-{stage["key"]} · регион us-central1 '
                 '(Gemini — global endpoint)" style="rounded=1;arcSize=2;dashed=1;fillColor=#F8FBFF;'
                 'strokeColor=#1A73E8;fontColor=#1A73E8;verticalAlign=top;align=left;spacingLeft=10;fontSize=14;" '
                 f'vertex="1" parent="1"><mxGeometry x="{gx}" y="95" width="{1485 - gx}" height="635" as="geometry"/>'
                 '</mxCell>')
    for key, (label, x, y, w, h, kind) in n.items():
        fill, stroke = COLORS[kind]
        lines = label.split("\n")
        val = "<b>" + html.escape(lines[0]) + "</b><br>" + "<br>".join(html.escape(s) for s in lines[1:])
        cells.append(f'<mxCell id="{key}" value="{html.escape(val, quote=True)}" style="rounded=1;whiteSpace=wrap;'
                     f'html=1;fillColor={fill};strokeColor={stroke};strokeWidth=2;fontSize=12;" vertex="1" '
                     f'parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>')
    for i, (a, b, label, pts, _lp) in enumerate(es):
        geo = ""
        if pts:
            geo = "<Array as=\"points\">" + "".join(f'<mxPoint x="{px}" y="{py}"/>' for px, py in pts) + "</Array>"
        dash = "dashed=1;" if (a, b) in [("api", "idp"), ("armor", "lb"), ("eventarc", "dlq")] else ""
        cells.append(f'<mxCell id="e{i}" value="{html.escape(label.replace(chr(10), "<br>"), quote=True)}" '
                     f'style="endArrow=block;html=1;rounded=0;{dash}strokeColor=#444444;fontSize=11;'
                     f'labelBackgroundColor=#FFFFFF;" edge="1" parent="1" source="{a}" target="{b}">'
                     f'<mxGeometry relative="1" as="geometry">{geo}</mxGeometry></mxCell>')
    body = "".join(cells)
    return (f'<diagram id="{pid}" name="{html.escape(stage["page"])}"><mxGraphModel dx="1500" dy="760" grid="1" '
            'gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
            f'pageWidth="1500" pageHeight="760" math="0" shadow="0"><root>{body}</root></mxGraphModel></diagram>')


def main():
    pages = []
    for i, st in enumerate(STAGES):
        with open(os.path.join(HERE, st["file"]), "w", encoding="utf-8") as f:
            f.write(svg_page(st))
        pages.append(drawio_page(st, f"page{i + 1}"))
    xml = ('<mxfile host="app.diagrams.net" agent="lab4 generator" version="24.0.0">'
           + "".join(pages) + "</mxfile>")
    with open(os.path.join(HERE, "chekscan-infrastructure.drawio"), "w", encoding="utf-8") as f:
        f.write(xml)
    print("ok")


if __name__ == "__main__":
    main()
