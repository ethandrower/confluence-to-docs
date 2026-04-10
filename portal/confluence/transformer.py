import re
import logging
from lxml import etree
import bleach

logger = logging.getLogger(__name__)

ALLOWED_TAGS = [
    'h1','h2','h3','h4','h5','h6',
    'p','br','hr',
    'strong','em','code','pre','s','sup','sub',
    'ul','ol','li',
    'table','thead','tbody','tr','th','td',
    'a','img',
    'div','span','blockquote',
]

ALLOWED_ATTRS = {
    'a': ['href', 'title'],
    'img': ['src', 'alt', 'width', 'height'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan'],
    'div': ['class', 'id'],
    'span': ['class'],
    'code': ['class'],
    'pre': ['class'],
    'h1': ['id'], 'h2': ['id'], 'h3': ['id'], 'h4': ['id'], 'h5': ['id'], 'h6': ['id'],
}

MACRO_PANEL_CLASSES = {
    'note': 'panel panel-note',
    'info': 'panel panel-info',
    'warning': 'panel panel-warning',
    'tip': 'panel panel-tip',
}

AC_NS = 'http://atlassian.com/content'
RI_NS = 'http://atlassian.com/ri'

NAMESPACES = {
    'ac': AC_NS,
    'ri': RI_NS,
}


def slugify(text):
    """Convert heading text to a URL-friendly id."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text


class StorageTransformer:
    def __init__(self, image_resolver=None, page_slug_resolver=None):
        """
        image_resolver: callable(filename) -> url
        page_slug_resolver: callable(page_title) -> slug
        """
        self.image_resolver = image_resolver or (lambda f: f'/media/confluence/{f}')
        self.page_slug_resolver = page_slug_resolver or (lambda t: '/docs/' + slugify(t))

    @staticmethod
    def _escape_html_entities(html: str) -> str:
        """Replace named HTML entities (e.g. &lsquo;) with their Unicode chars.
        Leaves XML entities (&amp; &lt; &gt; &quot; &apos;) intact."""
        import html as _html
        XML_ENTITIES = {'amp', 'lt', 'gt', 'quot', 'apos'}
        def replace(m):
            name = m.group(1)
            if name in XML_ENTITIES:
                return m.group(0)
            decoded = _html.unescape(f'&{name};')
            return decoded if decoded != f'&{name};' else m.group(0)
        return re.sub(r'&([a-zA-Z][a-zA-Z0-9]*);', replace, html)

    def transform(self, storage_html: str) -> str:
        if not storage_html:
            return ''
        try:
            storage_html = self._escape_html_entities(storage_html)
            # Wrap in root element with Confluence namespaces
            wrapped = (
                '<root '
                'xmlns:ac="http://atlassian.com/content" '
                'xmlns:ri="http://atlassian.com/ri">'
                f'{storage_html}'
                '</root>'
            )
            parser = etree.XMLParser(recover=True)
            root = etree.fromstring(wrapped.encode('utf-8'), parser)
            self._transform_node(root)
            self._add_heading_ids(root)
            # Serialize inner content (skip root wrapper)
            parts = []
            if root.text:
                parts.append(root.text)
            for child in root:
                parts.append(etree.tostring(child, encoding='unicode', method='html'))
            html = ''.join(parts)
            # Sanitize
            return bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
        except Exception as e:
            logger.exception(f"StorageTransformer.transform failed: {e}")
            return f'<p class="transform-error">Content rendering error: {e}</p>'

    def _qname(self, node):
        """Return localname of a node tag."""
        tag = node.tag
        if isinstance(tag, str) and '{' in tag:
            return etree.QName(tag).localname
        return tag if isinstance(tag, str) else ''

    def _transform_node(self, node):
        for child in list(node):
            localname = self._qname(child)
            if localname == 'structured-macro':
                self._transform_macro(node, child)
            elif localname == 'image':
                self._transform_image(node, child)
            elif localname == 'link':
                self._transform_link(node, child)
            elif localname in ('task-list', 'task'):
                self._transform_task(node, child)
            else:
                self._transform_node(child)

    def _find_ac(self, node, localname):
        return node.find(f'{{{AC_NS}}}{localname}')

    def _find_ri(self, node, localname):
        return node.find(f'{{{RI_NS}}}{localname}')

    def _findall_ac(self, node, localname):
        return node.findall(f'.//{{{AC_NS}}}{localname}')

    def _transform_macro(self, parent, macro):
        name = macro.get(f'{{{AC_NS}}}name', '')

        if name == 'code':
            lang = ''
            for param in self._findall_ac(macro, 'parameter'):
                if param.get(f'{{{AC_NS}}}name') == 'language':
                    lang = param.text or ''
                    break
            body_el = self._find_ac(macro, 'plain-text-body')
            body = body_el.text or '' if body_el is not None else ''
            idx = list(parent).index(macro)
            pre = etree.Element('pre')
            code = etree.SubElement(pre, 'code')
            if lang:
                code.set('class', f'language-{lang}')
            code.text = body
            parent.insert(idx, pre)
            if pre.tail is None:
                pre.tail = macro.tail
            parent.remove(macro)

        elif name in MACRO_PANEL_CLASSES:
            idx = list(parent).index(macro)
            div = etree.Element('div')
            div.set('class', MACRO_PANEL_CLASSES[name])
            body_el = self._find_ac(macro, 'rich-text-body')
            if body_el is not None:
                self._transform_node(body_el)
                for child in list(body_el):
                    div.append(child)
                if body_el.text:
                    div.text = body_el.text
            div.tail = macro.tail
            parent.insert(idx, div)
            parent.remove(macro)

        elif name == 'toc':
            idx = list(parent).index(macro)
            div = etree.Element('div')
            div.set('class', 'toc-placeholder')
            div.tail = macro.tail
            parent.insert(idx, div)
            parent.remove(macro)

        elif name == 'expand':
            # Render expand macro as a details/summary
            idx = list(parent).index(macro)
            details = etree.Element('div')
            details.set('class', 'confluence-expand')
            title_el = None
            for param in self._findall_ac(macro, 'parameter'):
                if param.get(f'{{{AC_NS}}}name') == 'title':
                    title_el = param
                    break
            summary = etree.SubElement(details, 'div')
            summary.set('class', 'confluence-expand-title')
            summary.text = (title_el.text if title_el is not None else 'Show/Hide') or 'Show/Hide'
            body_el = self._find_ac(macro, 'rich-text-body')
            if body_el is not None:
                self._transform_node(body_el)
                content_div = etree.SubElement(details, 'div')
                content_div.set('class', 'confluence-expand-content')
                for child in list(body_el):
                    content_div.append(child)
            details.tail = macro.tail
            parent.insert(idx, details)
            parent.remove(macro)

        else:
            # Unknown macro: preserve inner rich-text-body content
            body_el = self._find_ac(macro, 'rich-text-body')
            if body_el is not None:
                self._transform_node(body_el)
                idx = list(parent).index(macro)
                for i, child in enumerate(list(body_el)):
                    parent.insert(idx + i, child)
                if body_el.text:
                    # prepend text to first inserted child or parent
                    pass
            parent.remove(macro)

    def _transform_image(self, parent, image_node):
        attachment = image_node.find(f'.//{{{RI_NS}}}attachment')
        if attachment is not None:
            filename = attachment.get(f'{{{RI_NS}}}filename', '')
            url = self.image_resolver(filename)
            idx = list(parent).index(image_node)
            img = etree.Element('img')
            img.set('src', url)
            img.set('alt', filename)
            # Preserve width/height if specified
            width = image_node.get(f'{{{AC_NS}}}width', '')
            height = image_node.get(f'{{{AC_NS}}}height', '')
            if width:
                img.set('width', width)
            if height:
                img.set('height', height)
            img.tail = image_node.tail
            parent.insert(idx, img)
            parent.remove(image_node)
        else:
            parent.remove(image_node)

    def _transform_link(self, parent, link_node):
        page_el = link_node.find(f'.//{{{RI_NS}}}page')
        url_el = link_node.find(f'.//{{{RI_NS}}}url')
        link_body = link_node.find(f'{{{AC_NS}}}link-body')
        link_text = link_body.text if link_body is not None else ''

        idx = list(parent).index(link_node)
        a = etree.Element('a')

        if page_el is not None:
            title = page_el.get(f'{{{RI_NS}}}content-title', '')
            href = self.page_slug_resolver(title)
            a.set('href', href)
            a.text = link_text or title
        elif url_el is not None:
            href = url_el.get(f'{{{RI_NS}}}value', '#')
            a.set('href', href)
            a.text = link_text or href
        else:
            a.set('href', '#')
            a.text = link_text or ''

        a.tail = link_node.tail
        parent.insert(idx, a)
        parent.remove(link_node)

    def _transform_task(self, parent, task_node):
        """Transform Confluence task lists to HTML checkboxes."""
        localname = self._qname(task_node)
        if localname == 'task-list':
            idx = list(parent).index(task_node)
            ul = etree.Element('ul')
            ul.set('class', 'task-list')
            for task in task_node:
                if self._qname(task) == 'task':
                    li = etree.SubElement(ul, 'li')
                    li.set('class', 'task-item')
                    status_el = task.find(f'{{{AC_NS}}}task-status')
                    body_el = task.find(f'{{{AC_NS}}}task-body')
                    status = status_el.text if status_el is not None else 'incomplete'
                    checkbox = etree.SubElement(li, 'input')
                    checkbox.set('type', 'checkbox')
                    checkbox.set('disabled', 'disabled')
                    if status == 'complete':
                        checkbox.set('checked', 'checked')
                    span = etree.SubElement(li, 'span')
                    if body_el is not None:
                        self._transform_node(body_el)
                        span.text = body_el.text
                        for child in list(body_el):
                            span.append(child)
            ul.tail = task_node.tail
            parent.insert(idx, ul)
            parent.remove(task_node)

    def _add_heading_ids(self, root):
        """Add id attributes to headings for TOC anchor links."""
        counts = {}
        for heading in root.iter('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            text = ''.join(heading.itertext())
            base_id = slugify(text)
            count = counts.get(base_id, 0)
            heading_id = base_id if count == 0 else f'{base_id}-{count}'
            counts[base_id] = count + 1
            heading.set('id', heading_id)
