import type { NextConfig } from "next";

// HSTS(Strict-Transport-Security)는 Vercel이 프로덕션 배포에 자동 부여하므로 생략한다.
// 엄격한 CSP는 Next.js 인라인 스크립트(unsafe-inline 필요)와 충돌하므로 이번 범위에서 제외했다.
const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "X-Frame-Options",
            value: "DENY",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
