// jest-axe (@types/jest-axe) は jest の expect のみを型拡張し、vitest には
// 対応していない。vitest 5 で expect パッケージがインライン化された結果、
// jest 向けの型拡張がここに引き継がれなくなったため、jest-dom の vitest.d.ts
// と同じパターンで toHaveNoViolations を Assertion に追加する。
import 'vitest';
import type { AxeResults } from 'axe-core';

interface JestAxeMatchers<R = unknown> {
  toHaveNoViolations(): R;
}

declare module 'vitest' {
  // 宣言マージのための空インターフェース（jest-dom の vitest.d.ts と同じ書き方）
  /* eslint-disable @typescript-eslint/no-empty-object-type */
  interface Assertion<T = AxeResults> extends JestAxeMatchers<T> {}
  interface AsymmetricMatchersContaining extends JestAxeMatchers {}
  /* eslint-enable @typescript-eslint/no-empty-object-type */
}
