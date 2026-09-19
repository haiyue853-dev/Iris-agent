import AiBot, { generateReqId } from '@wecom/aibot-node-sdk';
import { randomUUID } from 'node:crypto';
import readline from 'node:readline';
import path from 'node:path';
import { fileURLToPath } from 'node:url';


const MAX_REPLY_BYTES = 20_000;


export function truncateUtf8(value, maxBytes = MAX_REPLY_BYTES) {
  const text = String(value ?? '');
  if (Buffer.byteLength(text, 'utf8') <= maxBytes) return text;
  const suffix = '…';
  const suffixBytes = Buffer.byteLength(suffix, 'utf8');
  let result = '';
  for (const character of text) {
    if (Buffer.byteLength(result + character, 'utf8') + suffixBytes > maxBytes) break;
    result += character;
  }
  return result + suffix;
}


function emit(payload) {
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}


function stderr(level, ...values) {
  const message = values.map((value) => value instanceof Error ? value.message : String(value)).join(' ');
  process.stderr.write(`[${level}] ${message}\n`);
}


export function runBridge() {
  const botId = process.env.IRIS_WECOM_BOT_ID?.trim();
  const secret = process.env.IRIS_WECOM_BOT_SECRET?.trim();
  if (!botId || !secret) {
    emit({ type: 'status', status: 'not_configured' });
    process.exitCode = 2;
    return;
  }

  const logger = {
    debug: (...values) => stderr('debug', ...values),
    info: (...values) => stderr('info', ...values),
    warn: (...values) => stderr('warn', ...values),
    error: (...values) => stderr('error', ...values),
  };
  const client = new AiBot.WSClient({ botId, secret, logger });
  const pending = new Map();

  client.on('connected', () => emit({ type: 'status', status: 'connected' }));
  client.on('authenticated', () => emit({ type: 'status', status: 'authenticated' }));
  client.on('disconnected', (reason) => emit({ type: 'status', status: 'disconnected', reason: String(reason ?? '') }));
  client.on('reconnecting', (attempt) => emit({ type: 'status', status: 'reconnecting', attempt }));
  client.on('error', (error) => stderr('error', error));

  client.on('message.text', async (frame) => {
    const text = frame.body?.text?.content;
    const userId = frame.body?.from?.userid;
    if (!text || !userId) return;
    const eventId = randomUUID();
    const streamId = generateReqId('iris');
    pending.set(eventId, { frame, streamId });
    try {
      await client.replyStream(frame, streamId, '收到，正在处理…', false);
    } catch (error) {
      stderr('warn', 'initial reply failed:', error);
    }
    emit({
      type: 'message',
      event_id: eventId,
      user_id: String(userId),
      chat_id: String(frame.body?.chatid ?? userId),
      chat_type: String(frame.body?.chattype ?? 'single'),
      message_id: String(frame.body?.msgid ?? frame.headers?.req_id ?? eventId),
      text: String(text),
    });
  });

  const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  input.on('line', async (line) => {
    let command;
    try {
      command = JSON.parse(line);
    } catch {
      stderr('warn', 'ignored invalid JSON command');
      return;
    }
    if (command.type === 'reply') {
      const context = pending.get(String(command.event_id));
      if (!context) return;
      pending.delete(String(command.event_id));
      try {
        await client.replyStream(
          context.frame,
          context.streamId,
          truncateUtf8(command.text || '已处理。'),
          true,
        );
      } catch (error) {
        stderr('error', 'final reply failed:', error);
      }
      return;
    }
    if (command.type === 'send') {
      try {
        await client.sendMessage(String(command.chat_id), {
          msgtype: 'markdown',
          markdown: { content: truncateUtf8(command.text) },
        });
        emit({ type: 'send_result', request_id: String(command.request_id), ok: true });
      } catch (error) {
        stderr('error', 'active send failed:', error);
        emit({ type: 'send_result', request_id: String(command.request_id), ok: false });
      }
      return;
    }
    if (command.type === 'shutdown') {
      client.disconnect();
      input.close();
      process.exit(0);
    }
  });

  const shutdown = () => {
    client.disconnect();
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
  emit({ type: 'status', status: 'connecting' });
  client.connect();
}


const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) runBridge();
