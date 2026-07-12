import { defineConfig } from "vitest/config";

// lib 순수 함수 단위 테스트용 설정. DOM이 필요 없으므로 node 환경을 사용한다.
export default defineConfig({
  test: {
    environment: "node",
    globals: true,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
