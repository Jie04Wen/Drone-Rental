import {marked} from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({
    breaks: true,
    gfm: true,
})

export function renderMarkdown(text) {
    if (!text) return ''
    const raw = marked.parse(text, {async: false})
    return DOMPurify.sanitize(raw, {
        USE_PROFILES: {html: true},
    })
}
