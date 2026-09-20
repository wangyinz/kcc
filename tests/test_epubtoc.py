import os
import tempfile
import unittest
from pathlib import Path

from kindlecomicconverter import epubtoc


class EpubTocTests(unittest.TestCase):
    def test_epub3_nav_and_processed_page_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops = root / 'OPS'
            ops.mkdir()
            pages = []
            for i in range(3):
                page = ops / f'p{i}.xhtml'
                page.write_text('<html xmlns="http://www.w3.org/1999/xhtml"><body/></html>', encoding='utf-8')
                pages.append(page)

            (ops / 'content.opf').write_text(
                '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
                   <manifest>
                     <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
                   </manifest><spine/>
                   </package>''',
                encoding='utf-8')
            (ops / 'nav.xhtml').write_text(
                '''<html xmlns="http://www.w3.org/1999/xhtml"
                          xmlns:epub="http://www.idpf.org/2007/ops"><body>
                   <nav epub:type="toc"><ol>
                     <li><a href="p0.xhtml">Vol 1</a><ol>
                       <li><a href="p1.xhtml">Chapter 1</a></li>
                     </ol></li>
                     <li><a href="p2.xhtml">Vol 2</a></li>
                   </ol></nav></body></html>''',
                encoding='utf-8')

            toc = epubtoc.read_epub_toc(
                str(ops / 'content.opf'),
                {str(page): index for index, page in enumerate(pages)})
            self.assertEqual(toc, [
                (1, 'Vol 1', 0),
                (2, 'Chapter 1', 1),
                (1, 'Vol 2', 2),
            ])

            mapped = epubtoc.map_toc_to_sequence(toc, [
                'cover.jpg',
                'kcc-0001.jpg',
                'kcc-0001-kcc-b.jpg',
                'kcc-0002.jpg',
                'kcc-0003.jpg',
            ])
            self.assertEqual(mapped, [
                (1, 'Vol 1', 1),
                (2, 'Chapter 1', 3),
                (1, 'Vol 2', 4),
            ])

    def test_epub2_ncx_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops = root / 'OPS'
            ops.mkdir()
            pages = []
            for i in range(3):
                page = ops / f'p{i}.xhtml'
                page.write_text('<html xmlns="http://www.w3.org/1999/xhtml"><body/></html>', encoding='utf-8')
                pages.append(page)

            (ops / 'content.opf').write_text(
                '''<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
                   <manifest>
                     <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
                   </manifest><spine toc="ncx"/>
                   </package>''',
                encoding='utf-8')
            (ops / 'toc.ncx').write_text(
                '''<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>
                     <navPoint><navLabel><text>Part A</text></navLabel><content src="p0.xhtml"/>
                       <navPoint><navLabel><text>Chapter A1</text></navLabel><content src="p1.xhtml"/></navPoint>
                     </navPoint>
                     <navPoint><navLabel><text>Part B</text></navLabel><content src="p2.xhtml"/></navPoint>
                   </navMap></ncx>''',
                encoding='utf-8')

            toc = epubtoc.read_epub_toc(
                str(ops / 'content.opf'),
                {str(page): index for index, page in enumerate(pages)})
            self.assertEqual(toc, [
                (1, 'Part A', 0),
                (2, 'Chapter A1', 1),
                (1, 'Part B', 2),
            ])

    def test_chunk_mapping_drops_outside_entries_and_rebases_levels(self):
        toc = [
            (1, 'Volume 1', 0),
            (2, 'Chapter 1', 1),
            (2, 'Chapter 2', 3),
            (1, 'Volume 2', 5),
            (2, 'Chapter 3', 6),
        ]
        mapped = epubtoc.map_toc_to_sequence(
            toc,
            ['kcc-0004.jpg', 'kcc-0005.jpg', 'kcc-0006.jpg'])
        self.assertEqual(mapped, [
            (1, 'Chapter 2', 0),
            (1, 'Volume 2', 2),
        ])


if __name__ == '__main__':
    unittest.main()
