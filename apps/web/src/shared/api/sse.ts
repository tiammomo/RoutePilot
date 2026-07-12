import { parsePublicRunEvent, type PublicRunEvent } from "./public-event";

export type StreamStatus = "connecting" | "live" | "reconnecting" | "offline" | "closed";

interface SseFrame {
  event?: string;
  id?: string;
  data: string;
}

function parseFrame(block: string): SseFrame | null {
  const data: string[] = [];
  let event: string | undefined;
  let id: string | undefined;
  for (const rawLine of block.split(/\r?\n/)) {
    if (!rawLine || rawLine.startsWith(":")) continue;
    const separator = rawLine.indexOf(":");
    const field = separator < 0 ? rawLine : rawLine.slice(0, separator);
    const value = separator < 0 ? "" : rawLine.slice(separator + 1).replace(/^ /, "");
    if (field === "data") data.push(value);
    if (field === "event") event = value;
    if (field === "id") id = value;
  }
  return data.length ? { event, id, data: data.join("\n") } : null;
}

export interface StreamOnceOptions {
  runId: string;
  afterSeq: number;
  signal: AbortSignal;
  onEvent: (event: PublicRunEvent) => void;
  onHeartbeat?: () => void;
  onOpen?: () => void;
  fetchImpl?: typeof fetch;
}

export async function streamRunEventsOnce(options: StreamOnceOptions): Promise<void> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const response = await fetchImpl(
    `/api/v1/runs/${encodeURIComponent(options.runId)}/events?after_seq=${options.afterSeq}`,
    {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        Accept: "text/event-stream",
        ...(options.afterSeq > 0 ? { "Last-Event-ID": String(options.afterSeq) } : {}),
      },
      signal: options.signal,
    },
  );
  if (!response.ok || !response.body) throw new Error(`EVENT_STREAM_${response.status}`);
  options.onOpen?.();

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const consume = (frameText: string) => {
    const frame = parseFrame(frameText);
    if (!frame) return;
    let payload: unknown;
    try {
      payload = JSON.parse(frame.data);
    } catch {
      return;
    }
    const event = parsePublicRunEvent(payload);
    if (event) options.onEvent(event);
    else if (frame.event === "heartbeat") options.onHeartbeat?.();
  };

  while (!options.signal.aborted) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? "";
    frames.forEach(consume);
    if (done) {
      if (buffer.trim()) consume(buffer);
      return;
    }
  }
}

export interface FollowStreamOptions extends Omit<StreamOnceOptions, "afterSeq" | "onOpen"> {
  getAfterSeq: () => number;
  isTerminal: () => boolean;
  onStatus: (status: StreamStatus) => void;
  wait?: (milliseconds: number, signal: AbortSignal) => Promise<void>;
}

function wait(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

export async function followRunEvents(options: FollowStreamOptions): Promise<void> {
  let attempt = 0;
  while (!options.signal.aborted && !options.isTerminal()) {
    const online = typeof navigator === "undefined" || navigator.onLine;
    options.onStatus(!online ? "offline" : attempt ? "reconnecting" : "connecting");
    if (!online) {
      await (options.wait ?? wait)(1_000, options.signal);
      continue;
    }
    try {
      await streamRunEventsOnce({
        ...options,
        afterSeq: options.getAfterSeq(),
        onOpen: () => {
          attempt = 0;
          options.onStatus("live");
        },
      });
      if (options.isTerminal()) break;
    } catch (error) {
      if (options.signal.aborted) break;
      attempt += 1;
      options.onStatus("reconnecting");
      await (options.wait ?? wait)(Math.min(10_000, 500 * 2 ** Math.min(attempt, 4)), options.signal);
      continue;
    }
    attempt += 1;
    await (options.wait ?? wait)(Math.min(10_000, 500 * 2 ** Math.min(attempt, 4)), options.signal);
  }
  if (!options.signal.aborted) options.onStatus("closed");
}
