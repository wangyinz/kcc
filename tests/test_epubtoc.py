import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

from PIL import Image

from kindlecomicconverter import comic2ebook, epubtoc


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


    def test_end_to_end_epub_output_keeps_nav_toc(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source.epub'
            output = root / 'output.epub'

            image_data = []
            for value in (230, 200, 170):
                stream = BytesIO()
                Image.new('RGB', (40, 60), (value, value, value)).save(stream, format='JPEG')
                image_data.append(stream.getvalue())

            container_xml = '''<?xml version="1.0"?>
                <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
                  <rootfiles><rootfile full-path="OEBPS/content.opf"
                    media-type="application/oebps-package+xml"/></rootfiles>
                </container>'''
            opf = '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
                <manifest>
                  <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
                  <item id="p1" href="Text/p1.xhtml" media-type="application/xhtml+xml"/>
                  <item id="p2" href="Text/p2.xhtml" media-type="application/xhtml+xml"/>
                  <item id="p3" href="Text/p3.xhtml" media-type="application/xhtml+xml"/>
                  <item id="i1" href="Images/i1.jpg" media-type="image/jpeg"/>
                  <item id="i2" href="Images/i2.jpg" media-type="image/jpeg"/>
                  <item id="i3" href="Images/i3.jpg" media-type="image/jpeg"/>
                </manifest>
                <spine><itemref idref="p1"/><itemref idref="p2"/><itemref idref="p3"/></spine>
              </package>'''
            nav = '''<html xmlns="http://www.w3.org/1999/xhtml"
                     xmlns:epub="http://www.idpf.org/2007/ops"><body>
                     <nav epub:type="toc"><ol>
                       <li><a href="Text/p1.xhtml">Volume 1</a><ol>
                         <li><a href="Text/p2.xhtml">Chapter 1</a></li>
                       </ol></li>
                       <li><a href="Text/p3.xhtml">Volume 2</a></li>
                     </ol></nav></body></html>'''

            with ZipFile(source, 'w') as archive:
                archive.writestr('mimetype', 'application/epub+zip', ZIP_STORED)
                archive.writestr('META-INF/container.xml', container_xml)
                archive.writestr('OEBPS/content.opf', opf)
                archive.writestr('OEBPS/nav.xhtml', nav)
                for index in range(1, 4):
                    archive.writestr(
                        f'OEBPS/Text/p{index}.xhtml',
                        f'''<html xmlns="http://www.w3.org/1999/xhtml"><body>
                            <img src="../Images/i{index}.jpg"/></body></html>''')
                    archive.writestr(f'OEBPS/Images/i{index}.jpg', image_data[index - 1])

            result = comic2ebook.main([
                '--noprocessing',
                '--preserve-epub-toc',
                '--format', 'EPUB',
                '--output', str(output),
                str(source),
            ])
            self.assertEqual(result, 0)
            self.assertTrue(output.exists())

            with ZipFile(output) as archive:
                output_nav = ET.fromstring(archive.read('OEBPS/nav.xhtml'))
            labels = [
                ' '.join(''.join(anchor.itertext()).split())
                for anchor in output_nav.findall('.//{*}nav[@id="toc"]//{*}a')
            ]
            self.assertEqual(labels, ['Volume 1', 'Chapter 1', 'Volume 2'])



if __name__ == '__main__':
    unittest.main()
