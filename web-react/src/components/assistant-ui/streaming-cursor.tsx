export function StreamingCursor({ running }: { running: boolean }) {
  return running ? <span className="iris-streaming-cursor" aria-label="正在生成" /> : null;
}
