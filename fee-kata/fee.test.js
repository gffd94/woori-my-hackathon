const test = require('node:test');
const assert = require('node:assert/strict');
const { transferFee } = require('./fee');

test('같은 은행 이체는 수수료가 0원이다', () => {
  assert.equal(transferFee(10000, true), 0);
});

test('다른 은행 이체는 수수료가 500원이다', () => {
  assert.equal(transferFee(10000, false), 500);
});

test('한도와 같은 금액은 이체할 수 있다', () => {
  assert.equal(transferFee(5000000, false), 500);
});

test('한도를 넘으면 LIMIT_PER_TX 오류가 발생한다', () => {
  assert.throws(() => transferFee(5000001, false), { message: 'LIMIT_PER_TX' });
});

test('0원 이체는 INVALID_AMOUNT 오류가 발생한다', () => {
  assert.throws(() => transferFee(0, true), { message: 'INVALID_AMOUNT' });
});

test('음수 금액 이체는 INVALID_AMOUNT 오류가 발생한다', () => {
  assert.throws(() => transferFee(-1000, false), { message: 'INVALID_AMOUNT' });
});