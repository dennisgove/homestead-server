"""Turn an EPUB into one web page (browsers can't open EPUBs themselves).

Text and headings only: the chapters in reading order, with scripts, styles and
pictures dropped. Enough for the manuals in the library.
"""
import html
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container", "o": "http://www.idpf.org/2007/opf",
      "dc": "http://purl.org/dc/elements/1.1/"}
KEEP = re.compile(r"</?(p|h[1-6]|ul|ol|li|blockquote|pre|em|strong|b|i|br|hr|table|tr|td|th|dl|dt|dd)\b[^>]*>", re.I)


def to_html(path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as z:
        cont = ET.fromstring(z.read("META-INF/container.xml"))
        opf_path = cont.find(".//c:rootfile", NS).get("full-path")
        opf = ET.fromstring(z.read(opf_path))
        base = posixpath.dirname(opf_path)
        title = (opf.findtext(".//dc:title", "", NS) or "").strip()
        items = {i.get("id"): i.get("href") for i in opf.findall(".//o:manifest/o:item", NS)}
        chapters = []
        for ref in opf.findall(".//o:spine/o:itemref", NS):
            href = items.get(ref.get("idref"))
            if not href:
                continue
            raw = z.read(posixpath.normpath(posixpath.join(base, href))).decode("utf-8", "replace")
            body = re.search(r"(?is)<body[^>]*>(.*)</body>", raw)
            raw = body.group(1) if body else raw
            raw = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", "", raw)
            # keep only plain structure tags (no attributes), escape all other text
            out, pos = [], 0
            for m in re.finditer(r"<[^>]+>", raw):
                out.append(html.escape(html.unescape(raw[pos:m.start()])))
                tag = m.group(0)
                if KEEP.fullmatch(tag):
                    name = re.match(r"</?\s*(\w+)", tag).group(1).lower()
                    out.append(f"</{name}>" if tag.startswith("</") else f"<{name}>")
                pos = m.end()
            out.append(html.escape(html.unescape(raw[pos:])))
            chapters.append("".join(out))
    return title, "\n<hr>\n".join(chapters)
