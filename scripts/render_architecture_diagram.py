from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "assets" / "rideresolve-architecture.png"
WIDTH = 1920
HEIGHT = 1080


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size)


TITLE = font("segoeuib.ttf", 54)
SUBTITLE = font("segoeui.ttf", 25)
SECTION = font("seguisb.ttf", 23)
NODE = font("seguisb.ttf", 24)
SMALL = font("segoeui.ttf", 19)
TINY = font("segoeui.ttf", 16)


def centered_text(draw, box, text, face, fill, spacing=5):
    x0, y0, x1, y1 = box
    max_chars = max(10, int((x1 - x0) / (face.size * 0.56)))
    lines = []
    for paragraph in text.split("\n"):
        lines.extend(wrap(paragraph, width=max_chars) or [""])
    heights = [draw.textbbox((0, 0), line, font=face)[3] for line in lines]
    total = sum(heights) + spacing * (len(lines) - 1)
    y = y0 + ((y1 - y0) - total) / 2
    for line, line_height in zip(lines, heights):
        bounds = draw.textbbox((0, 0), line, font=face)
        width = bounds[2] - bounds[0]
        draw.text((x0 + ((x1 - x0) - width) / 2, y), line, font=face, fill=fill)
        y += line_height + spacing


def card(draw, box, text, fill, outline, text_fill="#10253F", radius=20, face=NODE):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=3)
    centered_text(draw, box, text, face, text_fill)


def arrow(draw, start, end, color="#45647F", width=5):
    draw.line((start, end), fill=color, width=width)
    x2, y2 = end
    x1, y1 = start
    dx, dy = x2 - x1, y2 - y1
    length = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    size = 14
    left = (x2 - ux * size + px * size * 0.65, y2 - uy * size + py * size * 0.65)
    right = (x2 - ux * size - px * size * 0.65, y2 - uy * size - py * size * 0.65)
    draw.polygon((end, left, right), fill=color)


def elbow_arrow(draw, points, color="#45647F", width=5):
    draw.line(points, fill=color, width=width, joint="curve")
    arrow(draw, points[-2], points[-1], color=color, width=width)


def main():
    image = Image.new("RGB", (WIDTH, HEIGHT), "#F4F7FB")
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, WIDTH, 150), fill="#0D243D")
    draw.text((78, 34), "RideResolve", font=TITLE, fill="#FFFFFF")
    draw.text(
        (485, 52),
        "Accuracy-First Multi-Agent Dispute Resolution",
        font=SUBTITLE,
        fill="#8FE8DD",
    )
    draw.text(
        (78, 112),
        "Natural-language intake  |  Five role-separated Agents  |  Deterministic Python boundary",
        font=TINY,
        fill="#C8D6E5",
    )

    draw.text((80, 176), "1  VERIFIED INPUT & OFFICIAL DATA", font=SECTION, fill="#1C6E8C")

    top_y0, top_y1 = 225, 350
    top_boxes = [
        (70, top_y0, 315, top_y1),
        (390, top_y0, 635, top_y1),
        (710, top_y0, 955, top_y1),
        (1030, top_y0, 1275, top_y1),
        (1350, top_y0, 1850, top_y1),
    ]
    top_labels = [
        "User dispute\n+ DISP/TRIP reference",
        "Official Case Intake",
        "Signed internal\nrun context",
        "Workflow-owned\ntool nodes",
        "Immutable evidence + versioned policy\nGPS  |  events  |  contacts  |  fare ledger",
    ]
    for box, label in zip(top_boxes, top_labels):
        card(draw, box, label, "#FFFFFF", "#59A9C2")
    for left, right in zip(top_boxes, top_boxes[1:]):
        arrow(draw, (left[2] + 8, (left[1] + left[3]) // 2), (right[0] - 8, (right[1] + right[3]) // 2))

    clarification = (390, 385, 635, 455)
    card(draw, clarification, "Missing / ambiguous\n→ NEEDS_CLARIFICATION", "#FFF4E5", "#EAA34A", face=SMALL)
    arrow(draw, (512, top_y1 + 3), (512, clarification[1] - 5), color="#D58B32", width=4)

    draw.text((80, 492), "2  FIVE ROLE-SEPARATED AGENTS", font=SECTION, fill="#6246A8")
    draw.text((482, 494), "LLMs organize evidence and recommend; they never set final status or money.", font=SMALL, fill="#536679")

    agent_y0, agent_y1 = 545, 690
    agent_boxes = [
        (70, agent_y0, 390, agent_y1),
        (430, agent_y0, 750, agent_y1),
        (790, agent_y0, 1110, agent_y1),
        (1150, agent_y0, 1470, agent_y1),
        (1510, agent_y0, 1830, agent_y1),
    ]
    agent_labels = [
        "1. Evidence Collection\nshared cited baseline",
        "2. Rider Advocate\nindependent argument",
        "3. Driver Advocate\nindependent argument",
        "4. Policy & Precedent\nadvisory context only",
        "5. Judge\nstructured recommendation",
    ]
    agent_colors = ["#E9FBF7", "#F1EEFF", "#F1EEFF", "#FFF8E8", "#E9F2FF"]
    outlines = ["#30A88E", "#7358C1", "#7358C1", "#D49A2F", "#3D78B8"]
    for box, label, fill, outline in zip(agent_boxes, agent_labels, agent_colors, outlines):
        card(draw, box, label, fill, outline, face=SMALL)
    for left, right in zip(agent_boxes, agent_boxes[1:]):
        arrow(draw, (left[2] + 5, (left[1] + left[3]) // 2), (right[0] - 5, (right[1] + right[3]) // 2), color="#6A5BA7", width=4)
    elbow_arrow(
        draw,
        [(1600, top_y1 + 5), (1600, 525), (230, 525), (230, agent_y0 - 6)],
        color="#2E91A8",
        width=4,
    )

    draw.text((80, 730), "3  DETERMINISTIC CONTROL BOUNDARY", font=SECTION, fill="#16755D")
    gate = (360, 780, 1320, 900)
    card(
        draw,
        gate,
        "Python Gate: evidence integrity → policy facts → matched rule → ledger-derived amount → Judge consistency",
        "#E8FAF3",
        "#16866B",
        face=NODE,
    )
    elbow_arrow(
        draw,
        [(1670, agent_y1 + 4), (1670, 750), (1150, 750), (1150, gate[1] - 6)],
        color="#3D78B8",
        width=5,
    )

    learning = (1390, 765, 1845, 910)
    card(
        draw,
        learning,
        "Governed Learning Loop\nHuman override → checksum-bound approved precedent\nAdvisory only; never overrides policy",
        "#FFFFFF",
        "#8799AA",
        face=SMALL,
    )

    outcome_y0, outcome_y1 = 955, 1035
    outcomes = [
        ((245, outcome_y0, 655, outcome_y1), "RESOLVED", "#DDF7EE", "#16866B"),
        ((755, outcome_y0, 1165, outcome_y1), "PENDING HUMAN REVIEW", "#FFF2D9", "#D38A20"),
        ((1265, outcome_y0, 1675, outcome_y1), "TECHNICAL FAILURE", "#FDE7E7", "#C94E4E"),
    ]
    for box, label, fill, outline in outcomes:
        card(draw, box, label, fill, outline, face=SMALL)
        arrow(draw, ((gate[0] + gate[2]) // 2, gate[3] + 4), ((box[0] + box[2]) // 2, box[1] - 6), color=outline, width=4)

    draw.text((1420, 1044), "SYNTHETIC · OFFLINE DEMO", font=TINY, fill="#6F7E8C")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, format="PNG", optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()
