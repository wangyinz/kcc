# -*- coding: utf-8 -*-
"""Helpers for preserving an EPUB's existing table of contents during KCC conversion."""

import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit


_EPUB_TYPE = '{http://www.idpf.org/2007/ops}type'
_SOURCE_PAGE_RE = re.compile(r'kcc-(\d+)', re.IGNORECASE)


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _resolve(base_file, href):
    """Resolve an EPUB href against the document that contains it."""
    if not href:
        return None
    path = unquote(urlsplit(href).path)
    if not path:
        return _norm(base_file)
    return _norm(os.path.join(os.path.dirname(base_file), path))


def _text(node):
    if node is None:
        return ''
    return ' '.join(''.join(node.itertext()).split())


def _normalize_levels(entries):
    """Make TOC levels valid for NCX/PDF (first level=1, no jumps >1)."""
    if not entries:
        return []
    min_level = min(max(1, int(entry[0])) for entry in entries)
    normalized = []
    previous = 0
    for level, title, page_index in entries:
        level = max(1, int(level) - min_level + 1)
        if not normalized:
            level = 1
        elif level > previous + 1:
            level = previous + 1
        normalized.append((level, title, page_index))
        previous = level
    return normalized


def _read_nav(nav_path, page_map):
    try:
        root = ET.parse(nav_path).getroot()
    except (ET.ParseError, OSError):
        return []

    toc_nav = None
    for nav in root.findall('.//{*}nav'):
        nav_type = nav.attrib.get(_EPUB_TYPE, nav.attrib.get('epub:type', nav.attrib.get('type', '')))
        if 'toc' in nav_type.split():
            toc_nav = nav
            break
    if toc_nav is None:
        return []

    top_ol = next((child for child in toc_nav if child.tag.rsplit('}', 1)[-1] == 'ol'), None)
    if top_ol is None:
        top_ol = toc_nav.find('.//{*}ol')
    if top_ol is None:
        return []

    entries = []

    def walk_ol(ol, level):
        for li in (child for child in ol if child.tag.rsplit('}', 1)[-1] == 'li'):
            anchor = next((child for child in li if child.tag.rsplit('}', 1)[-1] == 'a'), None)
            if anchor is None:
                anchor = li.find('.//{*}a')
            if anchor is not None:
                target = _resolve(nav_path, anchor.attrib.get('href'))
                if target in page_map:
                    title = _text(anchor)
                    if title:
                        entries.append((level, title, page_map[target]))
            for child in li:
                if child.tag.rsplit('}', 1)[-1] == 'ol':
                    walk_ol(child, level + 1)

    walk_ol(top_ol, 1)
    return _normalize_levels(entries)


def _read_ncx(ncx_path, page_map):
    try:
        root = ET.parse(ncx_path).getroot()
    except (ET.ParseError, OSError):
        return []

    nav_map = root.find('.//{*}navMap')
    if nav_map is None:
        return []

    entries = []

    def walk(parent, level):
        for nav_point in (child for child in parent if child.tag.rsplit('}', 1)[-1] == 'navPoint'):
            content = nav_point.find('./{*}content')
            label = nav_point.find('./{*}navLabel/{*}text')
            if content is not None:
                target = _resolve(ncx_path, content.attrib.get('src'))
                if target in page_map:
                    title = _text(label)
                    if title:
                        entries.append((level, title, page_map[target]))
            walk(nav_point, level + 1)

    walk(nav_map, 1)
    return _normalize_levels(entries)


def read_epub_toc(opf_path, page_to_image_index):
    """Return a list of (level, title, image_index) from EPUB3 NAV or EPUB2 NCX.

    page_to_image_index maps absolute XHTML content-document paths to the zero-based
    image index KCC extracted from the EPUB spine.
    """
    page_map = {_norm(path): index for path, index in page_to_image_index.items()}
    if not page_map:
        return []

    try:
        root = ET.parse(opf_path).getroot()
    except (ET.ParseError, OSError):
        return []

    manifest = {}
    for item in root.findall('.//{*}manifest/{*}item'):
        item_id = item.attrib.get('id')
        if item_id:
            manifest[item_id] = item

    base_dir = os.path.dirname(opf_path)

    # EPUB 3 navigation document.
    for item in manifest.values():
        properties = item.attrib.get('properties', '').split()
        if 'nav' in properties and item.attrib.get('href'):
            nav_path = _norm(os.path.join(base_dir, unquote(urlsplit(item.attrib['href']).path)))
            entries = _read_nav(nav_path, page_map)
            if entries:
                return entries

    # EPUB 2 NCX fallback.
    spine = root.find('.//{*}spine')
    ncx_item = None
    if spine is not None and spine.attrib.get('toc'):
        ncx_item = manifest.get(spine.attrib['toc'])
    if ncx_item is None:
        ncx_item = next((item for item in manifest.values()
                         if item.attrib.get('media-type') == 'application/x-dtbncx+xml'), None)
    if ncx_item is not None and ncx_item.attrib.get('href'):
        ncx_path = _norm(os.path.join(base_dir, unquote(urlsplit(ncx_item.attrib['href']).path)))
        return _read_ncx(ncx_path, page_map)

    return []


def source_page_index(filename):
    """Return the zero-based source page encoded in a sanitized KCC image filename."""
    match = _SOURCE_PAGE_RE.search(os.path.basename(filename))
    return int(match.group(1)) - 1 if match else None


def map_toc_to_sequence(toc_entries, filenames):
    """Map original EPUB TOC entries to positions in a processed KCC page sequence.

    filenames must be in final output order. Returned positions are zero-based.
    This also works on a chunk/tome: entries outside that chunk are omitted and levels
    are normalized so Kindle NCX and PDF outlines remain valid.
    """
    first_by_source = {}
    for position, filename in enumerate(filenames):
        source_index = source_page_index(filename)
        if source_index is not None and source_index not in first_by_source:
            first_by_source[source_index] = position

    if not first_by_source or not toc_entries:
        return []

    source_pages = sorted(first_by_source)
    minimum = source_pages[0]
    maximum = source_pages[-1]
    mapped = []

    for level, title, source_index in toc_entries:
        if source_index < minimum or source_index > maximum:
            continue
        target_source = source_index
        if target_source not in first_by_source:
            target_source = next((page for page in source_pages if page >= source_index), None)
            if target_source is None:
                continue
        mapped.append((level, title, first_by_source[target_source]))

    return _normalize_levels(mapped)
