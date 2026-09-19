import assert from 'node:assert/strict';
import test from 'node:test';

import { truncateUtf8 } from './bridge.mjs';


test('truncateUtf8 keeps enterprise wechat replies within byte limit', () => {
  const text = '字'.repeat(100);
  const result = truncateUtf8(text, 31);

  assert.ok(Buffer.byteLength(result, 'utf8') <= 31);
  assert.ok(result.endsWith('…'));
});
