import type { NextConfig } from "next";

// HSTS(Strict-Transport-Security)는 Vercel이 프로덕션 배포에 자동 부여하므로 생략한다.
// CSP는 렌더링을 깨뜨릴 위험이 없는 저위험 지시어(frame-ancestors/base-uri/object-src/form-action)로만 한정한다.
// default-src·script-src·style-src·connect-src는 Next 인라인 스크립트/ECharts와 충돌해 사이트가 깨질 수 있어 이번엔 제외했다.
// 엄격한 script/style-src는 브라우저 육안 검증 후 별도 도입 예정이다.
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
          {
            key: "Content-Security-Policy",
            value:
              "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
