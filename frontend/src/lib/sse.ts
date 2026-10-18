export interface SseEvent {
  event: string;
  data: unknown;
}

/**
 * Incremental parser for a text/event-stream body. Feed it chunks; it returns the
 * complete events seen so far and keeps any partial event for the next chunk.
 */
export function createSseParser() {
  let buffer = "";
  return function feed(chunk: string): SseEvent[] {
    buffer += chunk.replace(/\r\n/g, "\n");
    const out: SseEvent[] = [];
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
      }
      if (data.length) out.push({ event, data: JSON.parse(data.join("\n")) });
    }
    return out;
  };
}
