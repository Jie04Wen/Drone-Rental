import {describe, it, expect} from 'vitest'
import {parseSseEvents} from '@/utils/sse'

describe('parseSseEvents', () => {
    it('保留同一 SSE 事件中被拆分的数据换行', () => {
        const raw = 'data:推荐如下\ndata:| 型号 | 日租金 |\ndata:| --- | --- |\ndata:| Mini 3 Pro | 149元 |\n\n'

        expect(parseSseEvents(raw)).toEqual({
            remaining: '',
            chunks: ['推荐如下\n| 型号 | 日租金 |\n| --- | --- |\n| Mini 3 Pro | 149元 |'],
            done: false,
        })
    })

    it('保留未完成事件并识别结束标记', () => {
        expect(parseSseEvents('data:未完成')).toEqual({
            remaining: 'data:未完成',
            chunks: [],
            done: false,
        })

        expect(parseSseEvents('data:[DONE]\n\n').done).toBe(true)
    })

    it('保留流式分片开头的空格', () => {
        const parsed = parseSseEvents('data:-\n\ndata: **性价比**\n\n')
        expect(parsed.chunks.join('')).toBe('- **性价比**')
    })
    it('keeps content when DONE is in the same buffer', () => {
        const parsed = parseSseEvents('data:complete answer\n\ndata:[DONE]\n\n')

        expect(parsed).toEqual({
            remaining: '',
            chunks: ['complete answer'],
            done: true,
        })
    })
})
