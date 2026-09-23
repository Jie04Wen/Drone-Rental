export function parseSseEvents(rawBuffer) {
    const events = rawBuffer.replace(/\r\n/g, '\n').split('\n\n')
    const remaining = events.pop() ?? ''
    const chunks = []
    let done = false

    for (const event of events) {
        const dataLines = event
            .split('\n')
            .filter(line => line.startsWith('data:'))
            .map(line => line.slice(5))

        if (!dataLines.length) continue

        const payload = dataLines.join('\n')
        if (payload === '[DONE]') {
            done = true
            break
        }
        chunks.push(payload)
    }

    return {remaining, chunks, done}
}
