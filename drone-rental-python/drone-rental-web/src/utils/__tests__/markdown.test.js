import {describe, it, expect} from 'vitest'
import {renderMarkdown} from '@/utils/markdown'

describe('renderMarkdown', () => {
    it('空输入返回空字符串', () => {
        expect(renderMarkdown('')).toBe('')
        expect(renderMarkdown(null)).toBe('')
        expect(renderMarkdown(undefined)).toBe('')
    })

    it('渲染标题为 h2 标签', () => {
        const html = renderMarkdown('## 标题')
        expect(html).toContain('<h2>标题</h2>')
    })

    it('渲染加粗文本', () => {
        const html = renderMarkdown('**重点**')
        expect(html).toContain('<strong>重点</strong>')
    })

    it('渲染无序列表', () => {
        const html = renderMarkdown('- 项一\n- 项二')
        expect(html).toContain('<ul>')
        expect(html).toContain('<li>项一</li>')
        expect(html).toContain('<li>项二</li>')
    })

    it('剥离危险脚本标签', () => {
        const html = renderMarkdown('<script>alert(1)</script>正常文本')
        expect(html).not.toContain('<script>')
        expect(html).toContain('正常文本')
    })

    it('渲染行内代码', () => {
        const html = renderMarkdown('使用 `npm` 安装')
        expect(html).toContain('<code>npm</code>')
    })

    it('渲染 GFM 表格', () => {
        const html = renderMarkdown('| 型号 | 日租金 |\n| --- | --- |\n| Mini 3 Pro | 149元 |')
        expect(html).toContain('<table>')
        expect(html).toContain('<th>型号</th>')
        expect(html).toContain('<td>Mini 3 Pro</td>')
    })
})
