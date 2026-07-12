import { describe, expect, it } from "vitest";

// 자리표시자 테스트. vitest 설정이 정상 동작하는지 확인하기 위한 샘플이며,
// 이후 lib 순수 함수 테스트로 교체될 예정이다.
describe("sample", () => {
  it("두 값을 더한다", () => {
    expect(1 + 1).toBe(2);
  });
});
